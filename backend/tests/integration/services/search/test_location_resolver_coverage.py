from __future__ import annotations

import json
import secrets
from types import SimpleNamespace

import pytest

from app.domain.neighborhood_config import NEIGHBORHOOD_MAPPING, generate_display_key
from app.models.location_alias import NYC_CITY_ID, LocationAlias
from app.models.region_boundary import RegionBoundary
import app.services.search.location_resolver as resolver_module
from app.services.search.location_resolver import LocationResolver, ResolutionTier, ResolvedLocation


def _build_consolidated_display_cases() -> list[object]:
    grouped: dict[str, dict[str, object]] = {}
    for (borough, raw_name), display_name in NEIGHBORHOOD_MAPPING.items():
        if display_name is None:
            continue
        display_key = generate_display_key("nyc", borough, display_name)
        bucket = grouped.setdefault(
            display_key,
            {"display_name": display_name, "raw_names": []},
        )
        raw_names = bucket["raw_names"]
        if isinstance(raw_names, list):
            raw_names.append(raw_name)

    return [
        pytest.param(
            display_key,
            str(payload["display_name"]),
            sorted(str(name) for name in payload["raw_names"]),
            id=display_key,
        )
        for display_key, payload in sorted(grouped.items())
        if len(payload["raw_names"]) > 1
    ]


CONSOLIDATED_DISPLAY_CASES = _build_consolidated_display_cases()
assert len(CONSOLIDATED_DISPLAY_CASES) == 19


def _create_region(
    db,
    *,
    name: str,
    parent: str | None = "Manhattan",
    region_code: str | None = None,
    display_name: str | None = None,
    display_key: str | None = None,
) -> RegionBoundary:
    existing = (
        db.query(RegionBoundary)
        .filter(RegionBoundary.region_type == "nyc", RegionBoundary.region_name == name)
        .first()
    )
    if existing:
        return existing
    if region_code is None:
        region_code = f"test-{secrets.token_hex(4)}"
    region = RegionBoundary(
        region_type="nyc",
        region_code=region_code,
        region_name=name,
        parent_region=parent,
        display_name=display_name,
        display_key=display_key,
    )
    db.add(region)
    db.flush()
    return region


def _create_alias(
    db,
    *,
    alias: str,
    region_id: str | None = None,
    candidate_ids: list[str] | None = None,
    source: str = "manual",
    status: str = "active",
    confidence: float = 1.0,
) -> LocationAlias:
    alias_row = LocationAlias(
        city_id=NYC_CITY_ID,
        alias_normalized=alias,
        region_boundary_id=region_id,
        requires_clarification=bool(candidate_ids),
        candidate_region_ids=candidate_ids,
        source=source,
        status=status,
        confidence=confidence,
        user_count=1,
    )
    db.add(alias_row)
    db.flush()
    return alias_row


def test_load_location_alias_seed_maps_handles_missing_and_invalid_json(monkeypatch):
    resolver_module._load_location_alias_seed_maps.cache_clear()

    def _raise_not_found(*_args, **_kwargs):
        raise FileNotFoundError("missing")

    monkeypatch.setattr(
        resolver_module,
        "_LOCATION_ALIASES_JSON_PATH",
        SimpleNamespace(read_text=_raise_not_found),
    )
    resolved, ambiguous = resolver_module._load_location_alias_seed_maps("nyc")
    assert resolved == {}
    assert ambiguous == {}

    resolver_module._load_location_alias_seed_maps.cache_clear()

    def _raise_value(*_args, **_kwargs):
        raise ValueError("bad json")

    monkeypatch.setattr(
        resolver_module,
        "_LOCATION_ALIASES_JSON_PATH",
        SimpleNamespace(read_text=_raise_value),
    )
    resolved, ambiguous = resolver_module._load_location_alias_seed_maps("nyc")
    assert resolved == {}
    assert ambiguous == {}


def test_load_location_alias_seed_maps_filters_rows(monkeypatch):
    resolver_module._load_location_alias_seed_maps.cache_clear()
    payload = {
        "region_code": "nyc",
        "aliases": [
            {"alias": "UES", "region_name": "Upper East Side"},
            "bad",
            {"alias": None},
        ],
        "ambiguous_aliases": [
            {"alias": "midtown", "candidates": ["Midtown East", "Midtown West"]},
            {"alias": ""},
        ],
    }
    monkeypatch.setattr(
        resolver_module,
        "_LOCATION_ALIASES_JSON_PATH",
        SimpleNamespace(read_text=lambda *_args, **_kwargs: json.dumps(payload)),
    )
    resolved, ambiguous = resolver_module._load_location_alias_seed_maps("nyc")
    assert "ues" in resolved
    assert "midtown" in ambiguous


def test_load_location_alias_seed_maps_wrong_region(monkeypatch):
    resolver_module._load_location_alias_seed_maps.cache_clear()
    payload = {"region_code": "la", "aliases": [], "ambiguous_aliases": []}
    monkeypatch.setattr(
        resolver_module,
        "_LOCATION_ALIASES_JSON_PATH",
        SimpleNamespace(read_text=lambda *_args, **_kwargs: json.dumps(payload)),
    )
    resolved, ambiguous = resolver_module._load_location_alias_seed_maps("nyc")
    assert resolved == {}
    assert ambiguous == {}


def test_resolved_location_kind_variants():
    resolved = ResolvedLocation.from_region(
        region_id="region-1",
        region_name="Test",
        borough="Manhattan",
        tier=ResolutionTier.EXACT,
        confidence=1.0,
    )
    assert resolved.kind == "region"

    borough = ResolvedLocation.from_borough(
        borough="Brooklyn",
        tier=ResolutionTier.EXACT,
        confidence=1.0,
    )
    assert borough.kind == "borough"

    ambiguous = ResolvedLocation.from_ambiguous(
        candidates=[{"region_id": "r1", "region_name": "A", "borough": "Manhattan"}],
        tier=ResolutionTier.ALIAS,
        confidence=0.5,
    )
    assert ambiguous.kind == "none"

    not_found = ResolvedLocation.from_not_found()
    assert not_found.kind == "none"


def test_resolve_sync_borough_and_exact_region(db):
    resolver = LocationResolver(db)
    borough = resolver.resolve_sync("bk")
    assert borough.borough == "Brooklyn"
    assert borough.tier == ResolutionTier.ALIAS

    region = _create_region(db, name="SoHo")
    exact = resolver.resolve_sync("soho")
    assert exact.region_id == region.id
    assert exact.tier == ResolutionTier.EXACT


def test_tier1_exact_match_borough(db):
    resolver = LocationResolver(db)
    borough = resolver._tier1_exact_match("brooklyn")
    assert borough.resolved is True
    assert borough.borough == "Brooklyn"
    assert borough.tier == ResolutionTier.EXACT


def test_resolve_sync_alias_resolved_and_ambiguous(db):
    resolver = LocationResolver(db)
    region_one = _create_region(db, name="Tribeca")
    region_two = _create_region(db, name="Midtown East")
    region_three = _create_region(db, name="Midtown West")

    _create_alias(db, alias="tri", region_id=region_one.id)
    _create_alias(
        db,
        alias="midtown",
        candidate_ids=[region_two.id, region_three.id],
        source="manual",
        status="active",
    )

    resolved = resolver.resolve_sync("tri")
    assert resolved.region_id == region_one.id
    assert resolved.tier == ResolutionTier.ALIAS

    ambiguous = resolver.resolve_sync("midtown")
    assert ambiguous.requires_clarification is True
    assert ambiguous.tier == ResolutionTier.ALIAS
    assert ambiguous.candidates and len(ambiguous.candidates) >= 2


def test_normalize_strips_wrappers_and_direction(db):
    resolver = LocationResolver(db)
    assert resolver._normalize("near Central Park North") == "central park"
    assert resolver._normalize("in Tribeca area") == "tribeca"


def test_tier2_5_substring_and_tier3_fuzzy(db):
    resolver = LocationResolver(db)
    _create_region(db, name="Upper East Side-Carnegie Hill")
    _create_region(db, name="Upper East Side-Yorkville")

    substring = resolver._tier2_5_region_name_substring("carnegie")
    assert substring.resolved is True
    assert substring.tier == ResolutionTier.FUZZY

    _create_region(db, name="Chelsea")
    fuzzy = resolver._tier3_fuzzy_match("chelsea")
    assert fuzzy.resolved is True
    assert fuzzy.tier == ResolutionTier.FUZZY


def test_expand_regions_for_logical_resolution_without_display_key_returns_original_region(db):
    resolver = LocationResolver(db)
    region = _create_region(db, name="Single Region", display_name=None, display_key=None)

    expanded = resolver._expand_regions_for_logical_resolution([region])

    assert expanded == [region]


def test_effective_region_ids_filters_empty_values():
    resolution = ResolvedLocation.from_region(
        region_id="region-1",
        region_name="Upper East Side",
        borough="Manhattan",
        region_ids=["region-2", "", None, "region-1"],  # type: ignore[list-item]
        tier=ResolutionTier.ALIAS,
        confidence=1.0,
    )

    assert LocationResolver.effective_region_ids(resolution) == ["region-1", "region-2"]


def test_tier2_5_substring_short_and_exact_logical_match_wins(db):
    resolver = LocationResolver(db)
    short = resolver._tier2_5_region_name_substring("ny")
    assert short.not_found is True

    _create_region(db, name="Midtown East")
    _create_region(db, name="Midtown West")
    candidates = resolver._format_candidates(
        resolver.repository.find_regions_by_name_fragment("midtown")
    )
    deduped = LocationResolver._dedupe_candidates_by_display(candidates)
    preferred = LocationResolver._prefer_exact_logical_candidates("midtown", deduped)

    assert len(preferred) == 1
    assert preferred[0]["display_name"] == "Midtown"
    assert preferred[0]["display_key"] == "nyc-manhattan-midtown"

    resolved = resolver._tier2_5_region_name_substring("midtown")
    assert resolved.resolved is True
    assert resolved.requires_clarification is False
    assert resolved.region_name == "Midtown"


def test_tier3_fuzzy_match_not_found(db, monkeypatch):
    resolver = LocationResolver(db)

    def _no_match(*_args, **_kwargs):
        return None, None

    monkeypatch.setattr(resolver.repository, "find_best_fuzzy_region", _no_match)
    result = resolver._tier3_fuzzy_match("unknown")
    assert result.not_found is True


@pytest.mark.asyncio
async def test_tier4_embedding_match_best_and_ambiguous(db):
    resolver = LocationResolver(db)

    class BestEmbedding:
        async def get_candidates(self, _normalized: str, limit: int = 5):
            return [{"region_id": "r1", "region_name": "Best Region", "similarity": 0.9}]

        def pick_best_or_ambiguous(self, candidates):
            return candidates[0], None

    resolver.embedding_service = BestEmbedding()
    best = await resolver._tier4_embedding_match("best")
    assert best.resolved is True
    assert best.tier == ResolutionTier.EMBEDDING

    class AmbiguousEmbedding:
        async def get_candidates(self, _normalized: str, limit: int = 5):
            return [
                {"region_id": "r2", "region_name": "Region A", "similarity": 0.8},
                {"region_id": "r3", "region_name": "Region B", "similarity": 0.79},
            ]

        def pick_best_or_ambiguous(self, candidates):
            return None, candidates

    resolver.embedding_service = AmbiguousEmbedding()
    ambiguous = await resolver._tier4_embedding_match("ambiguous")
    assert ambiguous.requires_clarification is True
    assert ambiguous.tier == ResolutionTier.EMBEDDING


@pytest.mark.asyncio
async def test_tier4_embedding_match_invalid_rows(db):
    resolver = LocationResolver(db)

    class BadEmbedding:
        async def get_candidates(self, _normalized: str, limit: int = 5):
            return [
                {"region_id": None, "region_name": None, "similarity": 0.5},
                {"region_id": "r1", "region_name": None, "similarity": 0.4},
            ]

        def pick_best_or_ambiguous(self, candidates):
            return None, candidates

    resolver.embedding_service = BadEmbedding()
    result = await resolver._tier4_embedding_match("bad")
    assert result.not_found is True


@pytest.mark.asyncio
async def test_tier5_llm_match_cached_ambiguous(db, monkeypatch):
    resolver = LocationResolver(db)
    region_a = _create_region(db, name="Union Square")
    region_b = _create_region(db, name="Times Square")
    _create_alias(
        db,
        alias="landmark",
        candidate_ids=[region_a.id, region_b.id],
        source="llm",
        status="pending_review",
    )

    async def _unused_resolve(**_kwargs):
        return {"neighborhoods": []}

    monkeypatch.setattr(resolver.llm_service, "resolve", _unused_resolve)
    result = await resolver._tier5_llm_match("landmark", original_query="landmark")
    assert result.requires_clarification is True
    assert result.tier == ResolutionTier.LLM


@pytest.mark.asyncio
async def test_tier5_llm_match_resolved_and_cached(db):
    resolver = LocationResolver(db)
    _create_region(db, name="Central Park")

    async def _resolve(**_kwargs):
        return {"neighborhoods": ["Central Park"], "confidence": 0.9}

    resolver.llm_service.resolve = _resolve

    result = await resolver._tier5_llm_match("central park", original_query="Central Park")
    assert result.resolved is True
    assert result.region_name == "Central Park"
    assert result.tier == ResolutionTier.LLM

    cached = (
        db.query(LocationAlias)
        .filter(LocationAlias.alias_normalized == "central park", LocationAlias.source == "llm")
        .first()
    )
    assert cached is not None


@pytest.mark.asyncio
async def test_tier5_llm_match_cached_resolved(db):
    resolver = LocationResolver(db)
    region = _create_region(db, name="Battery Park")
    _create_alias(db, alias="battery", region_id=region.id, source="llm", status="pending_review")

    result = await resolver._tier5_llm_match("battery", original_query="battery")
    assert result.resolved is True
    assert result.region_id == region.id


@pytest.mark.asyncio
async def test_tier5_llm_match_caches_ambiguous(db):
    resolver = LocationResolver(db)
    region_a = _create_region(db, name="East Village")
    region_b = _create_region(db, name="West Village")

    async def _resolve(**_kwargs):
        return {"neighborhoods": ["East Village", "West Village"], "confidence": 0.7}

    resolver.llm_service.resolve = _resolve
    result = await resolver._tier5_llm_match("village", original_query="village")
    assert result.requires_clarification is True

    cached = (
        db.query(LocationAlias)
        .filter(LocationAlias.alias_normalized == "village", LocationAlias.source == "llm")
        .first()
    )
    assert cached is not None
    assert cached.requires_clarification is True
    assert cached.candidate_region_ids is not None
    assert str(region_a.id) in cached.candidate_region_ids
    assert str(region_b.id) in cached.candidate_region_ids


def test_tier2_alias_lookup_from_seed_data_resolved_and_ambiguous(db, monkeypatch):
    resolver = LocationResolver(db)
    region = _create_region(db, name="Upper West Side")
    _create_region(db, name="East Village")
    _create_region(db, name="West Village")

    payload = {
        "region_code": "nyc",
        "aliases": [{"alias": "uws", "region_name": "Upper West Side", "confidence": 0.8}],
        "ambiguous_aliases": [
            {
                "alias": "village",
                "candidates": ["East Village", "West Village"],
                "confidence": 0.6,
            }
        ],
    }
    resolver_module._load_location_alias_seed_maps.cache_clear()
    monkeypatch.setattr(
        resolver_module,
        "_LOCATION_ALIASES_JSON_PATH",
        SimpleNamespace(read_text=lambda *_args, **_kwargs: json.dumps(payload)),
    )

    resolved = resolver._tier2_alias_lookup_from_seed_data("uws")
    assert resolved.resolved is True
    assert resolved.region_id == region.id

    ambiguous = resolver._tier2_alias_lookup_from_seed_data("village")
    assert ambiguous.requires_clarification is True
    assert ambiguous.tier == ResolutionTier.ALIAS
    assert ambiguous.candidates and len(ambiguous.candidates) >= 2


def test_tier2_alias_lookup_from_seed_data_fragment_and_single_candidate(db, monkeypatch):
    resolver = LocationResolver(db)
    _create_region(db, name="Upper East Side-Carnegie Hill")
    only_region = _create_region(db, name="Battery Park City")

    payload = {
        "region_code": "nyc",
        "aliases": [{"alias": "carnegie", "region_name": "Carnegie", "confidence": 0.8}],
        "ambiguous_aliases": [{"alias": "battery", "candidates": ["Battery Park City"]}],
    }
    resolver_module._load_location_alias_seed_maps.cache_clear()
    monkeypatch.setattr(
        resolver_module,
        "_LOCATION_ALIASES_JSON_PATH",
        SimpleNamespace(read_text=lambda *_args, **_kwargs: json.dumps(payload)),
    )

    fragment_match = resolver._tier2_alias_lookup_from_seed_data("carnegie")
    assert fragment_match.resolved is True
    assert fragment_match.tier == ResolutionTier.ALIAS

    single_candidate = resolver._tier2_alias_lookup_from_seed_data("battery")
    assert single_candidate.resolved is True
    assert single_candidate.region_id == only_region.id


def test_tier2_alias_lookup_single_candidate_resolves(db):
    resolver = LocationResolver(db)
    region = _create_region(db, name="SoHo")
    _create_alias(db, alias="solo", candidate_ids=[region.id], source="manual", status="active")
    result = resolver._tier2_alias_lookup("solo")
    assert result.resolved is True
    assert result.region_id == region.id
    assert result.region_ids == [region.id]


@pytest.mark.asyncio
async def test_resolve_tracks_unresolved(monkeypatch, db):
    resolver = LocationResolver(db)
    calls: list[tuple[str, str | None]] = []

    class DummyUnresolved:
        def track_unresolved(self, normalized, *, original_query=None):
            calls.append((normalized, original_query))

    resolver.unresolved_repository = DummyUnresolved()
    monkeypatch.setattr(resolver, "_resolve_non_semantic", lambda *_args, **_kwargs: None)

    result = await resolver.resolve("Unknown Place", track_unresolved=True)
    assert result.not_found is True
    assert calls


@pytest.mark.asyncio
async def test_resolve_empty_and_short_inputs(db):
    resolver = LocationResolver(db)
    empty = await resolver.resolve("")
    short = await resolver.resolve("a")
    assert empty.not_found is True
    assert short.not_found is True


@pytest.mark.asyncio
async def test_resolve_semantic_gated_and_llm_none(monkeypatch, db):
    resolver = LocationResolver(db)
    monkeypatch.setattr(resolver, "_resolve_non_semantic", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(resolver.repository, "get_best_fuzzy_score", lambda *_args, **_kwargs: 0.0)

    async def _resolve(**_kwargs):
        return None

    resolver.llm_service.resolve = _resolve
    result = await resolver.resolve("madeupplace", enable_semantic=True)
    assert result.not_found is True


@pytest.mark.asyncio
async def test_resolve_semantic_embedding_short_circuit(monkeypatch, db):
    resolver = LocationResolver(db)
    monkeypatch.setattr(resolver, "_resolve_non_semantic", lambda *_args, **_kwargs: None)

    async def _tier4(_normalized: str):
        return resolver_module.ResolvedLocation.from_region(
            region_id="region-1",
            region_name="Central Park",
            borough="Manhattan",
            tier=ResolutionTier.EMBEDDING,
            confidence=0.9,
        )

    monkeypatch.setattr(resolver, "_tier4_embedding_match", _tier4)
    result = await resolver.resolve("central park", enable_semantic=True)
    assert result.resolved is True
    assert result.tier == ResolutionTier.EMBEDDING


@pytest.mark.asyncio
async def test_resolve_perf_logging(monkeypatch, db):
    resolver = LocationResolver(db)
    monkeypatch.setattr(resolver_module, "_PERF_LOG_ENABLED", True)
    monkeypatch.setattr(resolver_module, "_PERF_LOG_SLOW_MS", 0)
    result = await resolver.resolve("unknownplace", enable_semantic=False)
    assert result.not_found is True


def test_resolve_sync_tracks_unresolved(monkeypatch, db):
    resolver = LocationResolver(db)
    calls: list[tuple[str, str | None]] = []

    class DummyUnresolved:
        def track_unresolved(self, normalized, *, original_query=None):
            calls.append((normalized, original_query))

    resolver.unresolved_repository = DummyUnresolved()
    monkeypatch.setattr(resolver, "_resolve_non_semantic", lambda *_args, **_kwargs: None)

    result = resolver.resolve_sync("Unknown Place", track_unresolved=True)
    assert result.not_found is True
    assert calls


def test_resolve_sync_perf_logging(monkeypatch, db):
    resolver = LocationResolver(db)
    monkeypatch.setattr(resolver_module, "_PERF_LOG_ENABLED", True)
    monkeypatch.setattr(resolver_module, "_PERF_LOG_SLOW_MS", 0)
    result = resolver.resolve_sync("unknownplace")
    assert result.not_found is True


@pytest.mark.asyncio
async def test_tier5_llm_match_handles_invalid_response(db):
    resolver = LocationResolver(db)

    async def _resolve(**_kwargs):
        return {"neighborhoods": "not-a-list"}

    resolver.llm_service.resolve = _resolve
    result = await resolver._tier5_llm_match("landmark", original_query="landmark")
    assert result.not_found is True


def test_cache_llm_alias_creates_rows(db):
    resolver = LocationResolver(db)
    region = _create_region(db, name="Tompkins Square")
    resolver.cache_llm_alias("tompkins", [region.id], confidence=0.9)

    cached = (
        db.query(LocationAlias)
        .filter(LocationAlias.alias_normalized == "tompkins", LocationAlias.source == "llm")
        .first()
    )
    assert cached is not None
    assert cached.region_boundary_id == region.id

    resolver.cache_llm_alias("tompkins-amb", [region.id, str(region.id)], confidence=0.8)
    cached = (
        db.query(LocationAlias)
        .filter(LocationAlias.alias_normalized == "tompkins-amb", LocationAlias.source == "llm")
        .first()
    )
    assert cached is not None
    assert cached.requires_clarification is False
    assert cached.region_boundary_id == region.id
    assert cached.candidate_region_ids is None


def test_cache_llm_alias_ignores_empty(db):
    resolver = LocationResolver(db)
    resolver.cache_llm_alias("", [], confidence=0.5)


def test_format_candidates_skips_invalid(db):
    resolver = LocationResolver(db)
    valid_region = _create_region(db, name="Valid Region")
    invalid = SimpleNamespace(id=None, region_name=None)
    candidates = resolver._format_candidates([invalid, valid_region])
    assert candidates == [
        {
            "region_id": valid_region.id,
            "region_name": valid_region.region_name,
            "borough": valid_region.parent_region,
            "display_name": None,
            "display_key": None,
            "region_ids": [valid_region.id],
        }
    ]


def test_dedupe_candidates_by_display_merges_region_ids_deterministically():
    candidates = [
        {
            "region_id": "r2",
            "region_name": "Upper East Side-Yorkville",
            "borough": "Manhattan",
            "display_name": "Upper East Side",
            "display_key": "nyc-manhattan-upper-east-side",
            "region_ids": ["r2"],
        },
        {
            "region_id": "r1",
            "region_name": "Upper East Side-Carnegie Hill",
            "borough": "Manhattan",
            "display_name": "Upper East Side",
            "display_key": "nyc-manhattan-upper-east-side",
            "region_ids": ["r1"],
        },
    ]

    deduped = LocationResolver._dedupe_candidates_by_display(candidates)

    assert deduped == [
        {
            "region_id": "r1",
            "region_name": "Upper East Side-Carnegie Hill",
            "borough": "Manhattan",
            "display_name": "Upper East Side",
            "display_key": "nyc-manhattan-upper-east-side",
            "region_ids": ["r1", "r2"],
        }
    ]


@pytest.mark.parametrize(
    ("display_key", "display_name", "raw_names"),
    CONSOLIDATED_DISPLAY_CASES,
)
def test_consolidated_display_keys_resolve_as_single_logical_candidate(
    db,
    display_key: str,
    display_name: str,
    raw_names: list[str],
):
    resolver = LocationResolver(db)
    rows = (
        db.query(RegionBoundary)
        .filter(
            RegionBoundary.region_type == "nyc",
            RegionBoundary.display_key == display_key,
        )
        .order_by(RegionBoundary.region_name.asc(), RegionBoundary.id.asc())
        .all()
    )

    canonical_rows_by_name: dict[str, RegionBoundary] = {}
    for row in rows:
        region_name = str(row.region_name or "")
        region_code = str(row.region_code or "")
        if region_name not in raw_names:
            continue
        if not str(row.display_key or "").startswith("nyc-"):
            continue
        if region_code.startswith("test-"):
            continue
        canonical_rows_by_name.setdefault(region_name, row)

    assert set(canonical_rows_by_name.keys()) == set(raw_names)
    canonical_rows = [canonical_rows_by_name[name] for name in sorted(canonical_rows_by_name)]
    canonical_ids = sorted(str(row.id) for row in canonical_rows)
    canonical_id_set = set(canonical_ids)

    result = resolver.resolve_sync(display_name)

    assert result.resolved is True
    assert result.requires_clarification is False
    assert result.region_name == display_name
    assert sorted(region_id for region_id in (result.region_ids or []) if region_id in canonical_id_set) == canonical_ids
    assert result.region_id is not None
    result_row = next((row for row in rows if str(row.id) == result.region_id), None)
    assert result_row is not None
    assert str(result_row.display_key or "").startswith("nyc-")
    assert str(result_row.region_name or "") in raw_names
