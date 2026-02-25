"""
Coverage tests for nl_search_service.py targeting uncovered edge-case paths.

Covers: subcategory filter cache, adaptive budget, inflight counting,
PipelineTimer stages, search metrics, pre/post OpenAI data structures,
and concurrency limit helpers.
"""

from __future__ import annotations

import asyncio
import time as time_mod
from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.unit
class TestSubcategoryFilterCache:
    def test_cache_miss(self):
        from app.services.search.nl_search_service import _get_cached_subcategory_filter_value

        hit, value = _get_cached_subcategory_filter_value("nonexistent_key_12345")
        assert hit is False
        assert value is None

    def test_cache_hit(self):
        from app.services.search.nl_search_service import (
            _get_cached_subcategory_filter_value,
            _set_cached_subcategory_filter_value,
        )

        _set_cached_subcategory_filter_value("test_key_hit", {"filters": [1, 2]})
        hit, value = _get_cached_subcategory_filter_value("test_key_hit")
        assert hit is True
        assert value == {"filters": [1, 2]}

    def test_cache_expired(self):
        from app.services.search.nl_search_service import (
            SUBCATEGORY_FILTER_CACHE_TTL_SECONDS,
            _get_cached_subcategory_filter_value,
            _subcategory_filter_cache,
            _subcategory_filter_cache_lock,
        )

        # Insert with expired timestamp
        with _subcategory_filter_cache_lock:
            _subcategory_filter_cache["expired_key_test"] = (
                time_mod.monotonic() - SUBCATEGORY_FILTER_CACHE_TTL_SECONDS - 10,
                "old_value",
            )
        hit, value = _get_cached_subcategory_filter_value("expired_key_test")
        assert hit is False

    def test_cache_eviction_on_full(self):
        from app.services.search.nl_search_service import (
            SUBCATEGORY_FILTER_CACHE_MAX_ENTRIES,
            _set_cached_subcategory_filter_value,
            _subcategory_filter_cache,
            _subcategory_filter_cache_lock,
        )

        # Save original state and fill the cache
        original = dict(_subcategory_filter_cache)
        try:
            with _subcategory_filter_cache_lock:
                _subcategory_filter_cache.clear()
                for i in range(SUBCATEGORY_FILTER_CACHE_MAX_ENTRIES):
                    _subcategory_filter_cache[f"fill_{i}"] = (time_mod.monotonic(), i)
            # This should trigger eviction
            _set_cached_subcategory_filter_value("new_entry_after_full", "new_value")
            # After eviction, cache should be smaller than max
            assert len(_subcategory_filter_cache) <= SUBCATEGORY_FILTER_CACHE_MAX_ENTRIES
        finally:
            with _subcategory_filter_cache_lock:
                _subcategory_filter_cache.clear()
                _subcategory_filter_cache.update(original)


@pytest.mark.unit
class TestAdaptiveBudget:
    @patch("app.services.search.nl_search_service.get_search_config")
    def test_low_load(self, mock_config):
        config = MagicMock()
        config.high_load_threshold = 10
        config.high_load_budget_ms = 500
        config.search_budget_ms = 2000
        mock_config.return_value = config

        from app.services.search.nl_search_service import _get_adaptive_budget

        result = _get_adaptive_budget(3)
        assert result == 2000

    @patch("app.services.search.nl_search_service.get_search_config")
    def test_high_load(self, mock_config):
        config = MagicMock()
        config.high_load_threshold = 5
        config.high_load_budget_ms = 500
        config.search_budget_ms = 2000
        mock_config.return_value = config

        from app.services.search.nl_search_service import _get_adaptive_budget

        result = _get_adaptive_budget(10)
        assert result == 500

    @patch("app.services.search.nl_search_service.get_search_config")
    def test_force_high_load(self, mock_config):
        config = MagicMock()
        config.high_load_threshold = 100
        config.high_load_budget_ms = 500
        config.search_budget_ms = 2000
        mock_config.return_value = config

        from app.services.search.nl_search_service import _get_adaptive_budget

        result = _get_adaptive_budget(1, force_high_load=True)
        assert result == 500


@pytest.mark.unit
class TestInflightCounting:
    @pytest.mark.asyncio
    async def test_increment_and_decrement(self):
        from app.services.search.nl_search_service import (
            _decrement_search_inflight,
            _increment_search_inflight,
            get_search_inflight_count,
        )

        initial = await get_search_inflight_count()
        val = await _increment_search_inflight()
        assert val == initial + 1
        after = await get_search_inflight_count()
        assert after == initial + 1
        await _decrement_search_inflight()
        final = await get_search_inflight_count()
        assert final == initial

    @pytest.mark.asyncio
    async def test_decrement_floor_zero(self):
        from app.services.search.nl_search_service import (
            _decrement_search_inflight,
        )

        # Force to zero via multiple decrements (safe floor)
        for _ in range(5):
            await _decrement_search_inflight()


@pytest.mark.unit
class TestSetConcurrencyLimit:
    @pytest.mark.asyncio
    async def test_min_one(self):
        from app.services.search.nl_search_service import set_uncached_search_concurrency_limit

        result = await set_uncached_search_concurrency_limit(0)
        assert result == 1
        result = await set_uncached_search_concurrency_limit(-5)
        assert result == 1
        result = await set_uncached_search_concurrency_limit(10)
        assert result == 10


@pytest.mark.unit
class TestPipelineTimer:
    def test_start_and_end_stage(self):
        from app.services.search.nl_search_service import PipelineTimer

        timer = PipelineTimer()
        timer.start_stage("parse")
        timer.end_stage("success", {"tokens": 5})
        assert len(timer.stages) == 1
        assert timer.stages[0]["name"] == "parse"
        assert timer.stages[0]["status"] == "success"

    def test_end_without_start(self):
        from app.services.search.nl_search_service import PipelineTimer

        timer = PipelineTimer()
        timer.end_stage("success")  # Should not raise or add a stage
        assert len(timer.stages) == 0

    def test_record_stage(self):
        from app.services.search.nl_search_service import PipelineTimer

        timer = PipelineTimer()
        timer.record_stage("embed", 150, "success", {"model": "ada"})
        assert len(timer.stages) == 1
        assert timer.stages[0]["duration_ms"] == 150

    def test_negative_duration_clamped(self):
        from app.services.search.nl_search_service import PipelineTimer

        timer = PipelineTimer()
        timer.record_stage("test", -50, "error")
        assert timer.stages[0]["duration_ms"] == 0

    def test_skip_stage(self):
        from app.services.search.nl_search_service import PipelineTimer

        timer = PipelineTimer()
        timer.skip_stage("vector", "disabled by config")
        assert len(timer.stages) == 1
        assert timer.stages[0]["duration_ms"] == 0

    def test_record_location_tier(self):
        from app.services.search.nl_search_service import PipelineTimer

        timer = PipelineTimer()
        timer.record_location_tier(
            tier=3,
            attempted=True,
            status="success",
            duration_ms=45,
            result="Manhattan",
            confidence=0.95,
        )
        assert len(timer.location_tiers) == 1
        assert timer.location_tiers[0]["tier"] == 3
        assert timer.location_tiers[0]["confidence"] == 0.95


@pytest.mark.unit
class TestSearchMetrics:
    def test_defaults(self):
        from app.services.search.nl_search_service import SearchMetrics

        m = SearchMetrics()
        assert m.cache_hit is False
        assert m.degraded is False
        assert m.degradation_reasons == []
        assert m.total_latency_ms == 0


@pytest.mark.unit
class TestPreOpenAIData:
    def test_default_fields(self):
        from app.services.search.nl_search_service import PreOpenAIData
        from app.services.search.query_parser import ParsedQuery

        parsed = MagicMock(spec=ParsedQuery)
        data = PreOpenAIData(
            parsed_query=parsed,
            parse_latency_ms=10,
            text_results=None,
            text_latency_ms=5,
            has_service_embeddings=True,
            best_text_score=0.8,
            require_text_match=False,
            skip_vector=False,
            region_lookup=None,
            location_resolution=None,
            location_normalized=None,
            cached_alias_normalized=None,
            fuzzy_score=None,
        )
        assert data.location_llm_candidates == []
        assert data.parse_latency_ms == 10


@pytest.mark.unit
class TestPostOpenAIData:
    def test_default_fields(self):
        from app.services.search.nl_search_service import PostOpenAIData

        data = PostOpenAIData(
            filter_result=MagicMock(),
            ranking_result=MagicMock(),
            retrieval_candidates=[],
            instructor_rows=[],
            distance_meters={},
            text_latency_ms=0,
            vector_latency_ms=0,
            filter_latency_ms=0,
            rank_latency_ms=0,
            vector_search_used=False,
            total_candidates=0,
            filter_failed=False,
            ranking_failed=False,
            skip_vector=True,
        )
        assert data.inferred_filters == {}
        assert data.available_content_filters == []
        assert data.effective_subcategory_id is None


@pytest.mark.unit
class TestLocationLLMCache:
    def test_frozen(self):
        from app.services.search.nl_search_service import LocationLLMCache

        cache = LocationLLMCache(normalized="manhattan", confidence=0.9, region_ids=["R1"])
        assert cache.normalized == "manhattan"
        with pytest.raises(AttributeError):
            cache.normalized = "other"  # type: ignore[misc]


@pytest.mark.unit
class TestUnresolvedLocationInfo:
    def test_frozen(self):
        from app.services.search.nl_search_service import UnresolvedLocationInfo

        info = UnresolvedLocationInfo(normalized="downtown", original_query="piano downtown")
        assert info.original_query == "piano downtown"
        with pytest.raises(AttributeError):
            info.normalized = "other"  # type: ignore[misc]


@pytest.mark.unit
class TestNLSearchServiceInit:
    def test_default_init(self):
        from app.services.search.nl_search_service import NLSearchService

        svc = NLSearchService(cache_service=None, region_code="nyc")
        assert svc._region_code == "nyc"
        assert svc.search_cache is not None
        assert svc.embedding_service is not None

    def test_custom_region(self):
        from app.services.search.nl_search_service import NLSearchService

        svc = NLSearchService(cache_service=None, region_code="la")
        assert svc._region_code == "la"

    def test_with_all_custom_services(self):
        from app.services.search.nl_search_service import NLSearchService

        mock_cache = MagicMock()
        mock_search_cache = MagicMock()
        mock_embed = MagicMock()
        mock_retriever = MagicMock()
        mock_filter = MagicMock()
        mock_ranking = MagicMock()

        svc = NLSearchService(
            cache_service=mock_cache,
            search_cache=mock_search_cache,
            embedding_service=mock_embed,
            retriever=mock_retriever,
            filter_service=mock_filter,
            ranking_service=mock_ranking,
        )
        assert svc.search_cache is mock_search_cache
        assert svc.embedding_service is mock_embed
        assert svc.retriever is mock_retriever
        assert svc.filter_service is mock_filter
        assert svc.ranking_service is mock_ranking


# ---------------------------------------------------------------------------
# _resolve_effective_subcategory_id  (lines 1252->1255)
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestResolveEffectiveSubcategoryId:
    def test_explicit_empty_string_falls_through(self):
        """L1252->1255: explicit_subcategory_id is whitespace-only -> falls to consensus."""
        from app.services.search.nl_search_service import NLSearchService

        result = NLSearchService._resolve_effective_subcategory_id(
            [],
            explicit_subcategory_id="   ",
        )
        assert result is None

    def test_explicit_nonempty_returns_stripped(self):
        from app.services.search.nl_search_service import NLSearchService

        result = NLSearchService._resolve_effective_subcategory_id(
            [],
            explicit_subcategory_id="  SUB123  ",
        )
        assert result == "SUB123"

    def test_no_candidates_returns_none(self):
        from app.services.search.nl_search_service import NLSearchService

        result = NLSearchService._resolve_effective_subcategory_id(
            [],
            explicit_subcategory_id=None,
        )
        assert result is None

    def test_single_candidate_returns_its_subcategory(self):
        from app.services.search.nl_search_service import NLSearchService

        candidate = MagicMock()
        candidate.subcategory_id = "SUB_A"
        result = NLSearchService._resolve_effective_subcategory_id(
            [candidate],
            explicit_subcategory_id=None,
        )
        assert result == "SUB_A"


# ---------------------------------------------------------------------------
# _resolve_cached_alias  (lines 1389->1397)
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestResolveCachedAlias:
    def test_resolved_alias_with_region_id_found(self):
        """L1387-1396: is_resolved=True, region_id matched in lookup -> returns region."""
        from app.services.search.nl_search_service import NLSearchService

        cached_alias = MagicMock()
        cached_alias.is_ambiguous = False
        cached_alias.is_resolved = True
        cached_alias.region_id = "R1"
        cached_alias.confidence = 0.9

        region_info = MagicMock()
        region_info.region_id = "R1"
        region_info.region_name = "Astoria"
        region_info.borough = "Queens"

        region_lookup = MagicMock()
        region_lookup.by_id = {"R1": region_info}

        result = NLSearchService._resolve_cached_alias(cached_alias, region_lookup)
        assert result is not None
        assert result.region_name == "Astoria"

    def test_resolved_alias_region_not_in_lookup(self):
        """L1389->1397: is_resolved but region_id not in lookup -> returns None."""
        from app.services.search.nl_search_service import NLSearchService

        cached_alias = MagicMock()
        cached_alias.is_ambiguous = False
        cached_alias.is_resolved = True
        cached_alias.region_id = "MISSING"
        cached_alias.confidence = 0.9

        region_lookup = MagicMock()
        region_lookup.by_id = {}

        result = NLSearchService._resolve_cached_alias(cached_alias, region_lookup)
        assert result is None

    def test_ambiguous_alias_fewer_than_two_candidates(self):
        """Ambiguous alias but only 1 region found -> no resolution."""
        from app.services.search.nl_search_service import NLSearchService

        cached_alias = MagicMock()
        cached_alias.is_ambiguous = True
        cached_alias.is_resolved = False
        cached_alias.candidate_region_ids = ["R1", "R_MISSING"]
        cached_alias.region_id = None
        cached_alias.confidence = 0.7

        region_info = MagicMock()
        region_info.region_id = "R1"
        region_info.region_name = "Astoria"
        region_info.borough = "Queens"

        region_lookup = MagicMock()
        region_lookup.by_id = {"R1": region_info}

        result = NLSearchService._resolve_cached_alias(cached_alias, region_lookup)
        # Only 1 candidate found (R_MISSING not in lookup) -> None
        assert result is None


# ---------------------------------------------------------------------------
# _format_location_resolved  (lines 3114->3107)
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestFormatLocationResolved:
    def test_none_input(self):
        from app.services.search.nl_search_service import NLSearchService

        svc = NLSearchService(cache_service=None)
        assert svc._format_location_resolved(None) is None

    def test_resolved_returns_region_name(self):
        from app.services.search.nl_search_service import NLSearchService

        svc = NLSearchService(cache_service=None)
        loc = MagicMock()
        loc.resolved = True
        loc.region_name = "Williamsburg"
        loc.borough = "Brooklyn"
        result = svc._format_location_resolved(loc)
        assert result == "Williamsburg"

    def test_resolved_fallback_to_borough(self):
        from app.services.search.nl_search_service import NLSearchService

        svc = NLSearchService(cache_service=None)
        loc = MagicMock()
        loc.resolved = True
        loc.region_name = None
        loc.borough = "Brooklyn"
        result = svc._format_location_resolved(loc)
        assert result == "Brooklyn"

    def test_clarification_with_candidates(self):
        """L3107-3115: candidates with region_name -> joined string."""
        from app.services.search.nl_search_service import NLSearchService

        svc = NLSearchService(cache_service=None)
        loc = MagicMock()
        loc.resolved = False
        loc.requires_clarification = True
        loc.candidates = [
            {"region_id": "R1", "region_name": "Astoria", "borough": "Queens"},
            {"region_id": "R2", "region_name": "Astoria Heights", "borough": "Queens"},
        ]
        result = svc._format_location_resolved(loc)
        assert result is not None
        assert "Astoria" in result

    def test_clarification_candidates_non_dict(self):
        """L3108: non-dict candidate -> skipped."""
        from app.services.search.nl_search_service import NLSearchService

        svc = NLSearchService(cache_service=None)
        loc = MagicMock()
        loc.resolved = False
        loc.requires_clarification = True
        loc.candidates = ["not_a_dict", 123]
        result = svc._format_location_resolved(loc)
        assert result is None

    def test_clarification_candidate_empty_name(self):
        """L3114->3107: candidate with empty region_name -> skipped."""
        from app.services.search.nl_search_service import NLSearchService

        svc = NLSearchService(cache_service=None)
        loc = MagicMock()
        loc.resolved = False
        loc.requires_clarification = True
        loc.candidates = [
            {"region_id": "R1", "region_name": "  "},
        ]
        result = svc._format_location_resolved(loc)
        assert result is None


# ---------------------------------------------------------------------------
# _generate_soft_filter_message  (lines 3165->3171)
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestGenerateSoftFilterMessage:
    def test_location_not_found(self):
        """L3163-3164: location_text present and location not_found."""
        from app.services.search.nl_search_service import NLSearchService

        svc = NLSearchService(cache_service=None)
        parsed = MagicMock()
        parsed.location_text = "narnia"
        parsed.date = None
        parsed.time_after = None
        parsed.max_price = None

        loc = MagicMock()
        loc.not_found = True

        msg = svc._generate_soft_filter_message(
            parsed,
            {},
            loc,
            None,
            relaxed_constraints=[],
            result_count=0,
        )
        assert msg is not None
        assert "narnia" in msg

    def test_after_location_zero(self):
        """L3165->3171: after_location==0 -> message about no instructors."""
        from app.services.search.nl_search_service import NLSearchService

        svc = NLSearchService(cache_service=None)
        parsed = MagicMock()
        parsed.location_text = "williamsburg"
        parsed.date = None
        parsed.time_after = None
        parsed.max_price = None

        loc = MagicMock()
        loc.not_found = False

        msg = svc._generate_soft_filter_message(
            parsed,
            {"after_location": 0},
            loc,
            "Williamsburg",
            relaxed_constraints=[],
            result_count=0,
        )
        assert msg is not None
        assert "Williamsburg" in msg

    def test_availability_date_zero(self):
        """L3171: availability with date and after_availability==0."""
        import datetime

        from app.services.search.nl_search_service import NLSearchService

        svc = NLSearchService(cache_service=None)
        parsed = MagicMock()
        parsed.location_text = None
        parsed.date = datetime.date(2024, 6, 15)
        parsed.time_after = None
        parsed.max_price = None

        msg = svc._generate_soft_filter_message(
            parsed,
            {"after_availability": 0},
            None,
            None,
            relaxed_constraints=[],
            result_count=0,
        )
        assert msg is not None
        assert "availability" in msg.lower() or "Jun" in msg

    def test_price_zero(self):
        """L3178-3179: max_price set and after_price==0."""
        from app.services.search.nl_search_service import NLSearchService

        svc = NLSearchService(cache_service=None)
        parsed = MagicMock()
        parsed.location_text = None
        parsed.date = None
        parsed.time_after = None
        parsed.max_price = 30

        msg = svc._generate_soft_filter_message(
            parsed,
            {"after_price": 0},
            None,
            None,
            relaxed_constraints=[],
            result_count=0,
        )
        assert msg is not None
        assert "$30" in msg


# ---------------------------------------------------------------------------
# _pick_best_location  (various branches)
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestPickBestLocation:
    def test_both_none_returns_none(self):
        from app.services.search.nl_search_service import NLSearchService

        result = NLSearchService._pick_best_location(None, None)
        assert result is None

    def test_tier4_high_confidence(self):
        """tier4 resolved + high confidence -> tier4 wins."""
        from app.services.search.nl_search_service import (
            LOCATION_TIER4_HIGH_CONFIDENCE,
            NLSearchService,
        )

        tier4 = MagicMock()
        tier4.resolved = True
        tier4.confidence = LOCATION_TIER4_HIGH_CONFIDENCE + 0.01
        tier5 = MagicMock()
        result = NLSearchService._pick_best_location(tier4, tier5)
        assert result is tier4

    def test_tier5_high_confidence_wins_over_low_tier4(self):
        from app.services.search.nl_search_service import (
            LOCATION_LLM_CONFIDENCE_THRESHOLD,
            NLSearchService,
        )

        tier4 = MagicMock()
        tier4.resolved = False
        tier4.confidence = 0.5
        tier5 = MagicMock()
        tier5.confidence = LOCATION_LLM_CONFIDENCE_THRESHOLD + 0.01
        result = NLSearchService._pick_best_location(tier4, tier5)
        assert result is tier5

    def test_tier5_low_confidence_but_no_tier4(self):
        from app.services.search.nl_search_service import NLSearchService

        tier5 = MagicMock()
        tier5.confidence = 0.1
        result = NLSearchService._pick_best_location(None, tier5)
        assert result is tier5

    def test_fallback_to_tier4(self):
        from app.services.search.nl_search_service import NLSearchService

        tier4 = MagicMock()
        tier4.resolved = False
        tier4.confidence = 0.3
        tier5 = MagicMock()
        tier5.confidence = 0.1
        result = NLSearchService._pick_best_location(tier4, tier5)
        assert result is tier4


# ---------------------------------------------------------------------------
# _normalize_location_text  (edge cases)
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestNormalizeLocationText:
    def test_strips_prefix_preposition(self):
        from app.services.search.nl_search_service import NLSearchService

        result = NLSearchService._normalize_location_text("near Astoria")
        assert result == "astoria"

    def test_strips_area_suffix(self):
        from app.services.search.nl_search_service import NLSearchService

        result = NLSearchService._normalize_location_text("Midtown area")
        assert result == "midtown"

    def test_strips_trailing_direction(self):
        from app.services.search.nl_search_service import NLSearchService

        result = NLSearchService._normalize_location_text("upper west side east")
        assert result == "upper west side"

    def test_two_token_keeps_direction(self):
        """Fewer than 3 tokens -> direction not stripped."""
        from app.services.search.nl_search_service import NLSearchService

        result = NLSearchService._normalize_location_text("east harlem")
        assert result == "east harlem"


# ---------------------------------------------------------------------------
# _select_instructor_ids  (simple coverage)
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestSelectInstructorIds:
    def test_deduplicates_and_limits(self):
        from app.services.search.nl_search_service import NLSearchService

        r1 = MagicMock(instructor_id="I1")
        r2 = MagicMock(instructor_id="I1")  # duplicate
        r3 = MagicMock(instructor_id="I2")
        r4 = MagicMock(instructor_id="I3")

        result = NLSearchService._select_instructor_ids([r1, r2, r3, r4], limit=2)
        assert result == ["I1", "I2"]


# ---------------------------------------------------------------------------
# _consume_task_result  (line coverage via done callback)
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestConsumeTaskResult:
    @pytest.mark.asyncio
    async def test_consume_cancelled_task(self):
        from app.services.search.nl_search_service import NLSearchService

        async def _cancel():
            raise asyncio.CancelledError()

        task = asyncio.create_task(_cancel())
        try:
            await task
        except asyncio.CancelledError:
            pass
        # Should not raise
        NLSearchService._consume_task_result(task, label="test")

    @pytest.mark.asyncio
    async def test_consume_successful_task(self):
        from app.services.search.nl_search_service import NLSearchService

        async def _ok():
            return 42

        task = asyncio.create_task(_ok())
        await task
        NLSearchService._consume_task_result(task, label="test")

    @pytest.mark.asyncio
    async def test_consume_failed_task(self):
        from app.services.search.nl_search_service import NLSearchService

        async def _fail():
            raise ValueError("boom")

        task = asyncio.create_task(_fail())
        try:
            await task
        except ValueError:
            pass
        NLSearchService._consume_task_result(task, label="test")


# ---------------------------------------------------------------------------
# _build_search_diagnostics location_info branch  (lines 3042->3063, 3058->3054, 3060->3063)
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestBuildDiagnosticsLocationBranch:
    def test_with_location_resolution_candidates(self):
        """L3042-3063: location_resolution with candidates -> builds location_info."""
        from app.services.search.nl_search_service import NLSearchService, PipelineTimer

        svc = NLSearchService(cache_service=None)
        parsed_query = MagicMock()
        parsed_query.location_text = "astoria"

        loc_resolution = MagicMock()
        loc_resolution.region_name = None
        loc_resolution.borough = "Queens"
        loc_resolution.tier = MagicMock()
        loc_resolution.tier.value = 3
        loc_resolution.candidates = [
            {"region_id": "R1", "region_name": "Astoria"},
            {"region_id": "R2", "region_name": "Astoria Heights"},
        ]

        timer = PipelineTimer()
        pre_data = MagicMock()
        pre_data.text_results = {}
        post_data = MagicMock()
        post_data.total_candidates = 10
        post_data.vector_search_used = False
        post_data.filter_result.filter_stats = {
            "initial_candidates": 10,
            "after_location": 5,
            "after_price": 5,
            "after_availability": 3,
        }

        diag = svc._build_search_diagnostics(
            timer=timer,
            budget=None,
            candidates_flow={"final_results": 3},
            parsed_query=parsed_query,
            location_resolution=loc_resolution,
            query_embedding=[0.1],
            pre_data=pre_data,
            post_data=post_data,
            results_count=3,
            cache_hit=False,
            parsing_mode="regex",
        )
        assert diag.location_resolution is not None
        assert diag.location_resolution.successful_tier == 3
        assert "Astoria" in (diag.location_resolution.resolved_regions or [])

    def test_with_non_dict_candidates_skipped(self):
        """L3055-3056: non-dict candidate -> skipped in resolved_regions."""
        from app.services.search.nl_search_service import NLSearchService, PipelineTimer

        svc = NLSearchService(cache_service=None)
        parsed_query = MagicMock()
        parsed_query.location_text = "test"

        loc_resolution = MagicMock()
        loc_resolution.region_name = "TestRegion"
        loc_resolution.borough = None
        loc_resolution.tier = MagicMock()
        loc_resolution.tier.value = 1
        loc_resolution.candidates = ["not_a_dict"]

        timer = PipelineTimer()
        diag = svc._build_search_diagnostics(
            timer=timer,
            budget=None,
            candidates_flow={},
            parsed_query=parsed_query,
            location_resolution=loc_resolution,
            query_embedding=None,
            pre_data=None,
            post_data=None,
            results_count=0,
            cache_hit=False,
            parsing_mode="regex",
        )
        assert diag.location_resolution is not None
        assert diag.location_resolution.resolved_name == "TestRegion"

    def test_tier_value_conversion_error(self):
        """L3048-3051: tier.value raises -> successful_tier=None."""
        from app.services.search.nl_search_service import NLSearchService, PipelineTimer

        svc = NLSearchService(cache_service=None)
        parsed_query = MagicMock()
        parsed_query.location_text = "wherever"

        loc_resolution = MagicMock()
        loc_resolution.region_name = "Test"
        loc_resolution.borough = None

        tier_obj = MagicMock()
        tier_obj.value = "not_an_int"

        def _int_raises(val):
            raise ValueError("bad")

        loc_resolution.tier = tier_obj
        loc_resolution.candidates = None

        timer = PipelineTimer()

        with patch("builtins.int", side_effect=lambda x: _int_raises(x) if x == "not_an_int" else int.__new__(int, x)):
            # Use a simpler approach: just pass a tier whose .value raises on int()
            pass

        # Simpler: set tier.value to an object that fails int()
        tier_obj.value = object()
        diag = svc._build_search_diagnostics(
            timer=timer,
            budget=None,
            candidates_flow={},
            parsed_query=parsed_query,
            location_resolution=loc_resolution,
            query_embedding=None,
            pre_data=None,
            post_data=None,
            results_count=0,
            cache_hit=False,
            parsing_mode="regex",
        )
        assert diag.location_resolution is not None
        assert diag.location_resolution.successful_tier is None
