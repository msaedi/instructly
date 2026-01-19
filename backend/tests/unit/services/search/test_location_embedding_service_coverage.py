from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.models.region_boundary import RegionBoundary
from app.services.search import location_embedding_service as les_module
from app.services.search.location_embedding_service import LocationEmbeddingService


class _RepoStub:
    def __init__(self) -> None:
        self._has_embeddings = True
        self._pairs: list[tuple[RegionBoundary, float]] = []

    def has_region_name_embeddings(self) -> bool:
        return self._has_embeddings

    def find_regions_by_name_embedding(self, embedding, limit: int = 5):
        return self._pairs[:limit]


def _make_region(region_id: str, name: str, borough: str) -> RegionBoundary:
    region = RegionBoundary(region_type="nyc", region_code="TEST", region_name=name)
    region.id = region_id
    region.parent_region = borough
    return region


@pytest.mark.asyncio
async def test_get_candidates_filters_and_requires_api_key(monkeypatch) -> None:
    repo = _RepoStub()
    service = LocationEmbeddingService(repository=repo)

    region = _make_region("RID-1", "Upper East Side", "Manhattan")
    repo._pairs = [(region, 0.9), (region, 0.5)]

    monkeypatch.setenv("OPENAI_API_KEY", "test")
    service._embed_location_text = AsyncMock(return_value=[0.1] * 1536)

    candidates = await service.get_candidates("Upper East Side", threshold=0.8)
    assert len(candidates) == 1
    assert candidates[0]["region_id"] == "RID-1"

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    candidates = await service.get_candidates("Upper East Side")
    assert candidates == []


@pytest.mark.asyncio
async def test_get_candidates_handles_blank_and_missing_embeddings(monkeypatch) -> None:
    repo = _RepoStub()
    repo._has_embeddings = False
    service = LocationEmbeddingService(repository=repo)

    monkeypatch.setenv("OPENAI_API_KEY", "test")
    assert await service.get_candidates("   ") == []
    assert await service.get_candidates("midtown") == []


def test_pick_best_or_ambiguous() -> None:
    candidates = [
        {"region_id": "1", "similarity": 0.9},
        {"region_id": "2", "similarity": 0.85},
    ]
    best, ambiguous = LocationEmbeddingService.pick_best_or_ambiguous(candidates)
    assert best is None
    assert ambiguous is not None

    candidates = [
        {"region_id": "1", "similarity": 0.95},
        {"region_id": "2", "similarity": 0.7},
    ]
    best, ambiguous = LocationEmbeddingService.pick_best_or_ambiguous(candidates)
    assert best is not None
    assert best["region_id"] == "1"
    assert ambiguous is None


def test_build_candidates_from_embeddings() -> None:
    query_embedding = [1.0, 0.0]
    region_embeddings = [
        {
            "region_id": "RID-1",
            "region_name": "SoHo",
            "borough": "Manhattan",
            "embedding": [1.0, 0.0],
            "norm": 1.0,
        },
        {
            "region_id": "RID-2",
            "region_name": "Queens",
            "borough": "Queens",
            "embedding": [0.0, 1.0],
            "norm": 1.0,
        },
    ]

    candidates = LocationEmbeddingService.build_candidates_from_embeddings(
        query_embedding,
        region_embeddings,
        limit=2,
        threshold=0.8,
    )

    assert len(candidates) == 1
    assert candidates[0]["region_id"] == "RID-1"


@pytest.mark.asyncio
async def test_embed_location_text_returns_none_on_error(monkeypatch) -> None:
    service = LocationEmbeddingService(repository=_RepoStub())
    dummy_client = SimpleNamespace(embeddings=SimpleNamespace(create=AsyncMock(side_effect=RuntimeError("boom"))))
    service._client = dummy_client

    result = await service.embed_location_text("midtown")
    assert result is None


def test_client_recreates_when_retry_count_changes(monkeypatch) -> None:
    class DummyOpenAI:
        def __init__(self, timeout: float, max_retries: int) -> None:
            self.timeout = timeout
            self.max_retries = max_retries
            self.embeddings = SimpleNamespace(create=AsyncMock())

    cfg = SimpleNamespace(max_retries=1)
    monkeypatch.setattr(les_module, "AsyncOpenAI", DummyOpenAI)
    monkeypatch.setattr(les_module, "get_search_config", lambda: cfg)

    service = LocationEmbeddingService(repository=_RepoStub())
    client_first = service.client
    assert client_first.max_retries == 1

    cfg.max_retries = 3
    client_second = service.client
    assert client_second.max_retries == 3
    assert client_second is not client_first
