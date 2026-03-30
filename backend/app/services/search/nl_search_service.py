# backend/app/services/search/nl_search_service.py
"""
Main NL search service facade that orchestrates the full search pipeline.

Pipeline stages:
1. Cache check - return cached response if available
2. Query parsing - regex fast-path or LLM for complex queries
3. Query embedding - generate vector embedding
4. Candidate retrieval - hybrid vector + text search
5. Constraint filtering - price, location, availability
6. Multi-signal ranking - quality, distance, freshness, etc.
7. Response caching - store for future requests
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Tuple, cast

from fastapi import HTTPException

from app.core.config import settings
from app.core.exceptions import raise_503_if_pool_exhaustion
from app.database import get_db_session
from app.repositories.search_batch_repository import (
    CachedAliasInfo,
    RegionLookup,
    SearchBatchRepository,
)
from app.schemas.nl_search import (
    NLSearchContentFilterDefinition,
    NLSearchResponse,
    NLSearchResultItem,
    SearchDiagnostics,
    StageStatus,
)
from app.services.search.config import get_search_config
from app.services.search.embedding_service import EmbeddingService
from app.services.search.filter_service import FilteredCandidate, FilterResult, FilterService
from app.services.search.llm_parser import hybrid_parse
from app.services.search.location_embedding_service import LocationEmbeddingService
from app.services.search.location_llm_service import LocationLLMService
from app.services.search.metrics import record_search_metrics
from app.services.search.nl_pipeline import (
    hydration,
    location,
    location_helpers,
    postflight,
    preflight,
    response,
    taxonomy,
)
from app.services.search.nl_pipeline.models import (
    LocationLLMCache,
    PipelineTimer,
    PostOpenAIData,
    PreOpenAIData,
    SearchMetrics,
    UnresolvedLocationInfo,
)
from app.services.search.nl_pipeline.runtime import (
    compute_adaptive_budget,
    decrement_inflight,
    get_cached_subcategory_filter_value,
    get_inflight_count,
    increment_inflight,
    normalize_concurrency_limit,
    set_cached_subcategory_filter_value,
)
from app.services.search.query_parser import ParsedQuery, QueryParser
from app.services.search.ranking_service import RankedResult, RankingResult, RankingService
from app.services.search.request_budget import RequestBudget
from app.services.search.retriever import (
    EMBEDDING_SOFT_TIMEOUT_MS,
    MAX_CANDIDATES,
    TEXT_REQUIRE_TEXT_MATCH_SCORE_THRESHOLD,
    TEXT_SKIP_VECTOR_MIN_RESULTS,
    TEXT_SKIP_VECTOR_SCORE_THRESHOLD,
    TEXT_TOP_K,
    TRIGRAM_GENERIC_TOKENS,
    VECTOR_TOP_K,
    PostgresRetriever,
    RetrievalResult,
    ServiceCandidate,
)
from app.services.search.search_cache import SearchCacheService
from app.services.search.taxonomy_filter_extractor import extract_inferred_filters

if TYPE_CHECKING:
    from app.services.cache_service import CacheService
    from app.services.search.location_resolver import ResolvedLocation

logger = logging.getLogger(__name__)

_PERF_LOG_ENABLED = os.getenv("NL_SEARCH_PERF_LOG") == "1"
_PERF_LOG_SLOW_MS = int(os.getenv("NL_SEARCH_PERF_LOG_SLOW_MS", "0"))

_search_inflight_lock = asyncio.Lock()
_search_inflight_requests = 0

LOCATION_LLM_TOP_K = int(os.getenv("LOCATION_LLM_TOP_K", "5"))
LOCATION_TIER4_HIGH_CONFIDENCE = float(os.getenv("LOCATION_TIER4_HIGH_CONFIDENCE", "0.85"))
LOCATION_LLM_CONFIDENCE_THRESHOLD = float(os.getenv("LOCATION_LLM_CONFIDENCE_THRESHOLD", "0.7"))
LOCATION_LLM_EMBEDDING_THRESHOLD = float(os.getenv("LOCATION_LLM_EMBEDDING_THRESHOLD", "0.7"))

TOP_MATCH_SUBCATEGORY_CANDIDATES = 5
TOP_MATCH_SUBCATEGORY_MIN_CONSENSUS = 2
SUBCATEGORY_FILTER_CACHE_TTL_SECONDS = max(
    60,
    int(os.getenv("NL_SEARCH_SUBCATEGORY_FILTER_CACHE_TTL_SECONDS", "180")),
)
SUBCATEGORY_FILTER_CACHE_MAX_ENTRIES = 512
_subcategory_filter_cache: Dict[str, Tuple[float, Any]] = {}
_subcategory_filter_cache_lock = threading.Lock()


def _get_inflight_count_value() -> int:
    return _search_inflight_requests


def _set_inflight_count_value(value: int) -> None:
    global _search_inflight_requests
    _search_inflight_requests = value


async def _increment_search_inflight() -> int:
    return await increment_inflight(
        _search_inflight_lock,
        get_count=_get_inflight_count_value,
        set_count=_set_inflight_count_value,
    )


async def _decrement_search_inflight() -> None:
    await decrement_inflight(
        _search_inflight_lock,
        get_count=_get_inflight_count_value,
        set_count=_set_inflight_count_value,
    )


def _get_adaptive_budget(inflight: int, *, force_high_load: bool = False) -> int:
    return compute_adaptive_budget(
        inflight,
        force_high_load=force_high_load,
        get_config=get_search_config,
    )


async def get_search_inflight_count() -> int:
    return await get_inflight_count(_search_inflight_lock, _get_inflight_count_value)


async def set_uncached_search_concurrency_limit(limit: int) -> int:
    return normalize_concurrency_limit(limit)


def _get_cached_subcategory_filter_value(cache_key: str) -> Tuple[bool, Any]:
    return get_cached_subcategory_filter_value(
        cache_key,
        cache=_subcategory_filter_cache,
        lock=_subcategory_filter_cache_lock,
        ttl_seconds=SUBCATEGORY_FILTER_CACHE_TTL_SECONDS,
        monotonic=time.monotonic,
    )


def _set_cached_subcategory_filter_value(cache_key: str, value: Any) -> None:
    set_cached_subcategory_filter_value(
        cache_key,
        value,
        cache=_subcategory_filter_cache,
        lock=_subcategory_filter_cache_lock,
        ttl_seconds=SUBCATEGORY_FILTER_CACHE_TTL_SECONDS,
        max_entries=SUBCATEGORY_FILTER_CACHE_MAX_ENTRIES,
        monotonic=time.monotonic,
    )


class NLSearchService:
    """Facade that keeps the public import path stable while delegating to nl_pipeline."""

    def __init__(
        self,
        cache_service: Optional["CacheService"] = None,
        search_cache: Optional[SearchCacheService] = None,
        embedding_service: Optional[EmbeddingService] = None,
        retriever: Optional[PostgresRetriever] = None,
        filter_service: Optional[FilterService] = None,
        ranking_service: Optional[RankingService] = None,
        region_code: str = "nyc",
    ) -> None:
        self._cache_service = cache_service
        self._region_code = region_code
        self.search_cache = search_cache or SearchCacheService(
            cache_service=cache_service,
            region_code=region_code,
        )
        self.embedding_service = embedding_service or EmbeddingService(cache_service=cache_service)
        self.retriever = retriever or PostgresRetriever(self.embedding_service)
        self.filter_service = filter_service or FilterService(region_code=region_code)
        self.ranking_service = ranking_service or RankingService()
        self.location_embedding_service = LocationEmbeddingService(repository=None)
        self.location_llm_service = LocationLLMService()

    @staticmethod
    def _build_candidates_flow(include_diagnostics: bool) -> Dict[str, int]:
        if not include_diagnostics:
            return {}
        return {
            "initial_candidates": 0,
            "after_text_search": 0,
            "after_vector_search": 0,
            "after_location_filter": 0,
            "after_price_filter": 0,
            "after_availability_filter": 0,
            "final_results": 0,
        }

    def _prepare_search_filters(
        self,
        *,
        explicit_skill_levels: Optional[List[str]],
        taxonomy_filter_selections: Optional[Dict[str, List[str]]],
        subcategory_id: Optional[str],
    ) -> tuple[Dict[str, List[str]], List[str], Optional[Dict[str, object]]]:
        normalized_explicit_skills = self._normalize_filter_values(explicit_skill_levels)
        effective_taxonomy_filters = self._normalize_taxonomy_filter_selections(
            taxonomy_filter_selections
        )
        if normalized_explicit_skills:
            effective_taxonomy_filters["skill_level"] = normalized_explicit_skills
        effective_skill_levels = effective_taxonomy_filters.get("skill_level", [])
        cache_filters = self._build_cache_filters(
            effective_taxonomy_filters,
            subcategory_id=subcategory_id,
        )
        return effective_taxonomy_filters, effective_skill_levels, cache_filters

    async def _cancel_task(self, task: Optional[asyncio.Task[Any]]) -> None:
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.debug("Background task failed after cancel: %s", exc)

    async def _cache_parsed_query_safe(self, query: str, parsed_query: ParsedQuery) -> None:
        try:
            await self.search_cache.cache_parsed_query(
                query,
                parsed_query,
                region_code=self._region_code,
            )
        except Exception as exc:
            logger.warning("Failed to cache parsed query: %s", exc)

    def _make_parsed_query_future(
        self,
        parsed_query_cached: Optional[ParsedQuery],
    ) -> tuple[asyncio.Future[ParsedQuery], Callable[[ParsedQuery], None]]:
        loop = asyncio.get_running_loop()
        parsed_query_future: asyncio.Future[ParsedQuery] = loop.create_future()
        if parsed_query_cached is not None:
            parsed_query_future.set_result(parsed_query_cached)

        def _notify(parsed_query: ParsedQuery) -> None:
            if parsed_query_future.done():
                return
            loop.call_soon_threadsafe(parsed_query_future.set_result, parsed_query)

        return parsed_query_future, _notify

    def _create_embedding_task(
        self,
        *,
        parsed_query_future: asyncio.Future[ParsedQuery],
        budget: RequestBudget,
        force_skip_vector_search: bool,
    ) -> Optional[asyncio.Task[tuple[Optional[List[float]], int, Optional[str]]]]:
        if force_skip_vector_search:
            budget.skip("embedding")
            budget.skip("vector_search")
            return None
        if not budget.can_afford_vector_search():
            budget.skip("embedding")
            budget.skip("vector_search")
            return None

        async def _maybe_embed_query() -> tuple[Optional[List[float]], int, Optional[str]]:
            parsed_query = await parsed_query_future
            if parsed_query.needs_llm:
                return None, 0, None
            return await self._embed_query_with_timeout(parsed_query.service_query)

        return asyncio.create_task(_maybe_embed_query())

    async def _prepare_uncached_pipeline(
        self,
        *,
        query: str,
        budget_ms: Optional[int],
        force_high_load: bool,
        force_skip_vector_search: bool,
    ) -> tuple[
        RequestBudget,
        Optional[ParsedQuery],
        asyncio.Future[ParsedQuery],
        Callable[[ParsedQuery], None],
        Optional[asyncio.Task[tuple[Optional[List[float]], int, Optional[str]]]],
    ]:
        inflight = await _increment_search_inflight()
        soft_limit = max(1, int(get_search_config().uncached_concurrency))
        if inflight > soft_limit:
            await _decrement_search_inflight()
            logger.warning(
                "[SEARCH] Soft concurrency limit reached, returning 503: query=%s",
                query[:50] if query else "",
            )
            raise HTTPException(
                status_code=503,
                detail="Search temporarily overloaded. Please retry in a few seconds.",
                headers={"Retry-After": "2"},
            )
        effective_budget_ms = (
            budget_ms
            if budget_ms is not None
            else _get_adaptive_budget(inflight, force_high_load=force_high_load)
        )
        budget = RequestBudget(total_ms=effective_budget_ms)
        parsed_query_cached: Optional[ParsedQuery] = None
        try:
            parsed_query_cached = await self.search_cache.get_cached_parsed_query(
                query,
                region_code=self._region_code,
            )
        except Exception as exc:
            logger.warning("Parsed query cache lookup failed: %s", exc)
        parsed_query_future, notify_parsed = self._make_parsed_query_future(parsed_query_cached)
        embedding_task = self._create_embedding_task(
            parsed_query_future=parsed_query_future,
            budget=budget,
            force_skip_vector_search=force_skip_vector_search,
        )
        return budget, parsed_query_cached, parsed_query_future, notify_parsed, embedding_task

    async def _run_llm_parse(
        self,
        *,
        query: str,
        parsed_query: ParsedQuery,
        user_id: Optional[str],
        metrics: SearchMetrics,
    ) -> ParsedQuery:
        from app.services.search.llm_parser import LLMParser

        llm_start = time.perf_counter()
        llm_parser = LLMParser(user_id=user_id, region_code=self._region_code)
        parsed_query = await llm_parser.parse(query, parsed_query)
        metrics.parse_latency_ms += int((time.perf_counter() - llm_start) * 1000)
        if parsed_query.parsing_mode != "llm":
            metrics.degraded = True
            metrics.degradation_reasons.append("parsing_error")
        await self._cache_parsed_query_safe(query, parsed_query)
        return parsed_query

    def _record_preflight_state(
        self,
        *,
        timer: Optional[PipelineTimer],
        pre_data: PreOpenAIData,
        pre_openai_ms: int,
        candidates_flow: Dict[str, int],
        parsed_query: ParsedQuery,
        user_location: Optional[Tuple[float, float]],
    ) -> None:
        if timer:
            location_tier_value = None
            if pre_data.location_resolution and pre_data.location_resolution.tier is not None:
                try:
                    location_tier_value = int(pre_data.location_resolution.tier.value)
                except Exception:
                    location_tier_value = None
            timer.record_stage(
                "burst1",
                pre_openai_ms,
                StageStatus.SUCCESS.value,
                {
                    "text_candidates": len(pre_data.text_results or {}),
                    "region_lookup_loaded": bool(pre_data.region_lookup),
                    "location_tier": location_tier_value,
                },
            )
        if candidates_flow:
            candidates_flow["after_text_search"] = len(pre_data.text_results or {})
        if (
            timer
            and parsed_query.location_text
            and parsed_query.location_type != "near_me"
            and user_location is None
        ):
            self._record_pre_location_tiers(timer, pre_data.location_resolution)

    def _start_speculative_tier5_task(
        self,
        *,
        parsed_query: ParsedQuery,
        pre_data: PreOpenAIData,
        user_location: Optional[Tuple[float, float]],
        budget: RequestBudget,
        force_skip_tier5: bool,
    ) -> tuple[
        Optional[
            asyncio.Task[
                tuple[
                    Optional[ResolvedLocation],
                    Optional[LocationLLMCache],
                    Optional[UnresolvedLocationInfo],
                ]
            ]
        ],
        Optional[float],
    ]:
        if (
            parsed_query.needs_llm
            or pre_data.location_resolution is not None
            or not pre_data.region_lookup
            or not pre_data.location_llm_candidates
            or not parsed_query.location_text
            or parsed_query.location_type == "near_me"
            or user_location is not None
        ):
            return None, None
        if not budget.can_afford_tier5() or force_skip_tier5:
            budget.skip("tier5_llm")
            return None, None
        started_at = time.perf_counter()
        task = asyncio.create_task(
            self._resolve_location_llm(
                location_text=parsed_query.location_text,
                original_query=parsed_query.original_query,
                region_lookup=pre_data.region_lookup,
                candidate_names=pre_data.location_llm_candidates,
            )
        )
        return task, started_at

    async def _finalize_preflight_parse(
        self,
        *,
        query: str,
        user_id: Optional[str],
        parsed_query_cached: Optional[ParsedQuery],
        parsed_query: ParsedQuery,
        embedding_task: Optional[asyncio.Task[tuple[Optional[List[float]], int, Optional[str]]]],
        metrics: SearchMetrics,
    ) -> tuple[
        ParsedQuery, Optional[asyncio.Task[tuple[Optional[List[float]], int, Optional[str]]]]
    ]:
        if parsed_query_cached is None and not parsed_query.needs_llm:
            await self._cache_parsed_query_safe(query, parsed_query)
            return parsed_query, embedding_task
        if not parsed_query.needs_llm:
            return parsed_query, embedding_task
        await self._cancel_task(embedding_task)
        parsed_query = await self._run_llm_parse(
            query=query,
            parsed_query=parsed_query,
            user_id=user_id,
            metrics=metrics,
        )
        return parsed_query, None

    async def _run_preflight_and_parse(
        self,
        *,
        query: str,
        user_id: Optional[str],
        user_location: Optional[Tuple[float, float]],
        parsed_query_cached: Optional[ParsedQuery],
        parsed_query_future: asyncio.Future[ParsedQuery],
        notify_parsed: Callable[[ParsedQuery], None],
        embedding_task: Optional[asyncio.Task[tuple[Optional[List[float]], int, Optional[str]]]],
        budget: RequestBudget,
        effective_skill_levels: List[str],
        metrics: SearchMetrics,
        timer: Optional[PipelineTimer],
        candidates_flow: Dict[str, int],
        force_skip_tier5: bool,
    ) -> tuple[
        PreOpenAIData,
        ParsedQuery,
        Optional[asyncio.Task[tuple[Optional[List[float]], int, Optional[str]]]],
        Optional[
            asyncio.Task[
                tuple[
                    Optional[ResolvedLocation],
                    Optional[LocationLLMCache],
                    Optional[UnresolvedLocationInfo],
                ]
            ]
        ],
        Optional[float],
    ]:
        pre_data, pre_openai_ms = await self._load_preflight_data(
            query=query,
            parsed_query_cached=parsed_query_cached,
            user_id=user_id,
            user_location=user_location,
            notify_parsed=notify_parsed,
            embedding_task=embedding_task,
        )
        if not parsed_query_future.done():
            parsed_query_future.set_result(pre_data.parsed_query)
        parsed_query = pre_data.parsed_query
        if effective_skill_levels:
            parsed_query.skill_level = (
                preflight.coerce_skill_level_override(effective_skill_levels[0])
                if len(effective_skill_levels) == 1
                else None
            )
        metrics.parse_latency_ms = pre_data.parse_latency_ms
        self._record_preflight_state(
            timer=timer,
            pre_data=pre_data,
            pre_openai_ms=pre_openai_ms,
            candidates_flow=candidates_flow,
            parsed_query=parsed_query,
            user_location=user_location,
        )
        tier5_task, tier5_started_at = self._start_speculative_tier5_task(
            parsed_query=parsed_query,
            pre_data=pre_data,
            user_location=user_location,
            budget=budget,
            force_skip_tier5=force_skip_tier5,
        )
        parsed_query, embedding_task = await self._finalize_preflight_parse(
            query=query,
            user_id=user_id,
            parsed_query_cached=parsed_query_cached,
            parsed_query=parsed_query,
            embedding_task=embedding_task,
            metrics=metrics,
        )
        if timer:
            timer.record_stage(
                "parse",
                metrics.parse_latency_ms,
                StageStatus.SUCCESS.value,
                {"mode": parsed_query.parsing_mode},
            )
        return pre_data, parsed_query, embedding_task, tier5_task, tier5_started_at

    async def _load_preflight_data(
        self,
        *,
        query: str,
        parsed_query_cached: Optional[ParsedQuery],
        user_id: Optional[str],
        user_location: Optional[Tuple[float, float]],
        notify_parsed: Callable[[ParsedQuery], None],
        embedding_task: Optional[asyncio.Task[tuple[Optional[List[float]], int, Optional[str]]]],
    ) -> tuple[PreOpenAIData, int]:
        pre_openai_start = time.perf_counter()
        try:
            pre_data = await asyncio.to_thread(
                self._run_pre_openai_burst,
                query,
                parsed_query=parsed_query_cached,
                user_id=user_id,
                user_location=user_location,
                notify_parsed=notify_parsed,
            )
        except Exception:
            await self._cancel_task(embedding_task)
            raise
        return pre_data, int((time.perf_counter() - pre_openai_start) * 1000)

    async def _resolve_query_embedding(
        self,
        *,
        parsed_query: ParsedQuery,
        pre_data: PreOpenAIData,
        embedding_task: Optional[asyncio.Task[tuple[Optional[List[float]], int, Optional[str]]]],
        budget: RequestBudget,
        metrics: SearchMetrics,
        timer: Optional[PipelineTimer],
        force_skip_vector: bool,
        force_skip_embedding: bool,
    ) -> tuple[Optional[List[float]], Optional[str]]:
        query_embedding: Optional[List[float]] = None
        embed_latency_ms = 0
        embedding_reason: Optional[str] = None
        budget_skip_vector = False
        force_skip_vector_search = force_skip_vector or force_skip_embedding
        if force_skip_vector_search:
            pre_data.skip_vector = True
            budget_skip_vector = True
            embedding_reason = (
                "force_skip_embedding" if force_skip_embedding else "force_skip_vector"
            )
        if not budget.can_afford_vector_search():
            budget.skip("vector_search")
            budget.skip("embedding")
            pre_data.skip_vector = True
            budget_skip_vector = True
        if pre_data.skip_vector:
            await self._cancel_task(embedding_task)
            if embedding_reason is None and budget_skip_vector:
                embedding_reason = "budget_skip_vector_search"
        elif not pre_data.has_service_embeddings:
            await self._cancel_task(embedding_task)
            embedding_reason = "no_embeddings_in_database"
        elif embedding_task is not None:
            try:
                query_embedding, embed_latency_ms, embedding_reason = await embedding_task
            except Exception as exc:
                logger.warning("[SEARCH] Embedding failed, falling back to text-only: %s", exc)
                embedding_reason = "embedding_service_unavailable"
        else:
            (
                query_embedding,
                embed_latency_ms,
                embedding_reason,
            ) = await self._embed_query_with_timeout(parsed_query.service_query)
        metrics.embed_latency_ms = embed_latency_ms
        if embedding_reason:
            metrics.degraded = True
            metrics.degradation_reasons.append(embedding_reason)
        if timer:
            if pre_data.skip_vector:
                embed_status = StageStatus.SKIPPED.value
            elif embedding_reason == "embedding_timeout":
                embed_status = StageStatus.TIMEOUT.value
            elif embedding_reason in {
                "no_embeddings_in_database",
                "budget_skip_vector_search",
                "force_skip_vector",
                "force_skip_embedding",
            }:
                embed_status = StageStatus.SKIPPED.value
            elif embedding_reason:
                embed_status = StageStatus.ERROR.value
            else:
                embed_status = StageStatus.SUCCESS.value
            timer.record_stage(
                "embedding",
                embed_latency_ms,
                embed_status,
                {"reason": embedding_reason, "used": bool(query_embedding)},
            )
        return query_embedding, embedding_reason

    async def _resolve_location_stage(
        self,
        *,
        parsed_query: ParsedQuery,
        pre_data: PreOpenAIData,
        user_location: Optional[Tuple[float, float]],
        budget: RequestBudget,
        timer: Optional[PipelineTimer],
        force_skip_tier5: bool,
        force_skip_tier4: bool,
        force_skip_embedding: bool,
        tier5_task: Optional[
            asyncio.Task[
                tuple[
                    Optional[ResolvedLocation],
                    Optional[LocationLLMCache],
                    Optional[UnresolvedLocationInfo],
                ]
            ]
        ],
        tier5_started_at: Optional[float],
    ) -> tuple[ResolvedLocation, Optional[LocationLLMCache], Optional[UnresolvedLocationInfo]]:
        from app.services.search.location_resolver import ResolvedLocation

        location_resolution = pre_data.location_resolution
        location_llm_cache: Optional[LocationLLMCache] = None
        unresolved_info: Optional[UnresolvedLocationInfo] = None
        if (
            user_location is None
            and parsed_query.location_text
            and parsed_query.location_type != "near_me"
        ):
            location_start = time.perf_counter()
            if location_resolution is None:
                allow_tier4 = (
                    budget.can_afford_tier4() and not force_skip_tier4 and not force_skip_embedding
                )
                allow_tier5 = budget.can_afford_tier5() and not force_skip_tier5
                if not allow_tier4:
                    budget.skip("tier4_embedding")
                if force_skip_tier5:
                    budget.skip("tier5_llm")
                (
                    location_resolution,
                    location_llm_cache,
                    unresolved_info,
                ) = await self._resolve_location_openai(
                    parsed_query.location_text,
                    region_lookup=pre_data.region_lookup,
                    fuzzy_score=pre_data.fuzzy_score,
                    original_query=parsed_query.original_query,
                    llm_candidates=pre_data.location_llm_candidates,
                    tier5_task=tier5_task,
                    tier5_started_at=tier5_started_at,
                    allow_tier4=allow_tier4,
                    allow_tier5=allow_tier5,
                    force_skip_tier5=force_skip_tier5,
                    budget=budget,
                    diagnostics=timer,
                )
            if location_resolution is None:
                location_resolution = ResolvedLocation.from_not_found()
            location_ms = int((time.perf_counter() - location_start) * 1000)
            if timer:
                tier_value = None
                if location_resolution and location_resolution.tier is not None:
                    try:
                        tier_value = int(location_resolution.tier.value)
                    except Exception:
                        tier_value = None
                status = (
                    StageStatus.SUCCESS.value
                    if location_resolution
                    and (location_resolution.resolved or location_resolution.requires_clarification)
                    else StageStatus.MISS.value
                )
                timer.record_stage(
                    "location_resolution",
                    location_ms,
                    status,
                    {
                        "resolved": bool(location_resolution and location_resolution.resolved),
                        "tier": tier_value,
                    },
                )
        elif timer:
            timer.skip_stage("location_resolution", "no_location")
        return (
            location_resolution or ResolvedLocation.from_not_found(),
            location_llm_cache,
            unresolved_info,
        )

    def _apply_budget_degradation(self, metrics: SearchMetrics, budget: RequestBudget) -> None:
        if not budget.is_degraded:
            return
        metrics.degraded = True
        for reason in budget.degradation_reasons:
            if reason not in metrics.degradation_reasons:
                metrics.degradation_reasons.append(reason)
        if budget.is_over_budget and "budget_overrun" not in metrics.degradation_reasons:
            metrics.degradation_reasons.append("budget_overrun")
        if budget.is_exhausted() and "budget_exhausted" not in metrics.degradation_reasons:
            metrics.degradation_reasons.append("budget_exhausted")

    async def _run_postflight_stage(
        self,
        *,
        pre_data: PreOpenAIData,
        parsed_query: ParsedQuery,
        query_embedding: Optional[List[float]],
        location_resolution: Optional[ResolvedLocation],
        location_llm_cache: Optional[LocationLLMCache],
        unresolved_info: Optional[UnresolvedLocationInfo],
        user_location: Optional[Tuple[float, float]],
        limit: int,
        requester_timezone: Optional[str],
        taxonomy_filter_selections: Optional[Dict[str, List[str]]],
        subcategory_id: Optional[str],
        embedding_reason: Optional[str],
        budget: RequestBudget,
        metrics: SearchMetrics,
        timer: Optional[PipelineTimer],
        candidates_flow: Dict[str, int],
    ) -> tuple[PostOpenAIData, RetrievalResult]:
        post_openai_start = time.perf_counter()
        post_data = await asyncio.to_thread(
            self._run_post_openai_burst,
            pre_data,
            parsed_query,
            query_embedding,
            location_resolution,
            location_llm_cache,
            unresolved_info,
            user_location,
            limit,
            requester_timezone=requester_timezone,
            taxonomy_filter_selections=taxonomy_filter_selections,
            subcategory_id=subcategory_id,
        )
        post_openai_ms = int((time.perf_counter() - post_openai_start) * 1000)
        if timer:
            timer.record_stage(
                "burst2",
                post_openai_ms,
                StageStatus.SUCCESS.value,
                {
                    "vector_search_used": post_data.vector_search_used,
                    "total_candidates": post_data.total_candidates,
                    "filter_failed": post_data.filter_failed,
                    "ranking_failed": post_data.ranking_failed,
                },
            )
        if candidates_flow:
            candidates_flow["after_vector_search"] = post_data.total_candidates
            filter_stats = post_data.filter_result.filter_stats or {}
            candidates_flow["initial_candidates"] = int(
                filter_stats.get("initial_candidates", post_data.total_candidates)
            )
            candidates_flow["after_location_filter"] = int(
                filter_stats.get("after_location", candidates_flow["after_vector_search"])
            )
            candidates_flow["after_price_filter"] = int(
                filter_stats.get("after_price", candidates_flow["after_location_filter"])
            )
            candidates_flow["after_availability_filter"] = int(
                filter_stats.get("after_availability", candidates_flow["after_price_filter"])
            )
        if embedding_reason == "no_embeddings_in_database" and post_data.skip_vector:
            embedding_reason = None
            metrics.degradation_reasons = [
                reason
                for reason in metrics.degradation_reasons
                if reason != "no_embeddings_in_database"
            ]
            if not metrics.degradation_reasons:
                metrics.degraded = False
        self._apply_budget_degradation(metrics, budget)
        metrics.retrieve_latency_ms = post_data.text_latency_ms + post_data.vector_latency_ms
        retrieval_result = RetrievalResult(
            candidates=post_data.retrieval_candidates,
            total_candidates=post_data.total_candidates,
            vector_search_used=post_data.vector_search_used,
            degraded=bool(embedding_reason),
            degradation_reason=embedding_reason,
            embed_latency_ms=metrics.embed_latency_ms,
            db_latency_ms=metrics.retrieve_latency_ms,
            text_search_latency_ms=post_data.text_latency_ms,
            vector_search_latency_ms=post_data.vector_latency_ms,
        )
        metrics.filter_latency_ms = post_data.filter_latency_ms
        metrics.rank_latency_ms = post_data.rank_latency_ms
        if post_data.filter_failed:
            metrics.degraded = True
            metrics.degradation_reasons.append("filtering_error")
        if post_data.ranking_failed:
            metrics.degraded = True
            metrics.degradation_reasons.append("ranking_error")
        return post_data, retrieval_result

    async def _hydrate_results(
        self,
        *,
        post_data: PostOpenAIData,
        limit: int,
        metrics: SearchMetrics,
        timer: Optional[PipelineTimer],
        candidates_flow: Dict[str, int],
    ) -> tuple[List[NLSearchResultItem], int]:
        hydrate_start = time.perf_counter()
        hydrate_failed = False
        try:
            results = await self._hydrate_instructor_results(
                post_data.ranking_result.results,
                limit=limit,
                location_resolution=post_data.filter_result.location_resolution,
                instructor_rows=cast(
                    List[hydration.InstructorProfileRow],
                    post_data.instructor_rows,
                ),
                distance_meters=post_data.distance_meters,
            )
        except Exception as exc:
            logger.error("Hydration failed: %s", exc)
            results = []
            hydrate_failed = True
            metrics.degraded = True
            metrics.degradation_reasons.append("hydration_error")
        hydrate_ms = int((time.perf_counter() - hydrate_start) * 1000)
        if timer:
            timer.record_stage(
                "hydrate",
                hydrate_ms,
                StageStatus.ERROR.value if hydrate_failed else StageStatus.SUCCESS.value,
                {"result_count": len(results)},
            )
        if candidates_flow:
            candidates_flow["final_results"] = len(results)
        return results, hydrate_ms

    def _build_response(
        self,
        *,
        query: str,
        parsed_query: ParsedQuery,
        results: List[NLSearchResultItem],
        limit: int,
        metrics: SearchMetrics,
        post_data: PostOpenAIData,
        budget: RequestBudget,
        timer: Optional[PipelineTimer],
    ) -> tuple[NLSearchResponse, int]:
        metrics.total_latency_ms = int((time.time() - metrics.total_start) * 1000)
        response_build_start = time.perf_counter()
        response_obj = self._build_instructor_response(
            query,
            parsed_query,
            results,
            limit,
            metrics,
            filter_result=post_data.filter_result,
            inferred_filters=post_data.inferred_filters,
            effective_subcategory_id=post_data.effective_subcategory_id,
            effective_subcategory_name=post_data.effective_subcategory_name,
            available_content_filters=post_data.available_content_filters,
            budget=budget,
        )
        response_build_ms = int((time.perf_counter() - response_build_start) * 1000)
        if timer:
            timer.record_stage(
                "build_response",
                response_build_ms,
                StageStatus.SUCCESS.value,
                {"result_count": len(response_obj.results)},
            )
        return response_obj, response_build_ms

    async def _record_metrics_and_cache(
        self,
        *,
        query: str,
        user_location: Optional[Tuple[float, float]],
        limit: int,
        parsed_query: ParsedQuery,
        response_obj: NLSearchResponse,
        metrics: SearchMetrics,
        retrieval_result: RetrievalResult,
        cache_check_ms: int,
        hydrate_ms: int,
        response_build_ms: int,
        cache_filters: Optional[Dict[str, object]],
    ) -> int:
        record_search_metrics(
            total_latency_ms=metrics.total_latency_ms,
            stage_latencies={
                "cache_check": cache_check_ms,
                "parsing": metrics.parse_latency_ms,
                "embedding": metrics.embed_latency_ms,
                "retrieval": metrics.retrieve_latency_ms,
                "filtering": metrics.filter_latency_ms,
                "ranking": metrics.rank_latency_ms,
                "hydration": hydrate_ms,
                "response_build": response_build_ms,
            },
            cache_hit=metrics.cache_hit,
            parsing_mode=parsed_query.parsing_mode,
            result_count=len(response_obj.results),
            degraded=metrics.degraded,
            degradation_reasons=metrics.degradation_reasons,
        )
        degraded_ttl = 30 if metrics.degraded else None
        cache_write_start = time.perf_counter()
        await self._cache_response(
            query,
            user_location,
            response_obj,
            limit,
            ttl=degraded_ttl,
            filters=cache_filters,
        )
        return int((time.perf_counter() - cache_write_start) * 1000)

    def _attach_diagnostics_and_perf_log(
        self,
        *,
        response_obj: NLSearchResponse,
        timer: Optional[PipelineTimer],
        budget: RequestBudget,
        parsed_query: ParsedQuery,
        pre_data: PreOpenAIData,
        post_data: PostOpenAIData,
        location_resolution: Optional[ResolvedLocation],
        query_embedding: Optional[List[float]],
        candidates_flow: Dict[str, int],
        metrics: SearchMetrics,
        retrieval_result: RetrievalResult,
        cache_check_ms: int,
        hydrate_ms: int,
        response_build_ms: int,
        cache_write_ms: int,
        limit: int,
        include_diagnostics: bool,
    ) -> None:
        if include_diagnostics and timer:
            diagnostics = self._build_search_diagnostics(
                timer=timer,
                budget=budget,
                parsed_query=parsed_query,
                pre_data=pre_data,
                post_data=post_data,
                location_resolution=location_resolution,
                query_embedding=query_embedding,
                results_count=len(response_obj.results),
                cache_hit=False,
                parsing_mode=parsed_query.parsing_mode,
                candidates_flow=candidates_flow,
                total_latency_ms=metrics.total_latency_ms,
            )
            response_obj.meta.diagnostics = diagnostics
        if _PERF_LOG_ENABLED and metrics.total_latency_ms >= _PERF_LOG_SLOW_MS:
            retrieval_stats = {
                "text_search_ms": int(getattr(retrieval_result, "text_search_latency_ms", 0) or 0),
                "vector_search_ms": int(
                    getattr(retrieval_result, "vector_search_latency_ms", 0) or 0
                ),
                "vector_used": bool(getattr(retrieval_result, "vector_search_used", False)),
                "candidates": int(getattr(retrieval_result, "total_candidates", 0) or 0),
            }
            logger.info(
                "NL search timings: %s",
                {
                    "cache_check_ms": cache_check_ms,
                    "parse_ms": metrics.parse_latency_ms,
                    "embed_ms": metrics.embed_latency_ms,
                    "retrieve_db_ms": metrics.retrieve_latency_ms,
                    "retrieve": retrieval_stats,
                    "filter_ms": metrics.filter_latency_ms,
                    "rank_ms": metrics.rank_latency_ms,
                    "hydrate_ms": hydrate_ms,
                    "response_build_ms": response_build_ms,
                    "cache_write_ms": cache_write_ms,
                    "total_ms": metrics.total_latency_ms,
                    "degraded": metrics.degraded,
                    "reasons": list(metrics.degradation_reasons),
                    "limit": limit,
                    "region": self._region_code,
                },
            )

    async def _run_pipeline_stages(
        self,
        *,
        query: str,
        user_id: Optional[str],
        user_location: Optional[Tuple[float, float]],
        limit: int,
        requester_timezone: Optional[str],
        subcategory_id: Optional[str],
        effective_filters: Dict[str, List[str]],
        effective_skill_levels: List[str],
        parsed_query_cached: Optional[ParsedQuery],
        parsed_query_future: asyncio.Future[ParsedQuery],
        notify_parsed: Callable[[ParsedQuery], None],
        embedding_task: Optional[asyncio.Task[tuple[Optional[List[float]], int, Optional[str]]]],
        budget: RequestBudget,
        metrics: SearchMetrics,
        timer: Optional[PipelineTimer],
        candidates_flow: Dict[str, int],
        force_skip_tier5: bool,
        force_skip_tier4: bool,
        force_skip_vector: bool,
        force_skip_embedding: bool,
    ) -> tuple[
        PreOpenAIData,
        ParsedQuery,
        Optional[List[float]],
        Optional[ResolvedLocation],
        Optional[LocationLLMCache],
        Optional[UnresolvedLocationInfo],
        PostOpenAIData,
        RetrievalResult,
    ]:
        (
            pre_data,
            parsed_query,
            embedding_task,
            tier5_task,
            tier5_started_at,
        ) = await self._run_preflight_and_parse(
            query=query,
            user_id=user_id,
            user_location=user_location,
            parsed_query_cached=parsed_query_cached,
            parsed_query_future=parsed_query_future,
            notify_parsed=notify_parsed,
            embedding_task=embedding_task,
            budget=budget,
            effective_skill_levels=effective_skill_levels,
            metrics=metrics,
            timer=timer,
            candidates_flow=candidates_flow,
            force_skip_tier5=force_skip_tier5,
        )
        query_embedding, embedding_reason = await self._resolve_query_embedding(
            parsed_query=parsed_query,
            pre_data=pre_data,
            embedding_task=embedding_task,
            budget=budget,
            metrics=metrics,
            timer=timer,
            force_skip_vector=force_skip_vector,
            force_skip_embedding=force_skip_embedding,
        )
        (
            location_resolution,
            location_llm_cache,
            unresolved_info,
        ) = await self._resolve_location_stage(
            parsed_query=parsed_query,
            pre_data=pre_data,
            user_location=user_location,
            budget=budget,
            timer=timer,
            force_skip_tier5=force_skip_tier5,
            force_skip_tier4=force_skip_tier4,
            force_skip_embedding=force_skip_embedding,
            tier5_task=tier5_task,
            tier5_started_at=tier5_started_at,
        )
        post_data, retrieval_result = await self._run_postflight_stage(
            pre_data=pre_data,
            parsed_query=parsed_query,
            query_embedding=query_embedding,
            location_resolution=location_resolution,
            location_llm_cache=location_llm_cache,
            unresolved_info=unresolved_info,
            user_location=user_location,
            limit=limit,
            requester_timezone=requester_timezone,
            taxonomy_filter_selections=effective_filters,
            subcategory_id=subcategory_id,
            embedding_reason=embedding_reason,
            budget=budget,
            metrics=metrics,
            timer=timer,
            candidates_flow=candidates_flow,
        )
        return (
            pre_data,
            parsed_query,
            query_embedding,
            location_resolution,
            location_llm_cache,
            unresolved_info,
            post_data,
            retrieval_result,
        )

    async def _finalize_uncached_search(
        self,
        *,
        query: str,
        user_location: Optional[Tuple[float, float]],
        limit: int,
        parsed_query: ParsedQuery,
        query_embedding: Optional[List[float]],
        location_resolution: Optional[ResolvedLocation],
        pre_data: PreOpenAIData,
        post_data: PostOpenAIData,
        metrics: SearchMetrics,
        budget: RequestBudget,
        timer: Optional[PipelineTimer],
        candidates_flow: Dict[str, int],
        retrieval_result: RetrievalResult,
        cache_check_ms: int,
        cache_filters: Optional[Dict[str, object]],
        include_diagnostics: bool,
    ) -> NLSearchResponse:
        results, hydrate_ms = await self._hydrate_results(
            post_data=post_data,
            limit=limit,
            metrics=metrics,
            timer=timer,
            candidates_flow=candidates_flow,
        )
        response_obj, response_build_ms = self._build_response(
            query=query,
            parsed_query=parsed_query,
            results=results,
            limit=limit,
            metrics=metrics,
            post_data=post_data,
            budget=budget,
            timer=timer,
        )
        cache_write_ms = await self._record_metrics_and_cache(
            query=query,
            user_location=user_location,
            limit=limit,
            parsed_query=parsed_query,
            response_obj=response_obj,
            metrics=metrics,
            retrieval_result=retrieval_result,
            cache_check_ms=cache_check_ms,
            hydrate_ms=hydrate_ms,
            response_build_ms=response_build_ms,
            cache_filters=cache_filters,
        )
        self._attach_diagnostics_and_perf_log(
            response_obj=response_obj,
            timer=timer,
            budget=budget,
            parsed_query=parsed_query,
            pre_data=pre_data,
            post_data=post_data,
            location_resolution=location_resolution,
            query_embedding=query_embedding,
            candidates_flow=candidates_flow,
            metrics=metrics,
            retrieval_result=retrieval_result,
            cache_check_ms=cache_check_ms,
            hydrate_ms=hydrate_ms,
            response_build_ms=response_build_ms,
            cache_write_ms=cache_write_ms,
            limit=limit,
            include_diagnostics=include_diagnostics,
        )
        return response_obj

    async def search(
        self,
        query: str,
        user_location: Optional[Tuple[float, float]] = None,
        limit: int = 20,
        user_id: Optional[str] = None,
        requester_timezone: Optional[str] = None,
        budget_ms: Optional[int] = None,
        *,
        explicit_skill_levels: Optional[List[str]] = None,
        subcategory_id: Optional[str] = None,
        taxonomy_filter_selections: Optional[Dict[str, List[str]]] = None,
        include_diagnostics: bool = False,
        force_skip_tier5: bool = False,
        force_skip_tier4: bool = False,
        force_skip_vector: bool = False,
        force_skip_embedding: bool = False,
        force_high_load: bool = False,
    ) -> NLSearchResponse:
        perf_start = time.perf_counter()
        metrics = SearchMetrics(total_start=time.time())
        timer = PipelineTimer() if include_diagnostics else None
        candidates_flow = self._build_candidates_flow(include_diagnostics)
        effective_filters, effective_skill_levels, cache_filters = self._prepare_search_filters(
            explicit_skill_levels=explicit_skill_levels,
            taxonomy_filter_selections=taxonomy_filter_selections,
            subcategory_id=subcategory_id,
        )
        cached, cache_check_ms = await self._get_cached_search_response(
            query=query,
            user_location=user_location,
            limit=limit,
            timer=timer,
            cache_filters=cache_filters,
        )
        if cached:
            return self._build_cached_response(
                cached=cached,
                perf_start=perf_start,
                cache_check_ms=cache_check_ms,
                timer=timer,
                candidates_flow=candidates_flow,
                include_diagnostics=include_diagnostics,
            )
        inflight_incremented = False
        try:
            (
                budget,
                parsed_query_cached,
                parsed_query_future,
                notify_parsed,
                embedding_task,
            ) = await self._prepare_uncached_pipeline(
                query=query,
                budget_ms=budget_ms,
                force_high_load=force_high_load,
                force_skip_vector_search=force_skip_vector or force_skip_embedding,
            )
            inflight_incremented = True
            (
                pre_data,
                parsed_query,
                query_embedding,
                location_resolution,
                _location_llm_cache,
                _unresolved_info,
                post_data,
                retrieval_result,
            ) = await self._run_pipeline_stages(
                query=query,
                user_id=user_id,
                user_location=user_location,
                limit=limit,
                requester_timezone=requester_timezone,
                subcategory_id=subcategory_id,
                effective_filters=effective_filters,
                effective_skill_levels=effective_skill_levels,
                parsed_query_cached=parsed_query_cached,
                parsed_query_future=parsed_query_future,
                notify_parsed=notify_parsed,
                embedding_task=embedding_task,
                budget=budget,
                metrics=metrics,
                timer=timer,
                candidates_flow=candidates_flow,
                force_skip_tier5=force_skip_tier5,
                force_skip_tier4=force_skip_tier4,
                force_skip_vector=force_skip_vector,
                force_skip_embedding=force_skip_embedding,
            )
            return await self._finalize_uncached_search(
                query=query,
                user_location=user_location,
                limit=limit,
                parsed_query=parsed_query,
                query_embedding=query_embedding,
                location_resolution=location_resolution,
                pre_data=pre_data,
                post_data=post_data,
                metrics=metrics,
                budget=budget,
                timer=timer,
                candidates_flow=candidates_flow,
                retrieval_result=retrieval_result,
                cache_check_ms=cache_check_ms,
                cache_filters=cache_filters,
                include_diagnostics=include_diagnostics,
            )
        except Exception as exc:
            raise_503_if_pool_exhaustion(exc)
            raise
        finally:
            if inflight_incremented:
                await _decrement_search_inflight()

    async def _get_cached_search_response(
        self,
        *,
        query: str,
        user_location: Optional[Tuple[float, float]],
        limit: int,
        timer: Optional[PipelineTimer],
        cache_filters: Optional[Dict[str, object]],
    ) -> tuple[Optional[Dict[str, object]], int]:
        if timer:
            timer.start_stage("cache_check")
        cache_check_start = time.perf_counter()
        cached = await self._check_cache(query, user_location, limit, filters=cache_filters)
        cache_check_ms = int((time.perf_counter() - cache_check_start) * 1000)
        if timer:
            timer.end_stage(
                status=StageStatus.CACHE_HIT.value if cached else StageStatus.SUCCESS.value,
                details={"latency_ms": cache_check_ms},
            )
        return cached, cache_check_ms

    def _build_cached_response(
        self,
        *,
        cached: Dict[str, object],
        perf_start: float,
        cache_check_ms: int,
        timer: Optional[PipelineTimer],
        candidates_flow: Dict[str, int],
        include_diagnostics: bool,
    ) -> NLSearchResponse:
        cached_total_ms = int((time.perf_counter() - perf_start) * 1000)
        meta_obj = cached.get("meta")
        if not isinstance(meta_obj, dict):
            meta_obj = {}
            cached["meta"] = meta_obj
        meta = cast(Dict[str, object], meta_obj)
        meta["cache_hit"] = True
        meta["latency_ms"] = cached_total_ms
        results_obj = cached.get("results")
        cached_results = results_obj if isinstance(results_obj, list) else []
        record_search_metrics(
            total_latency_ms=cached_total_ms,
            stage_latencies={"cache_check": cache_check_ms},
            cache_hit=True,
            parsing_mode=str(meta.get("parsing_mode") or "regex"),
            result_count=len(cached_results),
            degraded=False,
            degradation_reasons=[],
        )
        if _PERF_LOG_ENABLED and cached_total_ms >= _PERF_LOG_SLOW_MS:
            logger.info(
                "NL search timings (cache_hit): %s",
                {
                    "cache_check_ms": cache_check_ms,
                    "total_ms": cached_total_ms,
                    "limit": meta.get("limit", 0),
                    "region": self._region_code,
                },
            )
        response_obj = NLSearchResponse(**cached)
        if include_diagnostics and timer:
            response_obj.meta.diagnostics = self._build_search_diagnostics(
                timer=timer,
                budget=None,
                parsed_query=None,
                pre_data=None,
                post_data=None,
                location_resolution=None,
                query_embedding=None,
                results_count=len(response_obj.results),
                cache_hit=True,
                parsing_mode=str(response_obj.meta.parsing_mode or "regex"),
                candidates_flow=candidates_flow,
                total_latency_ms=cached_total_ms,
            )
        return response_obj

    def _normalize_filter_values(self, values: Optional[List[str]]) -> List[str]:
        return preflight.normalize_filter_values(values)

    def _normalize_taxonomy_filter_selections(
        self,
        selections: Optional[Dict[str, List[str]]],
    ) -> Dict[str, List[str]]:
        return preflight.normalize_taxonomy_filter_selections(selections)

    def _load_subcategory_filter_metadata(
        self,
        taxonomy_repository: object,
        subcategory_id: str,
    ) -> Tuple[List[Dict[str, object]], Optional[str]]:
        return taxonomy.load_subcategory_filter_metadata(
            taxonomy_repository,
            subcategory_id,
            get_cached_value=_get_cached_subcategory_filter_value,
            set_cached_value=_set_cached_subcategory_filter_value,
        )

    @staticmethod
    def _build_available_content_filters(
        filter_definitions: List[Dict[str, object]],
    ) -> List[NLSearchContentFilterDefinition]:
        return taxonomy.build_available_content_filters(filter_definitions)

    def _build_cache_filters(
        self,
        taxonomy_filters: Dict[str, List[str]],
        *,
        subcategory_id: Optional[str],
    ) -> Optional[Dict[str, object]]:
        return preflight.build_cache_filters(taxonomy_filters, subcategory_id=subcategory_id)

    @staticmethod
    def _resolve_effective_subcategory_id(
        candidates: List[ServiceCandidate],
        explicit_subcategory_id: Optional[str] = None,
    ) -> Optional[str]:
        return taxonomy.resolve_effective_subcategory_id(
            candidates,
            explicit_subcategory_id=explicit_subcategory_id,
            top_match_subcategory_candidates=TOP_MATCH_SUBCATEGORY_CANDIDATES,
            top_match_subcategory_min_consensus=TOP_MATCH_SUBCATEGORY_MIN_CONSENSUS,
        )

    @staticmethod
    def _normalize_location_text(text_value: str) -> str:
        return location_helpers.normalize_location_text(text_value)

    @staticmethod
    def _record_pre_location_tiers(
        timer: PipelineTimer,
        location_resolution: Optional[ResolvedLocation],
    ) -> None:
        location_helpers.record_pre_location_tiers(timer, location_resolution)

    @staticmethod
    def _compute_text_match_flags(
        service_query: str,
        text_results: Dict[str, Tuple[float, Dict[str, object]]],
    ) -> tuple[float, bool, bool]:
        return preflight.compute_text_match_flags(
            service_query,
            text_results,
            trigram_generic_tokens=TRIGRAM_GENERIC_TOKENS,
            require_text_match_score_threshold=TEXT_REQUIRE_TEXT_MATCH_SCORE_THRESHOLD,
            skip_vector_min_results=TEXT_SKIP_VECTOR_MIN_RESULTS,
            skip_vector_score_threshold=TEXT_SKIP_VECTOR_SCORE_THRESHOLD,
        )

    @staticmethod
    def _resolve_cached_alias(
        cached_alias: CachedAliasInfo,
        region_lookup: RegionLookup,
    ) -> Optional[ResolvedLocation]:
        return location_helpers.resolve_cached_alias(cached_alias, region_lookup)

    @staticmethod
    def _select_instructor_ids(ranked: List[RankedResult], limit: int) -> List[str]:
        return postflight.select_instructor_ids(ranked, limit)

    @staticmethod
    def _distance_region_ids(
        location_resolution: Optional[ResolvedLocation],
    ) -> Optional[List[str]]:
        return location_helpers.distance_region_ids(location_resolution)

    @staticmethod
    def _consume_task_result(task: asyncio.Task[Any], *, label: str) -> None:
        location_helpers.consume_task_result(task, label=label, logger=logger)

    @staticmethod
    def _pick_best_location(
        tier4_result: Optional[ResolvedLocation],
        tier5_result: Optional[ResolvedLocation],
    ) -> Optional[ResolvedLocation]:
        return location_helpers.pick_best_location(
            tier4_result,
            tier5_result,
            tier4_high_confidence=LOCATION_TIER4_HIGH_CONFIDENCE,
            llm_confidence_threshold=LOCATION_LLM_CONFIDENCE_THRESHOLD,
        )

    async def _resolve_location_llm(
        self,
        *,
        location_text: str,
        original_query: Optional[str],
        region_lookup: RegionLookup,
        candidate_names: List[str],
        timeout_s: Optional[float] = None,
        normalized: Optional[str] = None,
    ) -> tuple[
        Optional[ResolvedLocation], Optional[LocationLLMCache], Optional[UnresolvedLocationInfo]
    ]:
        return await location.resolve_location_llm(
            location_llm_service=self.location_llm_service,
            location_text=location_text,
            original_query=original_query,
            region_lookup=region_lookup,
            candidate_names=candidate_names,
            timeout_s=timeout_s,
            normalized=normalized,
        )

    async def _embed_query_with_timeout(
        self,
        query: str,
    ) -> tuple[Optional[List[float]], int, Optional[str]]:
        return await preflight.embed_query_with_timeout(
            query,
            asyncio_module=asyncio,
            embedding_service=self.embedding_service,
            get_config=get_search_config,
            embedding_soft_timeout_ms=EMBEDDING_SOFT_TIMEOUT_MS,
        )

    def _run_pre_openai_burst(
        self,
        query: str,
        *,
        parsed_query: Optional[ParsedQuery],
        user_id: Optional[str],
        user_location: Optional[Tuple[float, float]],
        notify_parsed: Optional[Callable[[ParsedQuery], None]] = None,
    ) -> PreOpenAIData:
        from app.services.search.location_resolver import LocationResolver

        return preflight.run_pre_openai_burst(
            get_db_session=get_db_session,
            search_batch_repository_cls=SearchBatchRepository,
            query=query,
            parsed_query=parsed_query,
            user_id=user_id,
            user_location=user_location,
            notify_parsed=notify_parsed,
            region_code=self._region_code,
            query_parser_cls=QueryParser,
            retriever=self.retriever,
            location_resolver_cls=LocationResolver,
            normalize_location_text=self._normalize_location_text,
            resolve_cached_alias=self._resolve_cached_alias,
            location_llm_top_k=LOCATION_LLM_TOP_K,
            trigram_generic_tokens=TRIGRAM_GENERIC_TOKENS,
            require_text_match_score_threshold=TEXT_REQUIRE_TEXT_MATCH_SCORE_THRESHOLD,
            skip_vector_min_results=TEXT_SKIP_VECTOR_MIN_RESULTS,
            skip_vector_score_threshold=TEXT_SKIP_VECTOR_SCORE_THRESHOLD,
            text_top_k=TEXT_TOP_K,
            max_candidates=MAX_CANDIDATES,
            logger=logger,
        )

    async def _resolve_location_openai(
        self,
        location_text: str,
        *,
        region_lookup: Optional[RegionLookup],
        fuzzy_score: Optional[float],
        original_query: Optional[str],
        llm_candidates: Optional[List[str]] = None,
        tier5_task: Optional[
            asyncio.Task[
                tuple[
                    Optional[ResolvedLocation],
                    Optional[LocationLLMCache],
                    Optional[UnresolvedLocationInfo],
                ]
            ]
        ] = None,
        tier5_started_at: Optional[float] = None,
        allow_tier4: bool = True,
        allow_tier5: bool = True,
        force_skip_tier5: bool = False,
        budget: Optional[RequestBudget] = None,
        diagnostics: Optional[PipelineTimer] = None,
    ) -> tuple[ResolvedLocation, Optional[LocationLLMCache], Optional[UnresolvedLocationInfo]]:
        return await location.resolve_location_openai(
            location_text=location_text,
            region_lookup=region_lookup,
            fuzzy_score=fuzzy_score,
            original_query=original_query,
            llm_candidates=llm_candidates,
            tier5_task=tier5_task,
            tier5_started_at=tier5_started_at,
            allow_tier4=allow_tier4,
            allow_tier5=allow_tier5,
            force_skip_tier5=force_skip_tier5,
            budget=budget,
            diagnostics=diagnostics,
            location_embedding_service=self.location_embedding_service,
            resolve_location_llm_fn=self._resolve_location_llm,
            get_config=get_search_config,
            logger=logger,
            tier4_high_confidence=LOCATION_TIER4_HIGH_CONFIDENCE,
            llm_confidence_threshold=LOCATION_LLM_CONFIDENCE_THRESHOLD,
            location_llm_top_k=LOCATION_LLM_TOP_K,
            llm_embedding_threshold=LOCATION_LLM_EMBEDDING_THRESHOLD,
        )

    def _run_post_openai_burst(
        self,
        pre_data: PreOpenAIData,
        parsed_query: ParsedQuery,
        query_embedding: Optional[List[float]],
        location_resolution: Optional[ResolvedLocation],
        location_llm_cache: Optional[LocationLLMCache],
        unresolved_info: Optional[UnresolvedLocationInfo],
        user_location: Optional[Tuple[float, float]],
        limit: int,
        requester_timezone: Optional[str] = None,
        taxonomy_filter_selections: Optional[Dict[str, List[str]]] = None,
        subcategory_id: Optional[str] = None,
    ) -> PostOpenAIData:
        from app.repositories.filter_repository import FilterRepository
        from app.repositories.ranking_repository import RankingRepository
        from app.repositories.retriever_repository import RetrieverRepository
        from app.repositories.taxonomy_filter_repository import TaxonomyFilterRepository
        from app.repositories.unresolved_location_query_repository import (
            UnresolvedLocationQueryRepository,
        )
        from app.services.search.location_resolver import LocationResolver

        return postflight.run_post_openai_burst(
            get_db_session=get_db_session,
            search_batch_repository_cls=SearchBatchRepository,
            pre_data=pre_data,
            parsed_query=parsed_query,
            query_embedding=query_embedding,
            location_resolution=location_resolution,
            location_llm_cache=location_llm_cache,
            unresolved_info=unresolved_info,
            user_location=user_location,
            limit=limit,
            requester_timezone=requester_timezone,
            taxonomy_filter_selections=taxonomy_filter_selections,
            subcategory_id=subcategory_id,
            retriever=self.retriever,
            compute_text_match_flags=self._compute_text_match_flags,
            normalize_taxonomy_filter_selections=self._normalize_taxonomy_filter_selections,
            resolve_effective_subcategory_id_fn=self._resolve_effective_subcategory_id,
            load_subcategory_filter_metadata_fn=self._load_subcategory_filter_metadata,
            build_available_content_filters_fn=self._build_available_content_filters,
            select_instructor_ids_fn=self._select_instructor_ids,
            distance_region_ids_fn=self._distance_region_ids,
            filter_service_cls=FilterService,
            ranking_service_cls=RankingService,
            filter_repository_cls=FilterRepository,
            ranking_repository_cls=RankingRepository,
            retriever_repository_cls=RetrieverRepository,
            taxonomy_filter_repository_cls=TaxonomyFilterRepository,
            unresolved_location_query_repository_cls=UnresolvedLocationQueryRepository,
            location_resolver_cls=LocationResolver,
            extract_inferred_filters=extract_inferred_filters,
            region_code=self._region_code,
            text_top_k=TEXT_TOP_K,
            vector_top_k=VECTOR_TOP_K,
            max_candidates=MAX_CANDIDATES,
            logger=logger,
        )

    @staticmethod
    def _serialize_format_prices(
        price_rows: List[Any],
    ) -> List[hydration.SerializedFormatPrice]:
        return hydration.serialize_format_prices(price_rows)

    @staticmethod
    def _derive_service_offers(
        format_prices: List[hydration.SerializedFormatPrice],
    ) -> Dict[str, bool]:
        return hydration.derive_service_offers(format_prices)

    async def _hydrate_instructor_results(
        self,
        ranked: List[RankedResult],
        limit: int,
        *,
        location_resolution: Optional[ResolvedLocation] = None,
        instructor_rows: Optional[List[hydration.InstructorProfileRow]] = None,
        distance_meters: Optional[Dict[str, float]] = None,
    ) -> List[NLSearchResultItem]:
        from app.repositories.filter_repository import FilterRepository
        from app.repositories.retriever_repository import RetrieverRepository
        from app.repositories.service_format_pricing_repository import (
            ServiceFormatPricingRepository,
        )

        return await hydration.hydrate_instructor_results(
            ranked=ranked,
            limit=limit,
            location_resolution=location_resolution,
            instructor_rows=instructor_rows,
            distance_meters=distance_meters,
            asyncio_module=asyncio,
            get_db_session=get_db_session,
            pricing_repository_cls=ServiceFormatPricingRepository,
            retriever_repository_cls=RetrieverRepository,
            filter_repository_cls=FilterRepository,
        )

    async def _check_cache(
        self,
        query: str,
        user_location: Optional[Tuple[float, float]],
        limit: int,
        *,
        filters: Optional[Dict[str, object]] = None,
    ) -> Optional[Dict[str, object]]:
        return await response.check_cache(
            search_cache=self.search_cache,
            query=query,
            user_location=user_location,
            limit=limit,
            region_code=self._region_code,
            logger=logger,
            filters=filters,
        )

    async def _parse_query(
        self,
        query: str,
        metrics: SearchMetrics,
        user_id: Optional[str] = None,
    ) -> ParsedQuery:
        start = time.time()
        try:
            cached_parsed = await self.search_cache.get_cached_parsed_query(
                query,
                region_code=self._region_code,
            )
            if cached_parsed:
                metrics.parse_latency_ms = int((time.time() - start) * 1000)
                return cached_parsed
            parsed = await hybrid_parse(query, user_id=user_id, region_code=self._region_code)
            await self.search_cache.cache_parsed_query(query, parsed, region_code=self._region_code)
        except Exception as exc:
            logger.error("Parsing failed, using basic extraction: %s", exc)

            def _parse_regex_fallback() -> ParsedQuery:
                with get_db_session() as db:
                    parser = QueryParser(db, user_id=user_id, region_code=self._region_code)
                    return parser.parse(query)

            parsed = await asyncio.to_thread(_parse_regex_fallback)
            metrics.degraded = True
            metrics.degradation_reasons.append("parsing_error")
        metrics.parse_latency_ms = int((time.time() - start) * 1000)
        return parsed

    async def _retrieve_candidates(
        self,
        parsed_query: ParsedQuery,
        metrics: SearchMetrics,
    ) -> RetrievalResult:
        start = time.time()
        try:
            result = await self.retriever.search(parsed_query)
            if result.degraded:
                metrics.degraded = True
                if result.degradation_reason:
                    metrics.degradation_reasons.append(result.degradation_reason)
        except Exception as exc:
            logger.error("Retrieval failed: %s", exc)
            result = RetrievalResult(
                candidates=[],
                total_candidates=0,
                vector_search_used=False,
                degraded=True,
                degradation_reason="retrieval_error",
            )
            metrics.degraded = True
            metrics.degradation_reasons.append("retrieval_error")
        total_ms = int((time.time() - start) * 1000)
        metrics.embed_latency_ms = int(getattr(result, "embed_latency_ms", 0) or 0)
        metrics.retrieve_latency_ms = int(getattr(result, "db_latency_ms", 0) or 0) or max(
            0,
            total_ms - metrics.embed_latency_ms,
        )
        return result

    async def _filter_candidates(
        self,
        retrieval_result: RetrievalResult,
        parsed_query: ParsedQuery,
        user_location: Optional[Tuple[float, float]],
        metrics: SearchMetrics,
        *,
        requester_timezone: Optional[str] = None,
    ) -> FilterResult:
        start = time.time()
        try:
            result = await self.filter_service.filter_candidates(
                retrieval_result.candidates,
                parsed_query,
                user_location=user_location,
                requester_timezone=requester_timezone,
            )
        except Exception as exc:
            logger.error("Filtering failed: %s", exc)
            result = FilterResult(
                candidates=[
                    FilteredCandidate(
                        service_id=candidate.service_id,
                        service_catalog_id=candidate.service_catalog_id,
                        instructor_id=candidate.instructor_id,
                        hybrid_score=candidate.hybrid_score,
                        name=candidate.name,
                        description=candidate.description,
                        min_hourly_rate=candidate.min_hourly_rate,
                    )
                    for candidate in retrieval_result.candidates
                ],
                total_before_filter=len(retrieval_result.candidates),
                total_after_filter=len(retrieval_result.candidates),
                filters_applied=[],
                soft_filtering_used=False,
            )
            metrics.degraded = True
            metrics.degradation_reasons.append("filtering_error")
        metrics.filter_latency_ms = int((time.time() - start) * 1000)
        return result

    def _rank_results(
        self,
        filter_result: FilterResult,
        parsed_query: ParsedQuery,
        user_location: Optional[Tuple[float, float]],
        metrics: SearchMetrics,
    ) -> RankingResult:
        start = time.time()
        try:
            result = self.ranking_service.rank_candidates(
                filter_result.candidates,
                parsed_query,
                user_location=user_location,
            )
        except Exception as exc:
            logger.error("Ranking failed: %s", exc)
            result = RankingResult(
                results=[
                    RankedResult(
                        service_id=candidate.service_id,
                        service_catalog_id=candidate.service_catalog_id,
                        instructor_id=candidate.instructor_id,
                        name=candidate.name,
                        description=candidate.description,
                        min_hourly_rate=candidate.min_hourly_rate,
                        effective_hourly_rate=candidate.effective_hourly_rate,
                        final_score=candidate.hybrid_score,
                        rank=index + 1,
                        relevance_score=candidate.hybrid_score,
                        quality_score=0.5,
                        distance_score=0.5,
                        price_score=0.5,
                        freshness_score=0.5,
                        completeness_score=0.5,
                        available_dates=list(candidate.available_dates),
                        earliest_available=candidate.earliest_available,
                    )
                    for index, candidate in enumerate(filter_result.candidates)
                ],
                total_results=len(filter_result.candidates),
            )
            metrics.degraded = True
            metrics.degradation_reasons.append("ranking_error")
        metrics.rank_latency_ms = int((time.time() - start) * 1000)
        return result

    async def _cache_response(
        self,
        query: str,
        user_location: Optional[Tuple[float, float]],
        response_obj: NLSearchResponse,
        limit: int,
        *,
        ttl: Optional[int] = None,
        filters: Optional[Dict[str, object]] = None,
    ) -> None:
        await response.cache_response(
            search_cache=self.search_cache,
            query=query,
            user_location=user_location,
            response=response_obj,
            limit=limit,
            region_code=self._region_code,
            logger=logger,
            ttl=ttl,
            filters=filters,
        )

    def _transform_instructor_results(
        self,
        raw_results: List[hydration.RawInstructorResultRow],
        parsed_query: ParsedQuery,
    ) -> List[NLSearchResultItem]:
        from app.repositories.service_format_pricing_repository import (
            ServiceFormatPricingRepository,
        )

        return hydration.transform_instructor_results(
            raw_results=raw_results,
            parsed_query=parsed_query,
            get_db_session=get_db_session,
            pricing_repository_cls=ServiceFormatPricingRepository,
        )

    def _build_instructor_response(
        self,
        query: str,
        parsed_query: ParsedQuery,
        results: List[NLSearchResultItem],
        limit: int,
        metrics: SearchMetrics,
        *,
        filter_result: Optional[FilterResult] = None,
        inferred_filters: Optional[Dict[str, List[str]]] = None,
        effective_subcategory_id: Optional[str] = None,
        effective_subcategory_name: Optional[str] = None,
        available_content_filters: Optional[List[NLSearchContentFilterDefinition]] = None,
        budget: Optional[RequestBudget] = None,
    ) -> NLSearchResponse:
        return response.build_instructor_response(
            query=query,
            parsed_query=parsed_query,
            results=results,
            limit=limit,
            metrics=metrics,
            filter_result=filter_result,
            inferred_filters=inferred_filters,
            effective_subcategory_id=effective_subcategory_id,
            effective_subcategory_name=effective_subcategory_name,
            available_content_filters=available_content_filters,
            budget=budget,
        )

    def _build_search_diagnostics(
        self,
        *,
        timer: PipelineTimer,
        budget: Optional[RequestBudget],
        parsed_query: Optional[ParsedQuery],
        pre_data: Optional[PreOpenAIData],
        post_data: Optional[PostOpenAIData],
        location_resolution: Optional[ResolvedLocation],
        query_embedding: Optional[List[float]],
        results_count: int,
        cache_hit: bool,
        parsing_mode: str,
        candidates_flow: Dict[str, int],
        total_latency_ms: Optional[int] = None,
    ) -> SearchDiagnostics:
        return response.build_search_diagnostics(
            timer=timer,
            budget=budget,
            parsed_query=parsed_query,
            pre_data=pre_data,
            post_data=post_data,
            location_resolution=location_resolution,
            query_embedding=query_embedding,
            results_count=results_count,
            cache_hit=cache_hit,
            parsing_mode=parsing_mode,
            candidates_flow=candidates_flow,
            get_search_config=get_search_config,
            total_latency_ms=total_latency_ms,
        )

    def _format_location_resolved(
        self,
        location_resolution: Optional[ResolvedLocation],
    ) -> Optional[str]:
        return response.format_location_resolved(location_resolution)

    def _generate_soft_filter_message(
        self,
        parsed: ParsedQuery,
        filter_stats: Dict[str, int],
        location_resolution: Optional[ResolvedLocation],
        location_resolved: Optional[str],
        *,
        relaxed_constraints: List[str],
        result_count: int,
    ) -> Optional[str]:
        return response.generate_soft_filter_message(
            parsed=parsed,
            filter_stats=filter_stats,
            location_resolution=location_resolution,
            location_resolved=location_resolved,
            relaxed_constraints=relaxed_constraints,
            result_count=result_count,
        )

    def _build_photo_url(self, key: Optional[str]) -> Optional[str]:
        return hydration.build_photo_url(
            key, assets_domain=getattr(settings, "r2_public_url", None)
        )
