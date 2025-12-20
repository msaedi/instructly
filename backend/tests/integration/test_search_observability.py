# backend/tests/integration/test_search_observability.py
"""
Integration tests for search observability and candidate persistence.

Covers:
- Persisting top-N candidates when provided to /api/search-history
"""

from typing import Dict, List

from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm import Session

from app.models.search_event import SearchEventCandidate
from app.models.service_catalog import ServiceCatalog


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

    resp = client.post("/api/v1/search-history/", json=payload, headers=_guest_headers())
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
