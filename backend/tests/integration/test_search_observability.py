# backend/tests/integration/test_search_observability.py
"""
Integration tests for search observability and candidate persistence.

Covers:
- Persisting top-N candidates when provided to /api/search-history
- Ensuring SearchService returns search_metadata.observability_candidates
  and that payload can be forwarded to persistence API
"""

from typing import Dict, List

from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm import Session

from app.models.search_event import SearchEventCandidate
from app.models.service_catalog import ServiceCatalog
from app.services.search_service import SearchService


def _guest_headers() -> Dict[str, str]:
    import uuid

    return {"X-Guest-Session-ID": f"test-guest-{uuid.uuid4().hex[:8]}", "X-Search-Origin": "/search"}


@pytest.mark.integration
def test_persist_candidates_on_record_search(client: TestClient, db: Session):
    """Assert that providing observability_candidates persists rows in search_event_candidates."""
    # Pick two real services for valid FK references
    services: List[ServiceCatalog] = db.query(ServiceCatalog).filter(ServiceCatalog.is_active == True).limit(2).all()
    assert services, "Expected at least one service in catalog for test"

    candidates = [
        {
            "position": 1,
            "service_catalog_id": services[0].id,
            "score": 0.95,
            "vector_score": 0.93,
            "lexical_score": None,
            "source": "vector",
        }
    ]
    if len(services) > 1:
        candidates.append(
            {
                "position": 2,
                "service_catalog_id": services[1].id,
                "score": 0.90,
                "vector_score": 0.88,
                "lexical_score": None,
                "source": "vector",
            }
        )

    payload = {
        "search_query": "piano lessons",
        "search_type": "natural_language",
        "results_count": 2,
        "observability_candidates": candidates,
    }

    resp = client.post("/api/search-history/", json=payload, headers=_guest_headers())
    assert resp.status_code == 201, resp.text
    body = resp.json()
    event_id = body.get("search_event_id")
    assert event_id, "Expected search_event_id in response"

    # Verify rows persisted
    rows = (
        db.query(SearchEventCandidate)
        .filter(SearchEventCandidate.search_event_id == event_id)
        .order_by(SearchEventCandidate.position)
        .all()
    )
    assert len(rows) == len(candidates)
    assert rows[0].service_catalog_id == candidates[0]["service_catalog_id"]
    assert rows[0].position == 1


@pytest.mark.integration
def test_search_service_returns_observability_candidates_and_can_persist(db: Session, client: TestClient, monkeypatch):
    """Ensure SearchService returns observability candidates and they can be written via the API."""
    # Prepare two real services to return from vector similarity
    services: List[ServiceCatalog] = db.query(ServiceCatalog).filter(ServiceCatalog.is_active == True).limit(2).all()
    assert services, "Expected at least one service in catalog for test"

    # Monkeypatch model encode to avoid heavy load
    class _FakeModel:
        def encode(self, texts):
            # Return a fixed-length vector (length does not matter for stubbed repo)
            return [[0.0] * 384]

    monkeypatch.setattr("app.services.search_service.get_cached_model", lambda *a, **k: _FakeModel())

    svc = SearchService(db)

    # Monkeypatch vector similarity to return our services with scores
    def _fake_similar_by_embedding(embedding, limit=10, threshold=0.0):
        pairs = []
        if services:
            pairs.append((services[0], 0.92))
        if len(services) > 1:
            pairs.append((services[1], 0.88))
        return pairs

    monkeypatch.setattr(svc.catalog_repository, "find_similar_by_embedding", _fake_similar_by_embedding)

    # Use a query that avoids exact-text path so vector branch is used
    result = svc.search("zzzz", limit=5)
    meta = result.get("search_metadata", {})

    assert "observability_candidates" in meta
    obs = meta.get("observability_candidates") or []
    assert len(obs) >= 1
    assert {"position", "service_catalog_id", "score"}.issubset(obs[0].keys())

    # Persist through API to ensure full e2e path works
    payload = {
        "search_query": "zzzz",
        "search_type": "natural_language",
        "results_count": len(result.get("results", [])),
        "observability_candidates": obs,
    }
    r2 = client.post("/api/search-history/", json=payload, headers=_guest_headers())
    assert r2.status_code == 201, r2.text
    event_id = r2.json().get("search_event_id")
    rows = (
        db.query(SearchEventCandidate)
        .filter(SearchEventCandidate.search_event_id == event_id)
        .order_by(SearchEventCandidate.position)
        .all()
    )
    assert len(rows) == len(obs)
