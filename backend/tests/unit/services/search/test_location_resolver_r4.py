from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.models.location_alias import LocationAlias
import app.services.search.location_resolver as location_module
from app.services.search.location_resolver import LocationResolver, ResolvedLocation


@pytest.fixture
def mock_repo() -> Mock:
    repo = Mock()
    repo.find_exact_region_by_name.return_value = None
    repo.find_regions_by_name_fragment.return_value = []
    repo.find_best_fuzzy_region.return_value = (None, 0.0)
    repo.get_best_fuzzy_score.return_value = 1.0
    repo.find_trusted_alias.return_value = None
    repo.list_region_names.return_value = []
    repo.find_cached_alias.return_value = None
    repo.increment_alias_user_count = Mock()
    repo.get_regions_by_ids.return_value = []
    repo.get_region_by_id.return_value = None
    repo.db = Mock()
    return repo


@pytest.fixture
def mock_unresolved_repo() -> Mock:
    repo = Mock()
    repo.track_unresolved = Mock()
    return repo


@pytest.mark.asyncio
async def test_resolve_perf_finalize_early_return(monkeypatch, mock_repo: Mock, mock_unresolved_repo: Mock) -> None:
    resolver = LocationResolver(
        db=Mock(), repository=mock_repo, unresolved_repository=mock_unresolved_repo, region_code="nyc"
    )

    async def sync_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(location_module.asyncio, "to_thread", sync_to_thread)
    monkeypatch.setattr(location_module, "_PERF_LOG_ENABLED", True)
    monkeypatch.setattr(location_module, "_PERF_LOG_SLOW_MS", 999999)

    resolver._resolve_non_semantic = Mock(return_value=ResolvedLocation.from_not_found())

    result = await resolver.resolve("upper east side")
    assert result.not_found is True


@pytest.mark.asyncio
async def test_resolve_semantic_perf_metrics(monkeypatch, mock_repo: Mock, mock_unresolved_repo: Mock) -> None:
    resolver = LocationResolver(
        db=Mock(), repository=mock_repo, unresolved_repository=mock_unresolved_repo, region_code="nyc"
    )

    async def sync_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(location_module.asyncio, "to_thread", sync_to_thread)
    monkeypatch.setattr(location_module, "_PERF_LOG_ENABLED", True)
    monkeypatch.setattr(location_module, "_PERF_LOG_SLOW_MS", 0)

    resolver._resolve_non_semantic = Mock(return_value=None)
    resolver._tier4_embedding_match = AsyncMock(return_value=ResolvedLocation.from_not_found())
    resolver._tier5_llm_match = AsyncMock(return_value=ResolvedLocation.from_not_found())

    result = await resolver.resolve("madeup", enable_semantic=True)
    assert result.not_found is True


def test_resolve_sync_empty_and_short(monkeypatch, mock_repo: Mock, mock_unresolved_repo: Mock) -> None:
    resolver = LocationResolver(
        db=Mock(), repository=mock_repo, unresolved_repository=mock_unresolved_repo, region_code="nyc"
    )
    monkeypatch.setattr(location_module, "_PERF_LOG_ENABLED", True)
    monkeypatch.setattr(location_module, "_PERF_LOG_SLOW_MS", 999999)

    assert resolver.resolve_sync("").not_found is True
    assert resolver.resolve_sync("a").not_found is True


def test_alias_seed_resolved_not_found(monkeypatch, mock_repo: Mock, mock_unresolved_repo: Mock) -> None:
    resolver = LocationResolver(
        db=Mock(), repository=mock_repo, unresolved_repository=mock_unresolved_repo, region_code="nyc"
    )

    resolved_map = {
        "ues": {"alias": "ues", "region_name": "Upper East Side", "confidence": 0.9}
    }

    monkeypatch.setattr(location_module, "_load_location_alias_seed_maps", lambda *_: (resolved_map, {}))

    result = resolver._tier2_alias_lookup_from_seed_data("ues")
    assert result.not_found is True


def test_alias_seed_ambiguous_skips_empty_and_uses_fragments(monkeypatch, mock_repo: Mock) -> None:
    resolver = LocationResolver(db=Mock(), repository=mock_repo, region_code="nyc")

    ambiguous_map = {
        "x": {"alias": "x", "candidates": [None, "Upper East Side", "Upper West Side"]}
    }
    monkeypatch.setattr(location_module, "_load_location_alias_seed_maps", lambda *_: ({}, ambiguous_map))

    mock_repo.find_regions_by_name_fragment.return_value = [
        SimpleNamespace(id="r1", region_name="Upper East Side", parent_region="Manhattan"),
        SimpleNamespace(id="r2", region_name="Upper West Side", parent_region="Manhattan"),
    ]

    result = resolver._tier2_alias_lookup_from_seed_data("x")
    assert result.requires_clarification is True


def test_alias_seed_ambiguous_returns_not_found(monkeypatch, mock_repo: Mock) -> None:
    resolver = LocationResolver(db=Mock(), repository=mock_repo, region_code="nyc")

    ambiguous_map = {"x": {"alias": "x", "candidates": []}}
    monkeypatch.setattr(location_module, "_load_location_alias_seed_maps", lambda *_: ({}, ambiguous_map))

    result = resolver._tier2_alias_lookup_from_seed_data("x")
    assert result.not_found is True


def test_tier2_5_region_name_substring_candidates_empty(mock_repo: Mock) -> None:
    resolver = LocationResolver(db=Mock(), repository=mock_repo, region_code="nyc")
    mock_repo.find_regions_by_name_fragment.return_value = [
        SimpleNamespace(id=None, region_name="Upper East Side")
    ]

    result = resolver._tier2_5_region_name_substring("carnegie")
    assert result.not_found is True


@pytest.mark.asyncio
async def test_tier5_cached_alias_kind_none_falls_through(monkeypatch, mock_repo: Mock) -> None:
    resolver = LocationResolver(db=Mock(), repository=mock_repo, region_code="nyc")

    alias = SimpleNamespace(
        is_ambiguous=False,
        candidate_region_ids=None,
        is_resolved=False,
        region_boundary_id=None,
        confidence=0.5,
        user_count=0,
    )
    mock_repo.find_cached_alias.return_value = alias
    resolver.llm_service = SimpleNamespace(resolve=AsyncMock(return_value=None))

    async def sync_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(location_module.asyncio, "to_thread", sync_to_thread)

    result = await resolver._tier5_llm_match("downtown", original_query="downtown")
    assert result.not_found is True


@pytest.mark.asyncio
async def test_tier5_llm_skips_invalid_and_fallback_fragment(monkeypatch, mock_repo: Mock) -> None:
    resolver = LocationResolver(db=Mock(), repository=mock_repo, region_code="nyc")

    resolver.llm_service = SimpleNamespace(
        resolve=AsyncMock(return_value={"neighborhoods": [None, "", "Someplace"]})
    )
    mock_repo.find_exact_region_by_name.return_value = None
    mock_repo.find_regions_by_name_fragment.return_value = []

    async def sync_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(location_module.asyncio, "to_thread", sync_to_thread)

    result = await resolver._tier5_llm_match("query", original_query="query")
    assert result.not_found is True


@pytest.mark.asyncio
async def test_tier5_llm_cache_existing_alias_updates_fields(monkeypatch, mock_repo: Mock) -> None:
    resolver = LocationResolver(db=Mock(), repository=mock_repo, region_code="nyc")

    existing = LocationAlias(
        id="alias-1",
        city_id=resolver.city_id,
        alias_normalized="central park",
        source="manual",
        status="active",
        confidence=0.2,
        user_count=1,
        alias_type=None,
    )

    mock_repo.find_cached_alias.side_effect = [None, existing]
    mock_repo.list_region_names.return_value = ["central park"]
    mock_repo.find_exact_region_by_name.return_value = SimpleNamespace(
        id="region-1", region_name="Central Park", parent_region="Manhattan"
    )

    resolver.llm_service = SimpleNamespace(
        resolve=AsyncMock(return_value={"neighborhoods": ["Central Park"], "confidence": 0.8})
    )

    async def sync_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(location_module.asyncio, "to_thread", sync_to_thread)

    result = await resolver._tier5_llm_match("central park", original_query="central park")

    assert result.resolved is True
    assert existing.source == "llm"
    assert existing.status == "pending_review"
    assert existing.alias_type == "landmark"
    assert existing.confidence == 0.8


@pytest.mark.asyncio
async def test_tier5_llm_cache_exception_rolls_back(monkeypatch, mock_repo: Mock) -> None:
    resolver = LocationResolver(db=Mock(), repository=mock_repo, region_code="nyc")

    mock_repo.find_cached_alias.side_effect = [None, None]
    mock_repo.list_region_names.return_value = ["central park"]
    mock_repo.find_exact_region_by_name.return_value = SimpleNamespace(
        id="region-1", region_name="Central Park", parent_region="Manhattan"
    )
    mock_repo.db.flush.side_effect = Exception("fail")
    mock_repo.db.rollback.side_effect = Exception("rollback")

    resolver.llm_service = SimpleNamespace(
        resolve=AsyncMock(return_value={"neighborhoods": ["Central Park"], "confidence": 0.7})
    )

    async def sync_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(location_module.asyncio, "to_thread", sync_to_thread)

    result = await resolver._tier5_llm_match("central park", original_query="central park")
    assert result.resolved is True


@pytest.mark.asyncio
async def test_tier5_llm_returns_not_found_when_candidates_empty(monkeypatch, mock_repo: Mock) -> None:
    resolver = LocationResolver(db=Mock(), repository=mock_repo, region_code="nyc")

    mock_repo.find_cached_alias.return_value = None
    mock_repo.list_region_names.return_value = ["weird"]
    mock_repo.find_exact_region_by_name.return_value = SimpleNamespace(
        id="region-1", region_name=None, parent_region="Manhattan"
    )

    resolver.llm_service = SimpleNamespace(
        resolve=AsyncMock(return_value={"neighborhoods": ["Weird"], "confidence": 0.6})
    )

    async def sync_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(location_module.asyncio, "to_thread", sync_to_thread)

    result = await resolver._tier5_llm_match("weird", original_query="weird")
    assert result.not_found is True


def test_cache_llm_alias_exception_rolls_back(mock_repo: Mock) -> None:
    resolver = LocationResolver(db=Mock(), repository=mock_repo, region_code="nyc")

    mock_repo.db.flush.side_effect = Exception("fail")
    mock_repo.db.rollback.side_effect = Exception("rollback")

    resolver.cache_llm_alias("central park", ["region-1"], confidence=0.9)
