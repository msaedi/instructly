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


# ---------------------------------------------------------------------------
# Coverage recovery: _load_location_alias_seed_maps (lines 88, 94, 99)
# ---------------------------------------------------------------------------


def test_load_alias_seed_maps_skips_non_dict_entries(monkeypatch: pytest.MonkeyPatch) -> None:
    """Non-dict entries in aliases and ambiguous_aliases are silently skipped."""
    import json as _json

    payload = {
        "region_code": "nyc",
        "aliases": [
            "not_a_dict",
            42,
            {"alias": "ues", "region_name": "Upper East Side"},
        ],
        "ambiguous_aliases": [
            None,
            True,
            {"alias": "midtown", "candidates": ["Midtown East", "Midtown West"]},
        ],
    }

    fake_path = Mock()
    fake_path.read_text.return_value = _json.dumps(payload)

    location_module._load_location_alias_seed_maps.cache_clear()
    monkeypatch.setattr(location_module, "_LOCATION_ALIASES_JSON_PATH", fake_path)
    try:
        resolved, ambiguous = location_module._load_location_alias_seed_maps("nyc")
        assert "ues" in resolved
        assert "midtown" in ambiguous
        assert len(resolved) == 1
        assert len(ambiguous) == 1
    finally:
        location_module._load_location_alias_seed_maps.cache_clear()


# ---------------------------------------------------------------------------
# Coverage recovery: resolve() — fuzzy below embedding threshold (line 368)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_skips_tier4_when_fuzzy_below_threshold(
    monkeypatch: pytest.MonkeyPatch, mock_repo: Mock, mock_unresolved_repo: Mock
) -> None:
    """When fuzzy score is below MIN_FUZZY_FOR_EMBEDDING, Tier 4 is skipped."""
    resolver = LocationResolver(
        db=Mock(), repository=mock_repo, unresolved_repository=mock_unresolved_repo, region_code="nyc"
    )

    async def sync_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(location_module.asyncio, "to_thread", sync_to_thread)
    monkeypatch.setattr(location_module, "_PERF_LOG_ENABLED", False)

    # _resolve_non_semantic returns None so resolve() enters semantic path
    resolver._resolve_non_semantic = Mock(return_value=None)
    # Fuzzy score exists but below threshold
    mock_repo.get_best_fuzzy_score.return_value = 0.1
    resolver.MIN_FUZZY_FOR_EMBEDDING = 0.5

    # Tier 4 should NOT be called; Tier 5 falls through
    resolver._tier4_embedding_match = AsyncMock(return_value=ResolvedLocation.from_not_found())
    resolver._tier5_llm_match = AsyncMock(return_value=ResolvedLocation.from_not_found())

    result = await resolver.resolve("madeup", enable_semantic=True)
    assert result.not_found is True
    resolver._tier4_embedding_match.assert_not_called()


# ---------------------------------------------------------------------------
# Coverage recovery: resolve_sync._finalize slow path (line 413)
# ---------------------------------------------------------------------------


def test_resolve_sync_finalize_slow_path_logs(
    monkeypatch: pytest.MonkeyPatch, mock_repo: Mock, mock_unresolved_repo: Mock
) -> None:
    """When _PERF_LOG_SLOW_MS=0, the slow-path perf log fires."""
    resolver = LocationResolver(
        db=Mock(), repository=mock_repo, unresolved_repository=mock_unresolved_repo, region_code="nyc"
    )
    monkeypatch.setattr(location_module, "_PERF_LOG_ENABLED", True)
    monkeypatch.setattr(location_module, "_PERF_LOG_SLOW_MS", 0)

    result = resolver.resolve_sync("upper east side")
    # Just confirm it completes (the logger.info path is exercised)
    assert isinstance(result, ResolvedLocation)


# ---------------------------------------------------------------------------
# Coverage recovery: _tier2_alias_lookup fallback (lines 546, 555-556)
# ---------------------------------------------------------------------------


def test_tier2_alias_resolved_fallback_to_single_region(mock_repo: Mock) -> None:
    """When get_regions_by_ids returns [], falls back to get_region_by_id."""
    resolver = LocationResolver(db=Mock(), repository=mock_repo, region_code="nyc")

    alias = SimpleNamespace(
        is_ambiguous=False,
        is_resolved=True,
        region_boundary_id="r1",
        candidate_region_ids=["r1"],
        confidence=0.9,
        user_count=5,
    )
    mock_repo.find_trusted_alias.return_value = alias
    mock_repo.get_regions_by_ids.return_value = []
    mock_repo.get_region_by_id.return_value = SimpleNamespace(
        id="r1", region_name="Upper East Side", parent_region="Manhattan",
        display_name="Upper East Side", display_key="nyc-manhattan-upper-east-side",
    )
    mock_repo.get_regions_by_display_key.return_value = []

    result = resolver._tier2_alias_lookup("ues")
    mock_repo.get_region_by_id.assert_called_with("r1")
    assert result.resolved is True


def test_tier2_alias_resolved_with_supporting_regions_uses_display_label(mock_repo: Mock) -> None:
    resolver = LocationResolver(db=Mock(), repository=mock_repo, region_code="nyc")

    alias = SimpleNamespace(
        is_ambiguous=False,
        is_resolved=True,
        region_boundary_id="r1",
        candidate_region_ids=["r2"],
        confidence=0.9,
        user_count=5,
    )
    mock_repo.find_trusted_alias.return_value = alias
    mock_repo.get_regions_by_ids.return_value = [
        SimpleNamespace(
            id="r1",
            region_name="Upper East Side-Carnegie Hill",
            parent_region="Manhattan",
            display_name="Upper East Side",
            display_key="nyc-manhattan-upper-east-side",
        ),
        SimpleNamespace(
            id="r2",
            region_name="Upper East Side-Yorkville",
            parent_region="Manhattan",
            display_name="Upper East Side",
            display_key="nyc-manhattan-upper-east-side",
        ),
    ]

    result = resolver._tier2_alias_lookup("ues")

    assert result.resolved is True
    assert result.requires_clarification is False
    assert result.region_name == "Upper East Side"
    assert result.region_ids == ["r1", "r2"]


def test_tier2_alias_ambiguous_resolved_or_clarification(mock_repo: Mock) -> None:
    """Ambiguous alias with regions that produce a clarification result."""
    resolver = LocationResolver(db=Mock(), repository=mock_repo, region_code="nyc")

    alias = SimpleNamespace(
        is_ambiguous=True,
        is_resolved=False,
        region_boundary_id=None,
        candidate_region_ids=["r1", "r2"],
        confidence=0.8,
        user_count=3,
    )
    mock_repo.find_trusted_alias.return_value = alias
    mock_repo.get_regions_by_ids.return_value = [
        SimpleNamespace(id="r1", region_name="Midtown East", parent_region="Manhattan",
                        display_name="Midtown East", display_key="nyc-manhattan-midtown-east"),
        SimpleNamespace(id="r2", region_name="Midtown West", parent_region="Manhattan",
                        display_name="Midtown West", display_key="nyc-manhattan-midtown-west"),
    ]

    result = resolver._tier2_alias_lookup("midtown")
    assert result.resolved or result.requires_clarification


# ---------------------------------------------------------------------------
# Coverage recovery: _tier2_alias_lookup untrusted alias → not_found (line 569)
# ---------------------------------------------------------------------------


def test_tier2_alias_untrusted_returns_not_found(mock_repo: Mock) -> None:
    """When alias is neither ambiguous w/ candidates nor resolved w/ boundary_id, returns not_found."""
    resolver = LocationResolver(db=Mock(), repository=mock_repo, region_code="nyc")

    alias = SimpleNamespace(
        is_ambiguous=False,
        is_resolved=False,
        region_boundary_id=None,
        candidate_region_ids=None,
        confidence=0.3,
        user_count=1,
    )
    mock_repo.find_trusted_alias.return_value = alias

    result = resolver._tier2_alias_lookup("random")
    assert result.not_found is True


# ---------------------------------------------------------------------------
# Coverage recovery: _tier2_5_region_name_substring (lines 628, 641, 666)
# ---------------------------------------------------------------------------


def test_tier2_5_substring_filters_regions_without_id(mock_repo: Mock) -> None:
    """Regions without .id attribute are filtered out (line 628 in seed data variant)."""
    resolver = LocationResolver(db=Mock(), repository=mock_repo, region_code="nyc")
    mock_repo.find_regions_by_name_fragment.return_value = [
        SimpleNamespace(id="r1", region_name="Carnegie Hill", parent_region="Manhattan",
                        display_name="Upper East Side", display_key="nyc-manhattan-ues"),
        SimpleNamespace(id=None, region_name="NoId Place", parent_region="Manhattan",
                        display_name=None, display_key=None),
    ]

    result = resolver._tier2_5_region_name_substring("carnegie")
    assert result.resolved is True


def test_tier2_5_substring_truncates_to_5_candidates(mock_repo: Mock) -> None:
    """>5 candidates get sorted by name length and truncated."""
    resolver = LocationResolver(db=Mock(), repository=mock_repo, region_code="nyc")
    regions = [
        SimpleNamespace(
            id=f"r{i}", region_name=f"Area {'X' * (i + 5)}", parent_region="Manhattan",
            display_name=f"Area {'X' * (i + 5)}", display_key=f"dk{i}",
        )
        for i in range(8)
    ]
    mock_repo.find_regions_by_name_fragment.return_value = regions

    result = resolver._tier2_5_region_name_substring("area x")
    assert result.requires_clarification is True
    assert len(result.candidates) <= 5


# ---------------------------------------------------------------------------
# Coverage recovery: _tier5_llm_match cached paths (lines 753-754, 769, 783)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tier5_cached_ambiguous_returns_clarification(monkeypatch: pytest.MonkeyPatch, mock_repo: Mock) -> None:
    """Cached ambiguous alias with regions builds clarification result."""
    resolver = LocationResolver(db=Mock(), repository=mock_repo, region_code="nyc")

    cached = SimpleNamespace(
        is_ambiguous=True,
        candidate_region_ids=["r1", "r2"],
        is_resolved=False,
        region_boundary_id=None,
        confidence=0.7,
        user_count=2,
    )
    mock_repo.find_cached_alias.return_value = cached
    mock_repo.get_regions_by_ids.return_value = [
        SimpleNamespace(id="r1", region_name="Midtown East", parent_region="Manhattan",
                        display_name="Midtown East", display_key="dk1"),
        SimpleNamespace(id="r2", region_name="Midtown West", parent_region="Manhattan",
                        display_name="Midtown West", display_key="dk2"),
    ]

    async def sync_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(location_module.asyncio, "to_thread", sync_to_thread)

    result = await resolver._tier5_llm_match("midtown", original_query="midtown")
    assert result.requires_clarification is True


@pytest.mark.asyncio
async def test_tier5_cached_resolved_with_fallback_region(monkeypatch: pytest.MonkeyPatch, mock_repo: Mock) -> None:
    """Cached resolved alias where batch fetch is empty, falls back to single region."""
    resolver = LocationResolver(db=Mock(), repository=mock_repo, region_code="nyc")

    cached = SimpleNamespace(
        is_ambiguous=False,
        candidate_region_ids=["r1"],
        is_resolved=True,
        region_boundary_id="r1",
        confidence=0.85,
        user_count=10,
    )
    mock_repo.find_cached_alias.return_value = cached
    mock_repo.get_regions_by_ids.return_value = []
    mock_repo.get_region_by_id.return_value = SimpleNamespace(
        id="r1", region_name="Central Park", parent_region="Manhattan",
        display_name="Central Park", display_key="nyc-manhattan-central-park",
    )
    mock_repo.get_regions_by_display_key.return_value = []

    async def sync_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(location_module.asyncio, "to_thread", sync_to_thread)

    result = await resolver._tier5_llm_match("central park", original_query="central park")
    assert result.resolved is True


# ---------------------------------------------------------------------------
# Coverage recovery: _format_candidates — no parent_region fallback (line 935)
# ---------------------------------------------------------------------------


def test_format_candidates_falls_back_to_borough_attr() -> None:
    """When parent_region is None, falls back to .borough attribute."""
    region = SimpleNamespace(
        id="r1", region_name="Test Area", parent_region=None,
        borough="Brooklyn", display_name=None, display_key=None,
    )
    candidates = LocationResolver._format_candidates([region])
    assert len(candidates) == 1
    assert candidates[0]["borough"] == "Brooklyn"


# ---------------------------------------------------------------------------
# Coverage recovery: _candidate_region_ids (line 971)
# ---------------------------------------------------------------------------


def test_candidate_region_ids_returns_deduped_list() -> None:
    """Non-empty region_ids list is deduped and returned."""
    candidate = {"region_id": "r1", "region_ids": ["r2", "r1", "r2"]}
    ids = LocationResolver._candidate_region_ids(candidate)
    assert ids == ["r1", "r2"]


# ---------------------------------------------------------------------------
# Coverage recovery: _expand_regions_for_logical_resolution (lines 1000-1002)
# ---------------------------------------------------------------------------


def test_expand_regions_uses_region_lookup(mock_repo: Mock) -> None:
    """Single region with display_key found in _region_lookup.by_display_key → expanded."""
    resolver = LocationResolver(db=Mock(), repository=mock_repo, region_code="nyc")

    region = SimpleNamespace(
        id="r1", region_name="Upper East Side", parent_region="Manhattan",
        display_name="Upper East Side", display_key="dk-ues",
    )
    expanded_region = SimpleNamespace(
        id="r2", region_name="Upper East Side-Yorkville", parent_region="Manhattan",
        display_name="Upper East Side", display_key="dk-ues",
    )
    resolver._region_lookup = SimpleNamespace(
        by_display_key={"dk-ues": [region, expanded_region]}
    )

    result = resolver._expand_regions_for_logical_resolution([region])
    assert len(result) == 2


# ---------------------------------------------------------------------------
# Coverage recovery: _prefer_exact_logical_candidates (line 1050)
# ---------------------------------------------------------------------------


def test_prefer_exact_raw_returns_single_match() -> None:
    """When exactly one candidate matches raw region_name, it's preferred."""
    candidates = [
        {"region_id": "r1", "region_name": "Upper East Side", "display_name": "UES", "borough": "Manhattan"},
        {"region_id": "r2", "region_name": "Upper West Side", "display_name": "UWS", "borough": "Manhattan"},
    ]
    result = LocationResolver._prefer_exact_logical_candidates("upper east side", candidates)
    assert len(result) == 1
    assert result[0]["region_id"] == "r1"


# ---------------------------------------------------------------------------
# Coverage recovery: effective_region_ids (line 1060)
# ---------------------------------------------------------------------------


def test_effective_region_ids_from_region_ids_list() -> None:
    """When location_resolution has region_ids, returns deduped sorted list."""
    loc = ResolvedLocation(
        resolved=True,
        region_id=None,
        region_name="Test",
        borough=None,
        region_ids=["r2", "r1", "r2"],
    )
    ids = LocationResolver.effective_region_ids(loc)
    assert ids == ["r1", "r2"]


# ---------------------------------------------------------------------------
# Coverage recovery: _dedupe_candidates_by_display (lines 1113-1142)
# ---------------------------------------------------------------------------


def test_dedupe_candidates_non_numeric_similarity() -> None:
    """Non-numeric similarity values are coerced to 0.0."""
    candidates = [
        {"region_id": "r1", "region_name": "Area A", "display_key": "dk1",
         "display_name": "Area A", "borough": "Manhattan", "similarity": "not_a_number"},
    ]
    result = LocationResolver._dedupe_candidates_by_display(candidates)
    assert len(result) == 1
    assert result[0]["similarity"] == 0.0


def test_dedupe_candidates_merges_display_name_and_borough() -> None:
    """Duplicate display_key: first entry missing display_name/borough, second has them."""
    candidates = [
        {"region_id": "r1", "region_name": "Area A", "display_key": "dk1",
         "display_name": None, "borough": None},
        {"region_id": "r2", "region_name": "Area A-Sub", "display_key": "dk1",
         "display_name": "Area A", "borough": "Manhattan"},
    ]
    result = LocationResolver._dedupe_candidates_by_display(candidates)
    assert len(result) == 1
    assert result[0]["display_name"] == "Area A"
    assert result[0]["borough"] == "Manhattan"


def test_dedupe_candidates_higher_similarity_wins() -> None:
    """Duplicate display_key with increasing similarity: higher value wins."""
    candidates = [
        {"region_id": "r1", "region_name": "Area A", "display_key": "dk1",
         "display_name": "Area A", "borough": "Manhattan", "similarity": 0.3},
        {"region_id": "r2", "region_name": "Area A-Sub", "display_key": "dk1",
         "display_name": "Area A", "borough": "Manhattan", "similarity": 0.9},
    ]
    result = LocationResolver._dedupe_candidates_by_display(candidates)
    assert len(result) == 1
    assert result[0]["similarity"] == 0.9


def test_alias_seed_ambiguous_non_list_candidates_returns_not_found(
    monkeypatch: pytest.MonkeyPatch, mock_repo: Mock
) -> None:
    """When ambiguous alias 'candidates' is not a list → from_not_found (line 641)."""
    resolver = LocationResolver(db=Mock(), repository=mock_repo, region_code="nyc")

    ambiguous_map = {"x": {"alias": "x", "candidates": "not_a_list"}}
    monkeypatch.setattr(location_module, "_load_location_alias_seed_maps", lambda *_: ({}, ambiguous_map))

    result = resolver._tier2_alias_lookup_from_seed_data("x")
    assert result.not_found is True


def test_dedupe_candidates_existing_similarity_malformed() -> None:
    """Existing entry has malformed similarity, new entry has valid — handles gracefully."""
    candidates = [
        {"region_id": "r1", "region_name": "Area A", "display_key": "dk1",
         "display_name": "Area A", "borough": "Manhattan", "similarity": "bad"},
        {"region_id": "r2", "region_name": "Area A-Sub", "display_key": "dk1",
         "display_name": "Area A", "borough": "Manhattan", "similarity": 0.7},
    ]
    result = LocationResolver._dedupe_candidates_by_display(candidates)
    assert len(result) == 1
    assert result[0]["similarity"] == 0.7
