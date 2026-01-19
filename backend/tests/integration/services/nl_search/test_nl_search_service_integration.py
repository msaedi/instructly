from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from tests.conftest import _ensure_region_boundary

from app.models.location_alias import LocationAlias
from app.models.service_catalog import ServiceCatalog
from app.models.unresolved_location_query import UnresolvedLocationQuery
from app.repositories.search_batch_repository import (
    CachedAliasInfo,
    RegionInfo,
    RegionLookup,
    SearchBatchRepository,
)
from app.schemas.nl_search import NLSearchMeta, ParsedQueryInfo, StageStatus
from app.services.search.filter_service import FilterResult
from app.services.search.location_resolver import ResolutionTier, ResolvedLocation
from app.services.search.nl_search_service import (
    LOCATION_TIER4_HIGH_CONFIDENCE,
    LocationLLMCache,
    NLSearchService,
    PipelineTimer,
    PostOpenAIData,
    SearchMetrics,
    UnresolvedLocationInfo,
)
from app.services.search.query_parser import ParsedQuery
from app.services.search.ranking_service import RankedResult, RankingResult


def _make_search_cache() -> AsyncMock:
    cache = AsyncMock()
    cache.get_cached_response = AsyncMock(return_value=None)
    cache.get_cached_parsed_query = AsyncMock(return_value=None)
    cache.cache_response = AsyncMock(return_value=True)
    cache.cache_parsed_query = AsyncMock(return_value=True)
    return cache


def _set_catalog_embedding(db, *, slug: str, vector: list[float]) -> None:
    catalog = db.query(ServiceCatalog).filter(ServiceCatalog.slug == slug).first()
    assert catalog is not None
    catalog.embedding_v2 = vector
    catalog.embedding_model = "test-model"
    catalog.embedding_model_version = "test"
    catalog.embedding_updated_at = datetime.now(timezone.utc)
    db.commit()


def _make_region_lookup() -> RegionLookup:
    info1 = RegionInfo(region_id="r1", region_name="Manhattan - Midtown", borough="Manhattan")
    info2 = RegionInfo(region_id="r2", region_name="Manhattan - Downtown", borough="Manhattan")
    return RegionLookup(
        region_names=[info1.region_name, info2.region_name],
        by_name={
            info1.region_name.lower(): info1,
            info2.region_name.lower(): info2,
        },
        by_id={
            info1.region_id: info1,
            info2.region_id: info2,
        },
        embeddings=[],
    )


def test_normalize_and_match_flags():
    normalized = NLSearchService._normalize_location_text(" near  Upper East Side area ")
    assert normalized == "upper east side"

    normalized = NLSearchService._normalize_location_text("upper east north")
    assert normalized == "upper east"

    best, require_match, skip_vector = NLSearchService._compute_text_match_flags(
        "piano lessons", {"svc1": (0.9, {})}
    )
    assert best == 0.9
    assert require_match is True
    assert skip_vector is False


def test_cached_alias_resolution_and_distance_ids():
    lookup = _make_region_lookup()
    cached = CachedAliasInfo(
        confidence=0.9,
        is_resolved=True,
        is_ambiguous=False,
        region_id="r1",
        candidate_region_ids=[],
    )
    resolved = NLSearchService._resolve_cached_alias(cached, lookup)
    assert resolved is not None
    assert resolved.resolved is True

    ambiguous = CachedAliasInfo(
        confidence=0.7,
        is_resolved=False,
        is_ambiguous=True,
        region_id=None,
        candidate_region_ids=["r1", "r2"],
    )
    ambiguous_result = NLSearchService._resolve_cached_alias(ambiguous, lookup)
    assert ambiguous_result is not None
    assert ambiguous_result.requires_clarification is True

    distance_ids = NLSearchService._distance_region_ids(ambiguous_result)
    assert distance_ids == ["r1", "r2"]


def test_select_instructor_ids_dedupes():
    ranked = [
        RankedResult(
            service_id="s1",
            service_catalog_id="c1",
            instructor_id="i1",
            name="Piano",
            description=None,
            price_per_hour=50,
            final_score=0.9,
            rank=1,
            relevance_score=0.9,
            quality_score=0.5,
            distance_score=0.5,
            price_score=0.5,
            freshness_score=0.5,
            completeness_score=0.5,
            available_dates=[],
            earliest_available=None,
        ),
        RankedResult(
            service_id="s2",
            service_catalog_id="c2",
            instructor_id="i1",
            name="Guitar",
            description=None,
            price_per_hour=45,
            final_score=0.8,
            rank=2,
            relevance_score=0.8,
            quality_score=0.5,
            distance_score=0.5,
            price_score=0.5,
            freshness_score=0.5,
            completeness_score=0.5,
            available_dates=[],
            earliest_available=None,
        ),
    ]
    ids = NLSearchService._select_instructor_ids(ranked, limit=10)
    assert ids == ["i1"]


def test_format_location_resolved_and_soft_filter_message():
    location = ResolvedLocation.from_ambiguous(
        candidates=[
            {"region_id": "r1", "region_name": "Manhattan - Midtown"},
            {"region_id": "r2", "region_name": "Manhattan - Downtown"},
        ],
        tier=ResolutionTier.FUZZY,
        confidence=0.6,
    )
    formatted = NLSearchService()._format_location_resolved(location)
    assert formatted == "Manhattan (Downtown, Midtown)"

    parsed = ParsedQuery(
        service_query="piano lessons",
        original_query="piano lessons in manhattan",
        location_text="manhattan",
        max_price=40,
    )
    message = NLSearchService()._generate_soft_filter_message(
        parsed,
        {
            "after_location": 0,
            "after_availability": 0,
            "after_price": 0,
        },
        location,
        formatted,
        relaxed_constraints=["location", "price"],
        result_count=3,
    )
    assert "Relaxed" in message
    assert "No instructors found" in message


@pytest.mark.asyncio
async def test_embed_query_timeout_marks_degraded(monkeypatch):
    service = NLSearchService(search_cache=_make_search_cache())
    service.embedding_service.embed_query = AsyncMock(side_effect=asyncio.TimeoutError())

    embedding, latency, reason = await service._embed_query_with_timeout("piano")

    assert embedding is None
    assert latency >= 0
    assert reason == "embedding_timeout"


@pytest.mark.asyncio
async def test_resolve_location_llm_ambiguous():
    service = NLSearchService(search_cache=_make_search_cache())
    service.location_llm_service.resolve = AsyncMock(
        return_value={"neighborhoods": ["Manhattan - Midtown", "Manhattan - Downtown"], "confidence": 0.6}
    )

    lookup = _make_region_lookup()
    result, llm_cache, unresolved = await service._resolve_location_llm(
        location_text="manhattan",
        original_query="piano lessons in manhattan",
        region_lookup=lookup,
        candidate_names=lookup.region_names,
    )

    assert result is not None
    assert result.requires_clarification is True
    assert llm_cache is not None
    assert unresolved is None


@pytest.mark.asyncio
async def test_resolve_location_llm_empty_query_returns_none():
    service = NLSearchService(search_cache=_make_search_cache())
    lookup = _make_region_lookup()

    result, llm_cache, unresolved = await service._resolve_location_llm(
        location_text=" ",
        original_query="",
        region_lookup=lookup,
        candidate_names=lookup.region_names,
    )

    assert result is None
    assert llm_cache is None
    assert unresolved is None


@pytest.mark.asyncio
async def test_resolve_location_llm_no_candidates_returns_unresolved():
    service = NLSearchService(search_cache=_make_search_cache())
    lookup = _make_region_lookup()

    result, llm_cache, unresolved = await service._resolve_location_llm(
        location_text="manhattan",
        original_query="manhattan",
        region_lookup=lookup,
        candidate_names=["", "  "],
    )

    assert result is None
    assert llm_cache is None
    assert unresolved is not None


@pytest.mark.asyncio
async def test_resolve_location_llm_handles_missing_llm_result():
    service = NLSearchService(search_cache=_make_search_cache())
    service.location_llm_service.resolve = AsyncMock(return_value=None)
    lookup = _make_region_lookup()

    result, llm_cache, unresolved = await service._resolve_location_llm(
        location_text="manhattan",
        original_query="manhattan",
        region_lookup=lookup,
        candidate_names=lookup.region_names,
    )

    assert result is None
    assert llm_cache is None
    assert unresolved is not None


@pytest.mark.asyncio
async def test_resolve_location_llm_single_region_returns_resolved():
    service = NLSearchService(search_cache=_make_search_cache())
    service.location_llm_service.resolve = AsyncMock(
        return_value={"neighborhoods": ["Manhattan - Midtown"], "confidence": 0.9}
    )
    lookup = _make_region_lookup()

    result, llm_cache, unresolved = await service._resolve_location_llm(
        location_text="manhattan",
        original_query="manhattan",
        region_lookup=lookup,
        candidate_names=lookup.region_names,
    )

    assert result is not None
    assert result.resolved is True
    assert llm_cache is not None
    assert unresolved is None


@pytest.mark.asyncio
async def test_resolve_location_openai_embedding_skips_tier5(db):
    service = NLSearchService(search_cache=_make_search_cache())

    boundary = _ensure_region_boundary(db, "Manhattan")
    embedding = [0.01] * 1536
    boundary.name_embedding = embedding
    db.commit()

    lookup = SearchBatchRepository(db, region_code="nyc").load_region_lookup()

    service.location_embedding_service.embed_location_text = AsyncMock(return_value=embedding)
    service.location_llm_service.resolve = AsyncMock(side_effect=AssertionError("LLM should be skipped"))

    timer = PipelineTimer()
    resolved, llm_cache, unresolved = await service._resolve_location_openai(
        "manhattan",
        region_lookup=lookup,
        fuzzy_score=None,
        original_query="piano lessons in manhattan",
        allow_tier4=True,
        allow_tier5=True,
        diagnostics=timer,
    )

    assert resolved is not None
    assert resolved.tier == ResolutionTier.EMBEDDING
    assert resolved.confidence >= LOCATION_TIER4_HIGH_CONFIDENCE
    assert llm_cache is None
    assert unresolved is None


@pytest.mark.asyncio
async def test_resolve_location_openai_llm_fallback():
    service = NLSearchService(search_cache=_make_search_cache())
    lookup = _make_region_lookup()
    dummy = ResolvedLocation.from_region(
        region_id="r1",
        region_name="Manhattan - Midtown",
        borough="Manhattan",
        tier=ResolutionTier.LLM,
        confidence=0.8,
    )
    service._resolve_location_llm = AsyncMock(
        return_value=(
            dummy,
            LocationLLMCache(normalized="manhattan", confidence=0.8, region_ids=["r1"]),
            None,
        )
    )

    resolved, llm_cache, unresolved = await service._resolve_location_openai(
        "manhattan",
        region_lookup=lookup,
        fuzzy_score=None,
        original_query="piano lessons in manhattan",
        allow_tier4=False,
        allow_tier5=True,
    )

    assert resolved.region_id == "r1"
    assert llm_cache is not None
    assert unresolved is None


@pytest.mark.asyncio
async def test_search_cache_hit_builds_diagnostics():
    cache = _make_search_cache()
    meta = NLSearchMeta(
        query="piano lessons",
        parsed=ParsedQueryInfo(service_query="piano lessons"),
        total_results=0,
        limit=20,
        latency_ms=0,
    )
    cache.get_cached_response.return_value = {
        "results": [],
        "meta": meta.model_dump(),
    }
    service = NLSearchService(search_cache=cache)

    response = await service.search("piano lessons", include_diagnostics=True)

    assert response.meta.cache_hit is True
    assert response.meta.diagnostics is not None
    assert response.meta.diagnostics.cache_hit is True


@pytest.mark.asyncio
async def test_search_concurrency_limit_raises_503(monkeypatch):
    from app.services.search import nl_search_service as module

    cache = _make_search_cache()
    service = NLSearchService(search_cache=cache)

    config = SimpleNamespace(
        uncached_concurrency=1,
        high_load_threshold=999,
        high_load_budget_ms=200,
        search_budget_ms=2000,
        embedding_timeout_ms=50,
        location_timeout_ms=200,
    )
    monkeypatch.setattr(module, "get_search_config", lambda: config)
    monkeypatch.setattr(module, "_search_inflight_requests", 1)

    with pytest.raises(Exception) as exc_info:
        await service.search("piano lessons")

    assert "Search temporarily overloaded" in str(exc_info.value)
    monkeypatch.setattr(module, "_search_inflight_requests", 0)


@pytest.mark.asyncio
async def test_search_pipeline_text_only_integration(db, test_instructor):
    cache = _make_search_cache()
    service = NLSearchService(search_cache=cache)

    response = await service.search(
        "piano lessons in manhattan",
        limit=5,
        include_diagnostics=True,
        force_skip_vector=True,
        force_skip_tier4=True,
        force_skip_tier5=True,
    )

    assert response.results
    assert response.meta.parsing_mode in {"regex", "hybrid"}
    assert response.meta.diagnostics is not None


@pytest.mark.asyncio
async def test_search_pipeline_vector_integration(db, test_instructor):
    cache = _make_search_cache()
    service = NLSearchService(search_cache=cache)

    embedding = [0.02] * 1536
    _set_catalog_embedding(db, slug="piano", vector=embedding)
    service.embedding_service.embed_query = AsyncMock(return_value=embedding)

    response = await service.search("piano lessons", limit=5, include_diagnostics=True)

    assert response.results
    assert response.meta.diagnostics is not None
    assert response.meta.diagnostics.vector_search_used is True


def test_run_pre_openai_burst_uses_cached_alias(db, test_instructor):
    service = NLSearchService(search_cache=_make_search_cache())
    boundary = _ensure_region_boundary(db, "Manhattan")
    alias_key = f"llm-{int(datetime.now(timezone.utc).timestamp() * 1000)}"
    alias = LocationAlias(
        alias_normalized=alias_key,
        region_boundary_id=boundary.id,
        source="llm",
        status="pending_review",
        confidence=0.4,
    )
    db.add(alias)
    db.commit()

    parsed_query = ParsedQuery(
        service_query="piano lessons",
        original_query=f"piano lessons in {alias_key}",
        location_text=alias_key,
        location_type="neighborhood",
    )
    pre_data = service._run_pre_openai_burst(
        f"piano lessons in {alias_key}",
        parsed_query=parsed_query,
        user_id=None,
        user_location=None,
    )

    assert pre_data.cached_alias_normalized == alias_key
    assert pre_data.location_resolution is not None


def test_run_post_openai_burst_tracks_unresolved(db, test_instructor):
    service = NLSearchService(search_cache=_make_search_cache())
    pre_data = service._run_pre_openai_burst(
        "piano lessons",
        parsed_query=None,
        user_id=None,
        user_location=None,
    )
    parsed = replace(pre_data.parsed_query, location_text=None)

    alias_key = f"llm-{int(datetime.now(timezone.utc).timestamp() * 1000)}"
    alias = LocationAlias(
        alias_normalized=alias_key,
        region_boundary_id=None,
        requires_clarification=True,
        candidate_region_ids=[],
        source="llm",
        confidence=0.6,
    )
    db.add(alias)
    db.commit()

    pre_data.cached_alias_normalized = alias_key

    location_llm_cache = LocationLLMCache(
        normalized=alias_key,
        confidence=0.7,
        region_ids=[_ensure_region_boundary(db, "Manhattan").id],
    )
    unresolved = UnresolvedLocationInfo(normalized="unknown", original_query="unknown place")

    post = service._run_post_openai_burst(
        pre_data,
        parsed,
        query_embedding=None,
        location_resolution=None,
        location_llm_cache=location_llm_cache,
        unresolved_info=unresolved,
        user_location=None,
        limit=5,
    )

    assert post.total_candidates >= 0
    stored = (
        db.query(UnresolvedLocationQuery)
        .filter(UnresolvedLocationQuery.query_normalized == "unknown")
        .first()
    )
    assert stored is not None


def test_transform_instructor_results_filters_price():
    parsed = ParsedQuery(service_query="piano", original_query="piano", max_price=40)
    raw_results = [
        {
            "instructor_id": "i1",
            "first_name": "Test",
            "last_initial": "I",
            "bio_snippet": None,
            "years_experience": 5,
            "profile_picture_key": None,
            "verified": True,
            "matching_services": [
                {
                    "service_id": "s1",
                    "service_catalog_id": "c1",
                    "name": "Piano",
                    "description": None,
                    "price_per_hour": 60,
                    "relevance_score": 0.9,
                }
            ],
            "avg_rating": 4.8,
            "review_count": 5,
            "coverage_areas": [],
        }
    ]

    service = NLSearchService(search_cache=_make_search_cache())
    results = service._transform_instructor_results(raw_results, parsed)

    assert results == []


@pytest.mark.asyncio
async def test_hydrate_instructor_results_uses_distance_map():
    service = NLSearchService(search_cache=_make_search_cache())
    ranked = [
        RankedResult(
            service_id="s1",
            service_catalog_id="c1",
            instructor_id="i1",
            name="Piano",
            description=None,
            price_per_hour=50,
            final_score=0.9,
            rank=1,
            relevance_score=0.9,
            quality_score=0.5,
            distance_score=0.5,
            price_score=0.5,
            freshness_score=0.5,
            completeness_score=0.5,
            available_dates=[],
            earliest_available=None,
        )
    ]
    instructor_rows = [
        {
            "instructor_id": "i1",
            "first_name": "Test",
            "last_initial": "I",
            "profile_picture_key": None,
            "bio_snippet": None,
            "verified": True,
            "is_founding_instructor": False,
            "years_experience": 5,
            "avg_rating": 4.8,
            "review_count": 10,
            "coverage_areas": ["Manhattan"],
        }
    ]
    distance_meters = {"i1": 1200.0}

    results = await service._hydrate_instructor_results(
        ranked,
        limit=5,
        instructor_rows=instructor_rows,
        distance_meters=distance_meters,
    )

    assert results
    assert results[0].distance_km == 1.2


def test_build_search_diagnostics_includes_location():
    service = NLSearchService(search_cache=_make_search_cache())
    timer = PipelineTimer()
    timer.record_stage("parse", 10, StageStatus.SUCCESS.value, {})
    timer.record_location_tier(
        tier=4,
        attempted=True,
        status=StageStatus.SUCCESS.value,
        duration_ms=5,
        result="Manhattan",
        confidence=0.9,
    )
    parsed = ParsedQuery(service_query="piano", original_query="piano", location_text="manhattan")
    location = ResolvedLocation.from_region(
        region_id="r1",
        region_name="Manhattan",
        borough="Manhattan",
        tier=ResolutionTier.FUZZY,
        confidence=0.7,
    )

    diagnostics = service._build_search_diagnostics(
        timer=timer,
        budget=None,
        parsed_query=parsed,
        pre_data=None,
        post_data=None,
        location_resolution=location,
        query_embedding=None,
        results_count=0,
        cache_hit=False,
        parsing_mode="regex",
        candidates_flow={},
        total_latency_ms=25,
    )

    assert diagnostics.location_resolution is not None
    assert diagnostics.location_resolution.resolved_name == "Manhattan"


@pytest.mark.asyncio
async def test_parse_retrieve_filter_rank_paths():
    service = NLSearchService(search_cache=_make_search_cache())
    metrics = SearchMetrics()
    parsed = ParsedQuery(service_query="piano", original_query="piano")

    service.search_cache.get_cached_parsed_query.return_value = parsed
    parsed_result = await service._parse_query("piano", metrics)
    assert parsed_result.service_query == "piano"

    retrieval = Mock()
    retrieval.candidates = []
    retrieval.total_candidates = 0
    retrieval.vector_search_used = False
    retrieval.degraded = False
    retrieval.degradation_reason = None
    retrieval.embed_latency_ms = 0
    retrieval.db_latency_ms = 0

    service.retriever.search = AsyncMock(return_value=retrieval)
    retrieval_result = await service._retrieve_candidates(parsed, metrics)
    assert retrieval_result.total_candidates == 0

    service.filter_service.filter_candidates = AsyncMock(
        return_value=SimpleNamespace(
            candidates=[],
            total_before_filter=0,
            total_after_filter=0,
            filters_applied=[],
            soft_filtering_used=False,
        )
    )
    filtered = await service._filter_candidates(retrieval_result, parsed, None, metrics)
    assert filtered.total_after_filter == 0

    service.ranking_service.rank_candidates = Mock(return_value=RankingResult(results=[], total_results=0))
    ranked = service._rank_results(filtered, parsed, None, metrics)
    assert ranked.total_results == 0


@pytest.mark.asyncio
async def test_parse_query_fallback_on_error(monkeypatch):
    service = NLSearchService(search_cache=_make_search_cache())
    metrics = SearchMetrics()

    async def _raise(*args, **kwargs):
        raise RuntimeError("parse failed")

    monkeypatch.setattr("app.services.search.nl_search_service.hybrid_parse", _raise)
    parsed = await service._parse_query("piano lessons", metrics)

    assert parsed.service_query
    assert metrics.degraded is True


@pytest.mark.asyncio
async def test_consume_task_result_swallows_errors():
    async def _boom():
        raise ValueError("boom")

    task = asyncio.create_task(_boom())
    NLSearchService._consume_task_result(task, label="boom")
    await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_budget_helpers_and_inflight_count(monkeypatch):
    from app.services.search import nl_search_service as module

    config = SimpleNamespace(
        high_load_threshold=1,
        high_load_budget_ms=25,
        search_budget_ms=250,
    )
    monkeypatch.setattr(module, "get_search_config", lambda: config)

    assert module._get_adaptive_budget(1) == 25
    assert module._get_adaptive_budget(0) == 250

    monkeypatch.setattr(module, "_search_inflight_requests", 3)
    assert await module.get_search_inflight_count() == 3
    assert await module.set_uncached_search_concurrency_limit(0) == 1


def test_record_pre_location_tiers_marks_resolved():
    timer = PipelineTimer()
    location = ResolvedLocation.from_region(
        region_id="r1",
        region_name="Manhattan",
        borough="Manhattan",
        tier=ResolutionTier.EXACT,
        confidence=1.0,
    )
    NLSearchService._record_pre_location_tiers(timer, location)

    resolved = [t for t in timer.location_tiers if t["status"] == StageStatus.SUCCESS.value]
    assert resolved


@pytest.mark.asyncio
async def test_search_needs_llm_path(db, test_instructor, monkeypatch):
    cache = _make_search_cache()
    service = NLSearchService(search_cache=cache)
    cache.get_cached_parsed_query.return_value = ParsedQuery(
        service_query="piano lessons",
        original_query="piano or guitar lessons in manhattan",
        location_text="manhattan",
        location_type="borough",
        needs_llm=True,
    )

    class DummyLLMParser:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def parse(self, query: str, parsed_query: ParsedQuery) -> ParsedQuery:
            parsed_query.parsing_mode = "llm"
            parsed_query.needs_llm = False
            return parsed_query

    monkeypatch.setattr("app.services.search.llm_parser.LLMParser", DummyLLMParser)

    response = await service.search(
        "piano or guitar lessons in manhattan",
        limit=3,
        include_diagnostics=True,
    )

    assert response.meta.parsing_mode == "llm"


@pytest.mark.asyncio
async def test_search_cache_hit_perf_logging(monkeypatch):
    from app.services.search import nl_search_service as module

    cache = _make_search_cache()
    meta = NLSearchMeta(
        query="piano lessons",
        parsed=ParsedQueryInfo(service_query="piano lessons"),
        total_results=0,
        limit=20,
        latency_ms=0,
    )
    cache.get_cached_response.return_value = {"results": [], "meta": meta.model_dump()}

    monkeypatch.setattr(module, "_PERF_LOG_ENABLED", True)
    monkeypatch.setattr(module, "_PERF_LOG_SLOW_MS", 0)

    service = NLSearchService(search_cache=cache)
    response = await service.search("piano lessons", include_diagnostics=True)

    assert response.meta.cache_hit is True


@pytest.mark.asyncio
async def test_search_parsed_query_cache_lookup_failure(db, test_instructor):
    cache = _make_search_cache()
    cache.get_cached_parsed_query.side_effect = RuntimeError("cache down")

    service = NLSearchService(search_cache=cache)
    response = await service.search("piano lessons", force_skip_vector=True)

    assert response.results


@pytest.mark.asyncio
async def test_search_pre_openai_burst_failure_cancels_embedding_task():
    cache = _make_search_cache()
    service = NLSearchService(search_cache=cache)

    def _boom(*args, **kwargs):
        raise RuntimeError("burst failed")

    service._run_pre_openai_burst = _boom

    with pytest.raises(RuntimeError):
        await service.search("piano lessons")


@pytest.mark.asyncio
async def test_search_cache_parsed_query_failure(db, test_instructor):
    cache = _make_search_cache()
    cache.cache_parsed_query.side_effect = RuntimeError("cache write failed")

    service = NLSearchService(search_cache=cache)
    response = await service.search("piano lessons", force_skip_vector=True)

    assert response.results


@pytest.mark.asyncio
async def test_search_unknown_location_uses_tier5_task(db, test_instructor):
    cache = _make_search_cache()
    cached_parsed = ParsedQuery(
        service_query="piano lessons",
        original_query="piano lessons in madeupplace",
        location_text="madeupplace",
        location_type="neighborhood",
    )
    cache.get_cached_parsed_query.return_value = cached_parsed
    service = NLSearchService(search_cache=cache)
    service._resolve_location_llm = AsyncMock(
        return_value=(None, None, UnresolvedLocationInfo(normalized="madeupplace", original_query="madeupplace"))
    )

    response = await service.search(
        "piano lessons in madeupplace",
        include_diagnostics=True,
        force_skip_tier4=True,
    )

    assert response.meta.location_not_found is True
    assert response.meta.diagnostics is not None


@pytest.mark.asyncio
async def test_search_budget_skip_vector_and_degradation(db, test_instructor):
    cache = _make_search_cache()
    service = NLSearchService(search_cache=cache)

    response = await service.search(
        "piano lessons",
        budget_ms=1,
        include_diagnostics=True,
    )

    assert response.meta.degraded is True
    assert "budget_skip_vector_search" in response.meta.degradation_reasons


@pytest.mark.asyncio
async def test_resolve_location_openai_missing_region_lookup():
    service = NLSearchService(search_cache=_make_search_cache())
    timer = PipelineTimer()

    resolved, llm_cache, unresolved = await service._resolve_location_openai(
        "manhattan",
        region_lookup=None,
        fuzzy_score=None,
        original_query="manhattan",
        diagnostics=timer,
    )

    assert resolved.not_found is True
    assert llm_cache is None
    assert unresolved is not None


def test_run_post_openai_burst_when_text_results_missing(db, test_instructor):
    service = NLSearchService(search_cache=_make_search_cache())
    pre_data = service._run_pre_openai_burst(
        "piano lessons",
        parsed_query=None,
        user_id=None,
        user_location=None,
    )
    pre_data = replace(
        pre_data,
        text_results=None,
        text_latency_ms=0,
        require_text_match=False,
        skip_vector=False,
    )

    post = service._run_post_openai_burst(
        pre_data,
        pre_data.parsed_query,
        query_embedding=None,
        location_resolution=None,
        location_llm_cache=None,
        unresolved_info=None,
        user_location=None,
        limit=5,
    )

    assert post.text_latency_ms >= 0


def test_run_post_openai_burst_handles_filter_and_ranking_errors(monkeypatch, db, test_instructor):
    def _raise_filter(*args, **kwargs):
        raise RuntimeError("filter failed")

    def _raise_rank(*args, **kwargs):
        raise RuntimeError("rank failed")

    monkeypatch.setattr(
        "app.services.search.filter_service.FilterService.filter_candidates_sync",
        _raise_filter,
    )
    monkeypatch.setattr(
        "app.services.search.ranking_service.RankingService.rank_candidates",
        _raise_rank,
    )

    service = NLSearchService(search_cache=_make_search_cache())
    pre_data = service._run_pre_openai_burst(
        "piano lessons in manhattan",
        parsed_query=None,
        user_id=None,
        user_location=None,
    )
    location = ResolvedLocation.from_region(
        region_id=_ensure_region_boundary(db, "Manhattan").id,
        region_name="Manhattan",
        borough="Manhattan",
        tier=ResolutionTier.EXACT,
        confidence=1.0,
    )

    post = service._run_post_openai_burst(
        pre_data,
        pre_data.parsed_query,
        query_embedding=None,
        location_resolution=location,
        location_llm_cache=None,
        unresolved_info=None,
        user_location=None,
        limit=5,
    )

    assert post.filter_failed is True
    assert post.ranking_failed is True


@pytest.mark.asyncio
async def test_search_handles_post_openai_failures(db, test_instructor):
    cache = _make_search_cache()
    service = NLSearchService(search_cache=cache)

    filter_result = FilterResult(
        candidates=[],
        total_before_filter=0,
        total_after_filter=0,
        filters_applied=[],
        soft_filtering_used=False,
    )
    post_data = PostOpenAIData(
        filter_result=filter_result,
        ranking_result=RankingResult(results=[], total_results=0),
        retrieval_candidates=[],
        instructor_rows=[],
        distance_meters={},
        text_latency_ms=0,
        vector_latency_ms=0,
        filter_latency_ms=0,
        rank_latency_ms=0,
        vector_search_used=False,
        total_candidates=0,
        filter_failed=True,
        ranking_failed=True,
        skip_vector=True,
    )

    service._run_post_openai_burst = Mock(return_value=post_data)
    service._hydrate_instructor_results = AsyncMock(side_effect=RuntimeError("boom"))

    response = await service.search("piano lessons", include_diagnostics=True)

    assert response.meta.degraded is True
    assert "filtering_error" in response.meta.degradation_reasons
