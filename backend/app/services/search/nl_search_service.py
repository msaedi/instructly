# backend/app/services/search/nl_search_service.py
"""
Main NL search service that orchestrates the full search pipeline.

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
from dataclasses import dataclass, field
import logging
import os
import time
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Tuple

from fastapi import HTTPException

from app.core.config import settings
from app.database import get_db_session
from app.repositories.search_batch_repository import (
    CachedAliasInfo,
    RegionInfo,
    RegionLookup,
    SearchBatchRepository,
)
from app.schemas.nl_search import (
    BudgetInfo,
    InstructorSummary,
    LocationResolutionInfo,
    LocationTierResult,
    NLSearchMeta,
    NLSearchResponse,
    NLSearchResultItem,
    ParsedQueryInfo,
    PipelineStage,
    RatingSummary,
    SearchDiagnostics,
    ServiceMatch,
    StageStatus,
)
from app.services.search.config import get_search_config
from app.services.search.embedding_service import EmbeddingService
from app.services.search.filter_service import FilteredCandidate, FilterResult, FilterService
from app.services.search.llm_parser import hybrid_parse
from app.services.search.location_embedding_service import LocationEmbeddingService
from app.services.search.location_llm_service import LocationLLMService
from app.services.search.metrics import record_search_metrics
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

if TYPE_CHECKING:
    from app.services.cache_service import CacheService
    from app.services.search.location_resolver import ResolvedLocation

logger = logging.getLogger(__name__)

# Optional perf logging for profiling in staging/dev.
_PERF_LOG_ENABLED = os.getenv("NL_SEARCH_PERF_LOG") == "1"
_PERF_LOG_SLOW_MS = int(os.getenv("NL_SEARCH_PERF_LOG_SLOW_MS", "0"))

# Concurrency control for uncached searches.
# Soft limit only; expensive OpenAI calls are gated separately.

_search_inflight_lock = asyncio.Lock()
_search_inflight_requests = 0


async def _increment_search_inflight() -> int:
    global _search_inflight_requests
    async with _search_inflight_lock:
        _search_inflight_requests += 1
        return _search_inflight_requests


async def _decrement_search_inflight() -> None:
    global _search_inflight_requests
    async with _search_inflight_lock:
        _search_inflight_requests = max(0, _search_inflight_requests - 1)


def _get_adaptive_budget(inflight: int, *, force_high_load: bool = False) -> int:
    config = get_search_config()
    if force_high_load or inflight >= int(config.high_load_threshold):
        return int(config.high_load_budget_ms)
    return int(config.search_budget_ms)


async def get_search_inflight_count() -> int:
    async with _search_inflight_lock:
        return _search_inflight_requests


async def set_uncached_search_concurrency_limit(limit: int) -> int:
    """Return the normalized soft concurrency limit."""
    return max(1, int(limit))


# Location resolution tuning.
LOCATION_LLM_TOP_K = int(os.getenv("LOCATION_LLM_TOP_K", "5"))
LOCATION_TIER4_HIGH_CONFIDENCE = float(os.getenv("LOCATION_TIER4_HIGH_CONFIDENCE", "0.85"))
LOCATION_LLM_CONFIDENCE_THRESHOLD = float(os.getenv("LOCATION_LLM_CONFIDENCE_THRESHOLD", "0.7"))
LOCATION_LLM_EMBEDDING_THRESHOLD = float(os.getenv("LOCATION_LLM_EMBEDDING_THRESHOLD", "0.7"))


@dataclass
class SearchMetrics:
    """Metrics collected during search execution."""

    total_start: float = 0
    parse_latency_ms: int = 0
    embed_latency_ms: int = 0
    retrieve_latency_ms: int = 0
    filter_latency_ms: int = 0
    rank_latency_ms: int = 0
    total_latency_ms: int = 0
    cache_hit: bool = False
    degraded: bool = False
    degradation_reasons: List[str] = field(default_factory=list)


@dataclass
class PipelineTimer:
    """Collect timing data for diagnostics."""

    stages: List[Dict[str, Any]] = field(default_factory=list)
    location_tiers: List[Dict[str, Any]] = field(default_factory=list)
    _current_stage_name: Optional[str] = None
    _current_stage_start: Optional[float] = None

    def start_stage(self, name: str) -> None:
        self._current_stage_name = name
        self._current_stage_start = time.perf_counter()

    def end_stage(self, status: str = "success", details: Optional[Dict[str, Any]] = None) -> None:
        if self._current_stage_start is None or self._current_stage_name is None:
            return
        duration_ms = int((time.perf_counter() - self._current_stage_start) * 1000)
        self.stages.append(
            {
                "name": self._current_stage_name,
                "duration_ms": max(0, duration_ms),
                "status": status,
                "details": details or {},
            }
        )
        self._current_stage_name = None
        self._current_stage_start = None

    def record_stage(
        self,
        name: str,
        duration_ms: int,
        status: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.stages.append(
            {
                "name": name,
                "duration_ms": max(0, int(duration_ms)),
                "status": status,
                "details": details or {},
            }
        )

    def skip_stage(self, name: str, reason: str) -> None:
        self.record_stage(name, 0, StageStatus.SKIPPED.value, {"reason": reason})

    def record_location_tier(
        self,
        *,
        tier: int,
        attempted: bool,
        status: str,
        duration_ms: int,
        result: Optional[str] = None,
        confidence: Optional[float] = None,
        details: Optional[str] = None,
    ) -> None:
        self.location_tiers.append(
            {
                "tier": tier,
                "attempted": attempted,
                "status": status,
                "duration_ms": max(0, int(duration_ms)),
                "result": result,
                "confidence": confidence,
                "details": details,
            }
        )


@dataclass
class PreOpenAIData:
    """DB-backed data collected before OpenAI calls."""

    parsed_query: ParsedQuery
    parse_latency_ms: int
    text_results: Optional[Dict[str, Tuple[float, Dict[str, Any]]]]
    text_latency_ms: int
    has_service_embeddings: bool
    best_text_score: float
    require_text_match: bool
    skip_vector: bool
    region_lookup: Optional[RegionLookup]
    location_resolution: Optional["ResolvedLocation"]
    location_normalized: Optional[str]
    cached_alias_normalized: Optional[str]
    fuzzy_score: Optional[float]
    location_llm_candidates: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class LocationLLMCache:
    """LLM-derived alias cache payload to persist in DB burst."""

    normalized: str
    confidence: float
    region_ids: List[str]


@dataclass(frozen=True)
class UnresolvedLocationInfo:
    """Unresolved location payload to persist in DB burst."""

    normalized: str
    original_query: str


@dataclass
class PostOpenAIData:
    """DB-backed data collected after OpenAI calls."""

    filter_result: FilterResult
    ranking_result: RankingResult
    retrieval_candidates: List[ServiceCandidate]
    instructor_rows: List[Dict[str, Any]]
    distance_meters: Dict[str, float]
    text_latency_ms: int
    vector_latency_ms: int
    filter_latency_ms: int
    rank_latency_ms: int
    vector_search_used: bool
    total_candidates: int
    filter_failed: bool
    ranking_failed: bool
    skip_vector: bool


class NLSearchService:
    """
    Orchestrates the full NL search pipeline.

    Pipeline stages:
    1. Cache check
    2. Query parsing (regex → LLM fallback)
    3. Query embedding
    4. Candidate retrieval (vector + text)
    5. Constraint filtering
    6. Multi-signal ranking
    7. Response caching

    All stages support graceful degradation.
    Supports multi-region architecture via region_code parameter.
    """

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

        # Initialize search cache
        self.search_cache = search_cache or SearchCacheService(
            cache_service=cache_service, region_code=region_code
        )

        # Initialize embedding service
        self.embedding_service = embedding_service or EmbeddingService(cache_service=cache_service)

        # Initialize pipeline components (DB sessions are acquired per operation)
        self.retriever = retriever or PostgresRetriever(self.embedding_service)
        self.filter_service = filter_service or FilterService(region_code=region_code)
        self.ranking_service = ranking_service or RankingService()
        self.location_embedding_service = LocationEmbeddingService(repository=None)
        self.location_llm_service = LocationLLMService()

    async def search(
        self,
        query: str,
        user_location: Optional[Tuple[float, float]] = None,
        limit: int = 20,
        user_id: Optional[str] = None,
        budget_ms: Optional[int] = None,
        *,
        include_diagnostics: bool = False,
        force_skip_tier5: bool = False,
        force_skip_tier4: bool = False,
        force_skip_vector: bool = False,
        force_skip_embedding: bool = False,
        force_high_load: bool = False,
    ) -> NLSearchResponse:
        """
        Execute full NL search pipeline and return instructor-level results.

        Pipeline:
        1. Cache check
        2. Parse query (regex → LLM as needed)
        3. Retrieve candidates (hybrid vector + trigram; text-only fallback)
        4. Filter candidates (price, location, availability; soft fallback)
        5. Rank candidates (6-signal scoring + audience/skill boosts)
        6. Hydrate top instructors with embedded data (eliminate N+1)

        Args:
            query: Natural language search query
            user_location: (lng, lat) tuple or None
            limit: Maximum instructors to return
            user_id: Optional user ID for timezone-aware parsing
            budget_ms: Optional request budget override in milliseconds
            include_diagnostics: Whether to include pipeline diagnostics in response
            force_skip_tier5: Force skip LLM location resolution (admin testing only)
            force_skip_tier4: Force skip embedding location resolution (admin testing only)
            force_skip_vector: Force skip vector search (admin testing only)
            force_skip_embedding: Force skip query embedding (admin testing only)
            force_high_load: Force high-load budget regardless of inflight (admin testing only)

        Returns:
            NLSearchResponse with instructor-level results and metadata
        """
        perf_start = time.perf_counter()
        cache_check_start = time.perf_counter()
        metrics = SearchMetrics(total_start=time.time())
        timer: Optional[PipelineTimer] = PipelineTimer() if include_diagnostics else None
        candidates_flow: Dict[str, int] = (
            {
                "initial_candidates": 0,
                "after_text_search": 0,
                "after_vector_search": 0,
                "after_location_filter": 0,
                "after_price_filter": 0,
                "after_availability_filter": 0,
                "final_results": 0,
            }
            if include_diagnostics
            else {}
        )
        if timer:
            timer.start_stage("cache_check")

        # Stage 0: Check cache
        cached = await self._check_cache(query, user_location, limit)
        cache_check_ms = int((time.perf_counter() - cache_check_start) * 1000)
        if timer:
            timer.end_stage(
                status=StageStatus.CACHE_HIT.value if cached else StageStatus.SUCCESS.value,
                details={"latency_ms": cache_check_ms},
            )
        if cached:
            metrics.cache_hit = True
            cached["meta"]["cache_hit"] = True
            cached_total_ms = int((time.perf_counter() - perf_start) * 1000)
            cached["meta"]["latency_ms"] = cached_total_ms

            record_search_metrics(
                total_latency_ms=cached_total_ms,
                stage_latencies={"cache_check": cache_check_ms},
                cache_hit=True,
                parsing_mode=str(cached.get("meta", {}).get("parsing_mode") or "regex"),
                result_count=len(cached.get("results") or []),
                degraded=False,
                degradation_reasons=[],
            )

            if _PERF_LOG_ENABLED and (cached_total_ms >= _PERF_LOG_SLOW_MS):
                logger.info(
                    "NL search timings (cache_hit): %s",
                    {
                        "cache_check_ms": cache_check_ms,
                        "total_ms": cached_total_ms,
                        "limit": limit,
                        "region": self._region_code,
                    },
                )

            response = NLSearchResponse(**cached)
            if include_diagnostics and timer:
                response.meta.diagnostics = self._build_search_diagnostics(
                    timer=timer,
                    budget=None,
                    parsed_query=None,
                    pre_data=None,
                    post_data=None,
                    location_resolution=None,
                    query_embedding=None,
                    results_count=len(response.results),
                    cache_hit=True,
                    parsing_mode=str(response.meta.parsing_mode or "regex"),
                    candidates_flow=candidates_flow,
                    total_latency_ms=cached_total_ms,
                )
            return response

        # Concurrency control for expensive uncached searches.
        # Limit concurrent full-pipeline searches to prevent system overload.
        # If semaphore is full, return 503 immediately instead of piling up.
        inflight_incremented = False
        budget: Optional[RequestBudget] = None
        soft_limit = max(1, int(get_search_config().uncached_concurrency))

        try:
            inflight = await _increment_search_inflight()
            inflight_incremented = True
            if inflight > soft_limit:
                await _decrement_search_inflight()
                inflight_incremented = False
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
            force_skip_vector_search = force_skip_vector or force_skip_embedding

            parsed_query_cached = None
            try:
                parsed_query_cached = await self.search_cache.get_cached_parsed_query(
                    query, region_code=self._region_code
                )
            except Exception as e:
                logger.warning(f"Parsed query cache lookup failed: {e}")

            loop = asyncio.get_running_loop()
            parsed_query_future: asyncio.Future[ParsedQuery] = loop.create_future()
            if parsed_query_cached is not None:
                parsed_query_future.set_result(parsed_query_cached)

            def _notify_parsed_query(parsed_query: ParsedQuery) -> None:
                if parsed_query_future.done():
                    return
                loop.call_soon_threadsafe(parsed_query_future.set_result, parsed_query)

            async def _maybe_embed_query() -> tuple[Optional[List[float]], int, Optional[str]]:
                parsed_query = await parsed_query_future
                if parsed_query.needs_llm:
                    return None, 0, None
                return await self._embed_query_with_timeout(parsed_query.service_query)

            embedding_task: Optional[
                asyncio.Task[tuple[Optional[List[float]], int, Optional[str]]]
            ] = None
            if force_skip_vector_search:
                if budget:
                    budget.skip("embedding")
                    budget.skip("vector_search")
            elif budget and budget.can_afford_vector_search():
                embedding_task = asyncio.create_task(_maybe_embed_query())
            elif budget:
                budget.skip("embedding")
                budget.skip("vector_search")

            pre_openai_start = time.perf_counter()
            try:
                pre_data = await asyncio.to_thread(
                    self._run_pre_openai_burst,
                    query,
                    parsed_query=parsed_query_cached,
                    user_id=user_id,
                    user_location=user_location,
                    notify_parsed=_notify_parsed_query,
                )
            except Exception:
                if embedding_task:
                    embedding_task.cancel()
                    try:
                        await embedding_task
                    except asyncio.CancelledError:
                        pass
                    except Exception as exc:
                        logger.debug("Embedding task failed after cancel: %s", exc)
                raise
            pre_openai_ms = int((time.perf_counter() - pre_openai_start) * 1000)

            if not parsed_query_future.done():
                parsed_query_future.set_result(pre_data.parsed_query)
            parsed_query = pre_data.parsed_query
            metrics.parse_latency_ms = pre_data.parse_latency_ms
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

            tier5_task: Optional[
                asyncio.Task[
                    tuple[
                        Optional["ResolvedLocation"],
                        Optional[LocationLLMCache],
                        Optional[UnresolvedLocationInfo],
                    ]
                ]
            ] = None
            tier5_started_at: Optional[float] = None

            if (
                not parsed_query.needs_llm
                and pre_data.location_resolution is None
                and pre_data.region_lookup
                and pre_data.location_llm_candidates
                and parsed_query.location_text
                and parsed_query.location_type != "near_me"
                and user_location is None
            ):
                allow_tier5_start = (
                    bool(budget and budget.can_afford_tier5()) and not force_skip_tier5
                )
                if allow_tier5_start:
                    tier5_started_at = time.perf_counter()
                    tier5_task = asyncio.create_task(
                        self._resolve_location_llm(
                            location_text=parsed_query.location_text,
                            original_query=parsed_query.original_query,
                            region_lookup=pre_data.region_lookup,
                            candidate_names=pre_data.location_llm_candidates,
                        )
                    )
                elif budget:
                    budget.skip("tier5_llm")

            if parsed_query_cached is None and not parsed_query.needs_llm:
                try:
                    await self.search_cache.cache_parsed_query(
                        query, parsed_query, region_code=self._region_code
                    )
                except Exception as e:
                    logger.warning(f"Failed to cache parsed query: {e}")

            if parsed_query.needs_llm:
                if embedding_task:
                    embedding_task.cancel()
                    try:
                        await embedding_task
                    except asyncio.CancelledError:
                        pass
                    except Exception as exc:
                        logger.debug("Embedding task failed after cancel: %s", exc)
                    embedding_task = None
                from app.services.search.llm_parser import LLMParser

                llm_start = time.perf_counter()
                llm_parser = LLMParser(user_id=user_id, region_code=self._region_code)
                parsed_query = await llm_parser.parse(query, parsed_query)
                metrics.parse_latency_ms += int((time.perf_counter() - llm_start) * 1000)

                if parsed_query.parsing_mode != "llm":
                    metrics.degraded = True
                    metrics.degradation_reasons.append("parsing_error")

                try:
                    await self.search_cache.cache_parsed_query(
                        query, parsed_query, region_code=self._region_code
                    )
                except Exception as e:
                    logger.warning(f"Failed to cache parsed query: {e}")

            if timer:
                timer.record_stage(
                    "parse",
                    metrics.parse_latency_ms,
                    StageStatus.SUCCESS.value,
                    {"mode": parsed_query.parsing_mode},
                )

            # Stage 2: Embed service query (OpenAI)
            embed_latency_ms = 0
            embedding_reason: Optional[str] = None
            query_embedding: Optional[List[float]] = None
            budget_skip_vector = False
            if force_skip_vector_search:
                pre_data.skip_vector = True
                budget_skip_vector = True
                if embedding_reason is None:
                    embedding_reason = (
                        "force_skip_embedding" if force_skip_embedding else "force_skip_vector"
                    )
            if budget and not budget.can_afford_vector_search():
                budget.skip("vector_search")
                budget.skip("embedding")
                pre_data.skip_vector = True
                budget_skip_vector = True
            if pre_data.skip_vector:
                if embedding_task:
                    embedding_task.cancel()
                    try:
                        await embedding_task
                    except asyncio.CancelledError:
                        pass
                    except Exception as exc:
                        logger.debug("Embedding task failed after cancel: %s", exc)
                    embedding_task = None
                if embedding_reason is None and budget_skip_vector:
                    embedding_reason = "budget_skip_vector_search"
            elif not pre_data.has_service_embeddings:
                if embedding_task:
                    embedding_task.cancel()
                    try:
                        await embedding_task
                    except asyncio.CancelledError:
                        pass
                    except Exception as exc:
                        logger.debug("Embedding task failed after cancel: %s", exc)
                    embedding_task = None
                embedding_reason = "no_embeddings_in_database"
            else:
                if embedding_task is not None:
                    try:
                        (
                            query_embedding,
                            embed_latency_ms,
                            embedding_reason,
                        ) = await embedding_task
                    except Exception as exc:
                        logger.warning(
                            "[SEARCH] Embedding failed, falling back to text-only: %s",
                            exc,
                        )
                        query_embedding = None
                        embed_latency_ms = 0
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
                    {
                        "reason": embedding_reason,
                        "used": bool(query_embedding),
                    },
                )

            # Stage 3: Resolve location with OpenAI (no DB)
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
                        bool(budget and budget.can_afford_tier4())
                        and not force_skip_tier4
                        and not force_skip_embedding
                    )
                    allow_tier5 = (
                        bool(budget and budget.can_afford_tier5()) and not force_skip_tier5
                    )
                    if budget and not allow_tier4:
                        budget.skip("tier4_embedding")
                    if budget and force_skip_tier5:
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
                        diagnostics=timer if include_diagnostics else None,
                    )
                if location_resolution is None:
                    from app.services.search.location_resolver import ResolvedLocation

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
                        and (
                            location_resolution.resolved
                            or location_resolution.requires_clarification
                        )
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

            # Stage 4: Post-OpenAI DB burst (vector search, filtering, ranking, hydration data)
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
                    r for r in metrics.degradation_reasons if r != "no_embeddings_in_database"
                ]
                if not metrics.degradation_reasons:
                    metrics.degraded = False

            if budget and budget.is_degraded:
                metrics.degraded = True
                for reason in budget.degradation_reasons:
                    if reason not in metrics.degradation_reasons:
                        metrics.degradation_reasons.append(reason)
                if budget.is_over_budget and "budget_overrun" not in metrics.degradation_reasons:
                    metrics.degradation_reasons.append("budget_overrun")
                if budget.is_exhausted() and "budget_exhausted" not in metrics.degradation_reasons:
                    metrics.degradation_reasons.append("budget_exhausted")

            # Retrieval metrics
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

            # Stage 5: Build instructor-level results with embedded data
            hydrate_start = time.perf_counter()
            hydrate_failed = False
            try:
                results = await self._hydrate_instructor_results(
                    post_data.ranking_result.results,
                    limit=limit,
                    location_resolution=post_data.filter_result.location_resolution,
                    instructor_rows=post_data.instructor_rows,
                    distance_meters=post_data.distance_meters,
                )
            except Exception as e:
                logger.error(f"Hydration failed: {e}")
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

            # Build response
            metrics.total_latency_ms = int((time.time() - metrics.total_start) * 1000)

            response_build_start = time.perf_counter()
            response = self._build_instructor_response(
                query,
                parsed_query,
                results,
                limit,
                metrics,
                filter_result=post_data.filter_result,
                budget=budget,
            )
            response_build_ms = int((time.perf_counter() - response_build_start) * 1000)
            if timer:
                timer.record_stage(
                    "build_response",
                    response_build_ms,
                    StageStatus.SUCCESS.value,
                    {"result_count": len(response.results)},
                )

            # Record Prometheus metrics
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
                result_count=len(response.results),
                degraded=metrics.degraded,
                degradation_reasons=metrics.degradation_reasons,
            )

            # Cache response.
            # Degraded responses get a short TTL to avoid "sticky" outages while still
            # preventing repeated expensive cache misses during provider instability.
            degraded_ttl = 30 if metrics.degraded else None
            cache_write_start = time.perf_counter()
            await self._cache_response(query, user_location, response, limit, ttl=degraded_ttl)
            cache_write_ms = int((time.perf_counter() - cache_write_start) * 1000)

            if include_diagnostics and timer:
                diagnostics = self._build_search_diagnostics(
                    timer=timer,
                    budget=budget,
                    parsed_query=parsed_query,
                    pre_data=pre_data,
                    post_data=post_data,
                    location_resolution=location_resolution,
                    query_embedding=query_embedding,
                    results_count=len(response.results),
                    cache_hit=False,
                    parsing_mode=parsed_query.parsing_mode,
                    candidates_flow=candidates_flow,
                    total_latency_ms=metrics.total_latency_ms,
                )
                response.meta.diagnostics = diagnostics

            if _PERF_LOG_ENABLED and (metrics.total_latency_ms >= _PERF_LOG_SLOW_MS):
                retrieval_stats = {
                    "text_search_ms": int(
                        getattr(retrieval_result, "text_search_latency_ms", 0) or 0
                    ),
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

            return response
        finally:
            if inflight_incremented:
                await _decrement_search_inflight()

    @staticmethod
    def _normalize_location_text(text_value: str) -> str:
        normalized = " ".join(str(text_value).lower().strip().split())
        wrappers = ("near ", "by ", "in ", "around ", "close to ", "at ")
        for wrapper in wrappers:
            if normalized.startswith(wrapper):
                normalized = normalized[len(wrapper) :]
        if normalized.endswith(" area"):
            normalized = normalized[:-5]
        tokens = normalized.split()
        if len(tokens) >= 3 and tokens[-1] in {"north", "south", "east", "west"}:
            normalized = " ".join(tokens[:-1])
        return " ".join(normalized.strip().split())

    @staticmethod
    def _record_pre_location_tiers(
        timer: PipelineTimer, location_resolution: Optional["ResolvedLocation"]
    ) -> None:
        from app.services.search.location_resolver import ResolutionTier

        tier_map = {
            ResolutionTier.EXACT: 1,
            ResolutionTier.ALIAS: 2,
            ResolutionTier.FUZZY: 3,
        }
        resolved_tier = (
            tier_map.get(location_resolution.tier)
            if location_resolution and location_resolution.tier
            else None
        )
        resolved_name = None
        if location_resolution and (location_resolution.region_name or location_resolution.borough):
            resolved_name = location_resolution.region_name or location_resolution.borough

        for tier in (1, 2, 3):
            if resolved_tier == tier:
                status = StageStatus.SUCCESS.value
                requires_clarification = bool(
                    location_resolution and location_resolution.requires_clarification
                )
                details = "ambiguous" if requires_clarification else "resolved"
                timer.record_location_tier(
                    tier=tier,
                    attempted=True,
                    status=status,
                    duration_ms=0,
                    result=resolved_name,
                    confidence=location_resolution.confidence if location_resolution else None,
                    details=details,
                )
            else:
                timer.record_location_tier(
                    tier=tier,
                    attempted=True,
                    status=StageStatus.MISS.value,
                    duration_ms=0,
                    details="miss",
                )

    @staticmethod
    def _compute_text_match_flags(
        service_query: str,
        text_results: Dict[str, Tuple[float, Dict[str, Any]]],
    ) -> tuple[float, bool, bool]:
        best_text_score = max((score for score, _ in text_results.values()), default=0.0)
        raw_tokens = [t for t in str(service_query or "").strip().split() if t]
        non_generic_tokens = [t for t in raw_tokens if t.lower() not in TRIGRAM_GENERIC_TOKENS]
        require_text_match = (
            bool(text_results)
            and (0 < len(non_generic_tokens) <= 2)
            and best_text_score >= TEXT_REQUIRE_TEXT_MATCH_SCORE_THRESHOLD
        )
        skip_vector = (
            len(text_results) >= TEXT_SKIP_VECTOR_MIN_RESULTS
            and best_text_score >= TEXT_SKIP_VECTOR_SCORE_THRESHOLD
        )
        return best_text_score, require_text_match, skip_vector

    @staticmethod
    def _resolve_cached_alias(
        cached_alias: "CachedAliasInfo",
        region_lookup: RegionLookup,
    ) -> Optional["ResolvedLocation"]:
        from app.services.search.location_resolver import (
            LocationCandidate,
            ResolutionTier,
            ResolvedLocation,
        )

        if cached_alias.is_ambiguous and cached_alias.candidate_region_ids:
            candidates: List[LocationCandidate] = []
            for region_id in cached_alias.candidate_region_ids:
                info = region_lookup.by_id.get(region_id)
                if not info:
                    continue
                candidates.append(
                    {
                        "region_id": info.region_id,
                        "region_name": info.region_name,
                        "borough": info.borough,
                    }
                )
            if len(candidates) >= 2:
                return ResolvedLocation.from_ambiguous(
                    candidates=candidates,
                    tier=ResolutionTier.LLM,
                    confidence=cached_alias.confidence,
                )

        if cached_alias.is_resolved and cached_alias.region_id:
            info = region_lookup.by_id.get(cached_alias.region_id)
            if info:
                return ResolvedLocation.from_region(
                    region_id=info.region_id,
                    region_name=info.region_name,
                    borough=info.borough,
                    tier=ResolutionTier.LLM,
                    confidence=cached_alias.confidence,
                )
        return None

    @staticmethod
    def _select_instructor_ids(ranked: List[RankedResult], limit: int) -> List[str]:
        ordered: List[str] = []
        seen: set[str] = set()
        for r in ranked:
            if r.instructor_id in seen:
                continue
            seen.add(r.instructor_id)
            ordered.append(r.instructor_id)
            if len(ordered) >= limit:
                break
        return ordered

    @staticmethod
    def _distance_region_ids(
        location_resolution: Optional["ResolvedLocation"],
    ) -> Optional[List[str]]:
        if not location_resolution:
            return None
        if location_resolution.region_id:
            return [str(location_resolution.region_id)]
        if location_resolution.requires_clarification and location_resolution.candidates:
            candidate_ids = [
                str(c.get("region_id"))
                for c in location_resolution.candidates
                if isinstance(c, dict) and c.get("region_id")
            ]
            return list(dict.fromkeys(candidate_ids)) or None
        return None

    @staticmethod
    def _consume_task_result(task: asyncio.Task[Any], *, label: str) -> None:
        """Ensure background task exceptions are surfaced without blocking."""

        def _done(finished: asyncio.Task[Any]) -> None:
            try:
                finished.result()
            except asyncio.CancelledError:
                return
            except Exception as exc:
                logger.debug("[SEARCH] %s task failed: %s", label, exc)

        task.add_done_callback(_done)

    @staticmethod
    def _pick_best_location(
        tier4_result: Optional["ResolvedLocation"],
        tier5_result: Optional["ResolvedLocation"],
    ) -> Optional["ResolvedLocation"]:
        if (
            tier4_result
            and tier4_result.resolved
            and tier4_result.confidence >= LOCATION_TIER4_HIGH_CONFIDENCE
        ):
            return tier4_result
        if tier5_result and (
            tier5_result.confidence >= LOCATION_LLM_CONFIDENCE_THRESHOLD or not tier4_result
        ):
            return tier5_result
        if tier4_result:
            return tier4_result
        return None

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
        Optional["ResolvedLocation"], Optional[LocationLLMCache], Optional[UnresolvedLocationInfo]
    ]:
        from app.services.search.location_resolver import (
            LocationCandidate,
            ResolutionTier,
            ResolvedLocation,
        )

        normalized_value = normalized or self._normalize_location_text(location_text)
        if not normalized_value:
            return None, None, None

        allowed_names: List[str] = []
        seen: set[str] = set()
        for name in candidate_names:
            if not name:
                continue
            key = str(name).strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            allowed_names.append(str(name).strip())

        if not allowed_names:
            return (
                None,
                None,
                UnresolvedLocationInfo(
                    normalized=normalized_value,
                    original_query=original_query or location_text,
                ),
            )

        llm_result = await self.location_llm_service.resolve(
            location_text=original_query or location_text,
            allowed_region_names=allowed_names,
            timeout_s=timeout_s,
        )
        if not llm_result:
            return (
                None,
                None,
                UnresolvedLocationInfo(
                    normalized=normalized_value,
                    original_query=original_query or location_text,
                ),
            )

        neighborhoods = llm_result.get("neighborhoods") or []
        if not isinstance(neighborhoods, list) or not neighborhoods:
            return (
                None,
                None,
                UnresolvedLocationInfo(
                    normalized=normalized_value,
                    original_query=original_query or location_text,
                ),
            )

        regions: List[RegionInfo] = []
        seen_ids: set[str] = set()
        for name in neighborhoods:
            if not isinstance(name, str):
                continue
            key = name.strip().lower()
            info = region_lookup.by_name.get(key)
            if not info or info.region_id in seen_ids:
                continue
            seen_ids.add(info.region_id)
            regions.append(info)

        if not regions:
            return (
                None,
                None,
                UnresolvedLocationInfo(
                    normalized=normalized_value,
                    original_query=original_query or location_text,
                ),
            )

        confidence_val = float(llm_result.get("confidence") or 0.5)
        region_ids = [r.region_id for r in regions]
        llm_cache = LocationLLMCache(
            normalized=normalized_value,
            confidence=confidence_val,
            region_ids=region_ids,
        )

        if len(regions) == 1:
            only = regions[0]
            return (
                ResolvedLocation.from_region(
                    region_id=only.region_id,
                    region_name=only.region_name,
                    borough=only.borough,
                    tier=ResolutionTier.LLM,
                    confidence=confidence_val,
                ),
                llm_cache,
                None,
            )

        llm_candidates: List[LocationCandidate] = [
            {
                "region_id": r.region_id,
                "region_name": r.region_name,
                "borough": r.borough,
            }
            for r in regions
        ]
        return (
            ResolvedLocation.from_ambiguous(
                candidates=llm_candidates,
                tier=ResolutionTier.LLM,
                confidence=confidence_val,
            ),
            llm_cache,
            None,
        )

    async def _embed_query_with_timeout(
        self,
        query: str,
    ) -> tuple[Optional[List[float]], int, Optional[str]]:
        embed_start = time.perf_counter()
        degradation_reason: Optional[str] = None
        embedding: Optional[List[float]] = None

        try:
            config_timeout_ms = max(0, int(get_search_config().embedding_timeout_ms))
            soft_timeout_ms = max(0, EMBEDDING_SOFT_TIMEOUT_MS)
            timeout_ms = (
                min(config_timeout_ms, soft_timeout_ms) if soft_timeout_ms else config_timeout_ms
            )
            timeout_s = (timeout_ms / 1000.0) if timeout_ms else None

            if timeout_s:
                embedding = await asyncio.wait_for(
                    self.embedding_service.embed_query(query), timeout=timeout_s
                )
            else:
                embedding = await self.embedding_service.embed_query(query)
        except asyncio.TimeoutError:
            degradation_reason = "embedding_timeout"
            embedding = None

        if embedding is None and degradation_reason is None:
            degradation_reason = "embedding_service_unavailable"

        embed_latency_ms = int((time.perf_counter() - embed_start) * 1000)
        return embedding, embed_latency_ms, degradation_reason

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

        with get_db_session() as db:
            batch = SearchBatchRepository(db, region_code=self._region_code)
            parse_latency_ms = 0
            if parsed_query is None:
                parse_start = time.perf_counter()
                parser = QueryParser(db, user_id=user_id, region_code=self._region_code)
                parsed_query = parser.parse(query)
                parse_latency_ms = int((time.perf_counter() - parse_start) * 1000)

            if notify_parsed and parsed_query is not None:
                try:
                    notify_parsed(parsed_query)
                except Exception as exc:
                    logger.debug("Failed to notify parsed query: %s", exc)

            has_service_embeddings = batch.has_service_embeddings()
            text_results: Optional[Dict[str, Tuple[float, Dict[str, Any]]]] = None
            text_latency_ms = 0
            best_text_score = 0.0
            require_text_match = False
            skip_vector = False

            if not parsed_query.needs_llm:
                text_query = self.retriever._normalize_query_for_trigram(parsed_query.service_query)
                text_start = time.perf_counter()
                text_results = batch.text_search(
                    text_query,
                    text_query,
                    limit=min(TEXT_TOP_K, MAX_CANDIDATES),
                )
                text_latency_ms = int((time.perf_counter() - text_start) * 1000)
                (
                    best_text_score,
                    require_text_match,
                    skip_vector,
                ) = self._compute_text_match_flags(parsed_query.service_query, text_results)

            region_lookup: Optional[RegionLookup] = None
            location_resolution: Optional["ResolvedLocation"] = None
            location_normalized: Optional[str] = None
            cached_alias_normalized: Optional[str] = None
            fuzzy_score: Optional[float] = None
            location_llm_candidates: List[str] = []

            should_load_regions = bool(parsed_query.needs_llm or parsed_query.location_text)
            if should_load_regions:
                region_lookup = batch.load_region_lookup()

            if (
                region_lookup
                and parsed_query.location_text
                and parsed_query.location_type != "near_me"
                and user_location is None
                and not parsed_query.needs_llm
            ):
                location_normalized = self._normalize_location_text(parsed_query.location_text)
                resolver = LocationResolver(db, region_code=self._region_code)
                non_semantic = resolver.resolve_sync(
                    parsed_query.location_text,
                    original_query=parsed_query.original_query,
                    track_unresolved=False,
                )
                if non_semantic.resolved or non_semantic.requires_clarification:
                    location_resolution = non_semantic
                else:
                    cached_alias = batch.get_cached_llm_alias(location_normalized)
                    if cached_alias:
                        location_resolution = self._resolve_cached_alias(
                            cached_alias, region_lookup
                        )
                        if location_resolution:
                            cached_alias_normalized = location_normalized

                if location_resolution is None and location_normalized:
                    fuzzy_score = batch.get_best_fuzzy_score(location_normalized)

                if location_resolution is None and location_normalized:
                    location_llm_candidates = batch.get_fuzzy_candidate_names(
                        location_normalized, limit=LOCATION_LLM_TOP_K
                    )
                    if (
                        fuzzy_score is not None
                        and fuzzy_score < resolver.MIN_FUZZY_FOR_EMBEDDING
                        and region_lookup.region_names
                    ):
                        location_llm_candidates = list(region_lookup.region_names)

            return PreOpenAIData(
                parsed_query=parsed_query,
                parse_latency_ms=parse_latency_ms,
                text_results=text_results,
                text_latency_ms=text_latency_ms,
                has_service_embeddings=has_service_embeddings,
                best_text_score=best_text_score,
                require_text_match=require_text_match,
                skip_vector=skip_vector,
                region_lookup=region_lookup,
                location_resolution=location_resolution,
                location_normalized=location_normalized,
                cached_alias_normalized=cached_alias_normalized,
                fuzzy_score=fuzzy_score,
                location_llm_candidates=location_llm_candidates,
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
                    Optional["ResolvedLocation"],
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
        from app.services.search.location_resolver import (
            LocationCandidate,
            LocationResolver,
            ResolutionTier,
            ResolvedLocation,
        )

        normalized = self._normalize_location_text(location_text)
        if not normalized or not region_lookup:
            if tier5_task:
                self._consume_task_result(tier5_task, label="location_llm")
            if diagnostics:
                reason = "empty_query" if not normalized else "missing_region_lookup"
                diagnostics.record_location_tier(
                    tier=4,
                    attempted=False,
                    status=StageStatus.SKIPPED.value,
                    duration_ms=0,
                    details=reason,
                )
                diagnostics.record_location_tier(
                    tier=5,
                    attempted=False,
                    status=StageStatus.SKIPPED.value,
                    duration_ms=0,
                    details=reason,
                )
            unresolved = (
                UnresolvedLocationInfo(
                    normalized=normalized,
                    original_query=original_query or location_text,
                )
                if normalized
                else None
            )
            return ResolvedLocation.from_not_found(), None, unresolved

        tokens = normalized.split()
        threshold = LocationResolver.MIN_FUZZY_FOR_EMBEDDING
        should_try_embedding = bool(region_lookup.embeddings) and (
            len(tokens) >= 2 or fuzzy_score is None or (fuzzy_score >= threshold)
        )

        tier4_result: Optional[ResolvedLocation] = None
        embedding_candidate_names: List[str] = []
        if allow_tier4 and should_try_embedding:
            tier4_start = time.perf_counter()
            embedding = None
            tier4_recorded = False
            try:
                embedding = await self.location_embedding_service.embed_location_text(normalized)
            except Exception as exc:
                if diagnostics:
                    diagnostics.record_location_tier(
                        tier=4,
                        attempted=True,
                        status=StageStatus.ERROR.value,
                        duration_ms=int((time.perf_counter() - tier4_start) * 1000),
                        details=str(exc),
                    )
                    tier4_recorded = True
            if embedding:
                embedding_rows = [
                    {
                        "region_id": row.region_id,
                        "region_name": row.region_name,
                        "borough": row.borough,
                        "embedding": row.embedding,
                        "norm": row.norm,
                    }
                    for row in region_lookup.embeddings
                ]
                embedding_candidates = LocationEmbeddingService.build_candidates_from_embeddings(
                    embedding,
                    embedding_rows,
                    limit=5,
                )
                llm_embedding_candidates = (
                    LocationEmbeddingService.build_candidates_from_embeddings(
                        embedding,
                        embedding_rows,
                        limit=LOCATION_LLM_TOP_K,
                        threshold=LOCATION_LLM_EMBEDDING_THRESHOLD,
                    )
                )
                for row in llm_embedding_candidates:
                    name = row.get("region_name")
                    if not name:
                        continue
                    text = str(name).strip()
                    if text and text not in embedding_candidate_names:
                        embedding_candidate_names.append(text)
                best_candidate, ambiguous = LocationEmbeddingService.pick_best_or_ambiguous(
                    embedding_candidates
                )
                if (
                    best_candidate
                    and best_candidate.get("region_id")
                    and best_candidate.get("region_name")
                ):
                    tier4_result = ResolvedLocation.from_region(
                        region_id=str(best_candidate["region_id"]),
                        region_name=str(best_candidate["region_name"]),
                        borough=best_candidate.get("borough"),
                        tier=ResolutionTier.EMBEDDING,
                        confidence=float(best_candidate.get("similarity") or 0.0),
                    )
                if ambiguous:
                    formatted: List[LocationCandidate] = []
                    for row in ambiguous:
                        if not row.get("region_id") or not row.get("region_name"):
                            continue
                        formatted.append(
                            {
                                "region_id": str(row["region_id"]),
                                "region_name": str(row["region_name"]),
                                "borough": row.get("borough"),
                            }
                        )
                    if len(formatted) >= 2:
                        top_sim = float(ambiguous[0].get("similarity") or 0.0)
                        tier4_result = ResolvedLocation.from_ambiguous(
                            candidates=formatted,
                            tier=ResolutionTier.EMBEDDING,
                            confidence=top_sim,
                        )
            if diagnostics and not tier4_recorded:
                tier4_duration = int((time.perf_counter() - tier4_start) * 1000)
                status = (
                    StageStatus.SUCCESS.value
                    if tier4_result
                    and (tier4_result.resolved or tier4_result.requires_clarification)
                    else StageStatus.MISS.value
                )
                resolved_name = None
                if tier4_result and (tier4_result.region_name or tier4_result.borough):
                    resolved_name = tier4_result.region_name or tier4_result.borough
                diagnostics.record_location_tier(
                    tier=4,
                    attempted=True,
                    status=status,
                    duration_ms=tier4_duration,
                    result=resolved_name,
                    confidence=getattr(tier4_result, "confidence", None),
                    details="embedding_match" if embedding else "no_embedding",
                )
        elif diagnostics:
            reason = "disabled"
            if allow_tier4:
                reason = (
                    "no_region_embeddings" if not region_lookup.embeddings else "fuzzy_threshold"
                )
            diagnostics.record_location_tier(
                tier=4,
                attempted=False,
                status=StageStatus.SKIPPED.value,
                duration_ms=0,
                details=reason,
            )

        if (
            tier4_result
            and tier4_result.resolved
            and tier4_result.confidence >= LOCATION_TIER4_HIGH_CONFIDENCE
        ):
            if tier5_task:
                self._consume_task_result(tier5_task, label="location_llm")
                if diagnostics:
                    diagnostics.record_location_tier(
                        tier=5,
                        attempted=False,
                        status=StageStatus.SKIPPED.value,
                        duration_ms=0,
                        details="tier4_high_confidence",
                    )
            return tier4_result, None, None

        tier4_resolved = bool(tier4_result and tier4_result.resolved)
        tier5_timeout_s: Optional[float] = None
        if budget and not budget.can_afford_tier5():
            if not force_skip_tier5 and not tier4_resolved and budget.remaining_ms > 0:
                config = get_search_config()
                location_timeout_s = max(0.0, float(config.location_timeout_ms) / 1000.0)
                tier5_timeout_s = min(budget.remaining_ms / 1000.0, location_timeout_s)
                allow_tier5 = True
            else:
                allow_tier5 = False
                budget.skip("tier5_llm")
                if tier5_task:
                    self._consume_task_result(tier5_task, label="location_llm")
                    tier5_task = None
                if diagnostics:
                    diagnostics.record_location_tier(
                        tier=5,
                        attempted=False,
                        status=StageStatus.SKIPPED.value,
                        duration_ms=0,
                        details="budget_insufficient",
                    )

        llm_result: Optional[ResolvedLocation] = None
        llm_cache: Optional[LocationLLMCache] = None
        llm_unresolved: Optional[UnresolvedLocationInfo] = None

        if not allow_tier5 and tier5_task is not None:
            self._consume_task_result(tier5_task, label="location_llm")
            if diagnostics:
                diagnostics.record_location_tier(
                    tier=5,
                    attempted=False,
                    status=StageStatus.SKIPPED.value,
                    duration_ms=0,
                    details="disabled",
                )
        elif tier5_task is not None:
            tier5_start = tier5_started_at or time.perf_counter()
            try:
                if tier5_timeout_s and tier5_timeout_s > 0:
                    llm_result, llm_cache, llm_unresolved = await asyncio.wait_for(
                        tier5_task, timeout=tier5_timeout_s
                    )
                else:
                    llm_result, llm_cache, llm_unresolved = await tier5_task
                if diagnostics:
                    tier5_duration = int((time.perf_counter() - tier5_start) * 1000)
                    resolved_name = None
                    if llm_result and (llm_result.region_name or llm_result.borough):
                        resolved_name = llm_result.region_name or llm_result.borough
                    diagnostics.record_location_tier(
                        tier=5,
                        attempted=True,
                        status=StageStatus.SUCCESS.value if llm_result else StageStatus.MISS.value,
                        duration_ms=tier5_duration,
                        result=resolved_name,
                        confidence=getattr(llm_result, "confidence", None),
                        details=(
                            f"llm_task timeout_ms={int(tier5_timeout_s * 1000)}"
                            if tier5_timeout_s
                            else "llm_task"
                        ),
                    )
            except asyncio.TimeoutError:
                llm_result = None
                logger.warning("[LOCATION] Tier 5 timed out")
                if diagnostics:
                    tier5_duration = int((time.perf_counter() - tier5_start) * 1000)
                    diagnostics.record_location_tier(
                        tier=5,
                        attempted=True,
                        status=StageStatus.TIMEOUT.value,
                        duration_ms=tier5_duration,
                        details="timeout",
                    )
            except asyncio.CancelledError:
                llm_result = None
                if diagnostics:
                    tier5_duration = int((time.perf_counter() - tier5_start) * 1000)
                    diagnostics.record_location_tier(
                        tier=5,
                        attempted=True,
                        status=StageStatus.CANCELLED.value,
                        duration_ms=tier5_duration,
                        details="cancelled",
                    )
            except Exception as exc:
                logger.warning("[LOCATION] Tier 5 failed: %s", exc)
                if diagnostics:
                    tier5_duration = int((time.perf_counter() - tier5_start) * 1000)
                    diagnostics.record_location_tier(
                        tier=5,
                        attempted=True,
                        status=StageStatus.ERROR.value,
                        duration_ms=tier5_duration,
                        details=str(exc),
                    )
        elif allow_tier5:
            allowed_names = list(llm_candidates or [])
            for name in embedding_candidate_names:
                if name not in allowed_names:
                    allowed_names.append(name)
            if not allowed_names:
                allowed_names = region_lookup.region_names
            if allowed_names:
                tier5_start = time.perf_counter()
                try:
                    llm_result, llm_cache, llm_unresolved = await self._resolve_location_llm(
                        location_text=location_text,
                        original_query=original_query,
                        region_lookup=region_lookup,
                        candidate_names=allowed_names,
                        timeout_s=tier5_timeout_s,
                        normalized=normalized,
                    )
                    if diagnostics:
                        tier5_duration = int((time.perf_counter() - tier5_start) * 1000)
                        resolved_name = None
                        if llm_result and (llm_result.region_name or llm_result.borough):
                            resolved_name = llm_result.region_name or llm_result.borough
                        diagnostics.record_location_tier(
                            tier=5,
                            attempted=True,
                            status=StageStatus.SUCCESS.value
                            if llm_result
                            else StageStatus.MISS.value,
                            duration_ms=tier5_duration,
                            result=resolved_name,
                            confidence=getattr(llm_result, "confidence", None),
                            details=(
                                f"llm_call candidates={len(allowed_names)}"
                                + (
                                    f" timeout_ms={int(tier5_timeout_s * 1000)}"
                                    if tier5_timeout_s
                                    else ""
                                )
                            ),
                        )
                except asyncio.TimeoutError:
                    llm_result = None
                    logger.warning("[LOCATION] Tier 5 timed out")
                    if diagnostics:
                        tier5_duration = int((time.perf_counter() - tier5_start) * 1000)
                        diagnostics.record_location_tier(
                            tier=5,
                            attempted=True,
                            status=StageStatus.TIMEOUT.value,
                            duration_ms=tier5_duration,
                            details="timeout",
                        )
                except Exception as exc:
                    logger.warning("[LOCATION] Tier 5 failed: %s", exc)
                    if diagnostics:
                        tier5_duration = int((time.perf_counter() - tier5_start) * 1000)
                        diagnostics.record_location_tier(
                            tier=5,
                            attempted=True,
                            status=StageStatus.ERROR.value,
                            duration_ms=tier5_duration,
                            details=str(exc),
                        )
            elif diagnostics:
                diagnostics.record_location_tier(
                    tier=5,
                    attempted=False,
                    status=StageStatus.SKIPPED.value,
                    duration_ms=0,
                    details="no_candidates",
                )
        elif diagnostics and tier5_task is None:
            diagnostics.record_location_tier(
                tier=5,
                attempted=False,
                status=StageStatus.SKIPPED.value,
                duration_ms=0,
                details="disabled",
            )

        best = self._pick_best_location(tier4_result, llm_result)
        if not best:
            if llm_unresolved is None:
                llm_unresolved = UnresolvedLocationInfo(
                    normalized=normalized,
                    original_query=original_query or location_text,
                )
            return ResolvedLocation.from_not_found(), None, llm_unresolved

        if best is llm_result:
            return best, llm_cache, None

        return best, None, None

    def _run_post_openai_burst(
        self,
        pre_data: PreOpenAIData,
        parsed_query: ParsedQuery,
        query_embedding: Optional[List[float]],
        location_resolution: Optional["ResolvedLocation"],
        location_llm_cache: Optional[LocationLLMCache],
        unresolved_info: Optional[UnresolvedLocationInfo],
        user_location: Optional[Tuple[float, float]],
        limit: int,
    ) -> PostOpenAIData:
        from app.repositories.filter_repository import FilterRepository
        from app.repositories.ranking_repository import RankingRepository
        from app.repositories.retriever_repository import RetrieverRepository
        from app.repositories.unresolved_location_query_repository import (
            UnresolvedLocationQueryRepository,
        )
        from app.services.search.location_resolver import LocationResolver

        with get_db_session() as db:
            batch = SearchBatchRepository(db, region_code=self._region_code)
            retriever_repo = RetrieverRepository(db)
            filter_repo = FilterRepository(db)
            ranking_repo = RankingRepository(db)
            resolver = LocationResolver(db, region_code=self._region_code)

            text_results = pre_data.text_results
            text_latency_ms = pre_data.text_latency_ms
            require_text_match = pre_data.require_text_match
            skip_vector = pre_data.skip_vector

            if text_results is None:
                text_query = self.retriever._normalize_query_for_trigram(parsed_query.service_query)
                text_start = time.perf_counter()
                text_results = batch.text_search(
                    text_query,
                    text_query,
                    limit=min(TEXT_TOP_K, MAX_CANDIDATES),
                )
                text_latency_ms = int((time.perf_counter() - text_start) * 1000)
                (
                    _,
                    require_text_match,
                    skip_vector,
                ) = self._compute_text_match_flags(parsed_query.service_query, text_results)

            vector_results: Dict[str, Tuple[float, Dict[str, Any]]] = {}
            vector_latency_ms = 0
            vector_search_used = False
            if query_embedding and not skip_vector:
                vector_start = time.perf_counter()
                vector_results = batch.vector_search(
                    query_embedding,
                    limit=min(VECTOR_TOP_K, MAX_CANDIDATES),
                )
                vector_latency_ms = int((time.perf_counter() - vector_start) * 1000)
                vector_search_used = True

            candidates = self.retriever.fuse_results(
                vector_results,
                text_results or {},
                MAX_CANDIDATES,
                require_text_match=require_text_match,
            )

            # Filtering (sync, DB-only)
            filter_start = time.perf_counter()
            filter_service = FilterService(
                repository=filter_repo,
                location_resolver=resolver,
                region_code=self._region_code,
            )
            filter_failed = False
            try:
                filter_result = filter_service.filter_candidates_sync(
                    candidates,
                    parsed_query,
                    user_location=user_location,
                    location_resolution=location_resolution,
                )
            except Exception as exc:
                logger.error(f"Filtering failed: {exc}")
                filter_failed = True
                filter_result = FilterResult(
                    candidates=[
                        FilteredCandidate(
                            service_id=c.service_id,
                            service_catalog_id=c.service_catalog_id,
                            instructor_id=c.instructor_id,
                            hybrid_score=c.hybrid_score,
                            name=c.name,
                            description=c.description,
                            price_per_hour=c.price_per_hour,
                        )
                        for c in candidates
                    ],
                    total_before_filter=len(candidates),
                    total_after_filter=len(candidates),
                    filters_applied=[],
                    soft_filtering_used=False,
                    location_resolution=location_resolution,
                )
            filter_latency_ms = int((time.perf_counter() - filter_start) * 1000)

            # Ranking
            rank_start = time.perf_counter()
            ranking_service = RankingService(repository=ranking_repo)
            ranking_failed = False
            try:
                ranking_result = ranking_service.rank_candidates(
                    filter_result.candidates,
                    parsed_query,
                    user_location=user_location,
                )
            except Exception as exc:
                logger.error(f"Ranking failed: {exc}")
                ranking_failed = True
                ranking_result = RankingResult(results=[], total_results=0)
            rank_latency_ms = int((time.perf_counter() - rank_start) * 1000)

            ordered_instructor_ids = self._select_instructor_ids(ranking_result.results, limit)
            instructor_rows = retriever_repo.get_instructor_cards(ordered_instructor_ids)

            distance_meters: Dict[str, float] = {}
            distance_region_ids = self._distance_region_ids(location_resolution)
            if distance_region_ids:
                distance_meters = filter_repo.get_instructor_min_distance_to_regions(
                    ordered_instructor_ids,
                    distance_region_ids,
                )

            # Location cache updates (best-effort)
            if location_llm_cache:
                resolver.cache_llm_alias(
                    location_llm_cache.normalized,
                    location_llm_cache.region_ids,
                    confidence=location_llm_cache.confidence,
                )

            if pre_data.cached_alias_normalized:
                cached_alias = resolver.repository.find_cached_alias(
                    pre_data.cached_alias_normalized, source="llm"
                )
                if cached_alias:
                    resolver.repository.increment_alias_user_count(cached_alias)

            if unresolved_info:
                unresolved_repo = UnresolvedLocationQueryRepository(db)
                unresolved_repo.track_unresolved(
                    unresolved_info.normalized,
                    original_query=unresolved_info.original_query,
                )

            return PostOpenAIData(
                filter_result=filter_result,
                ranking_result=ranking_result,
                retrieval_candidates=candidates,
                instructor_rows=instructor_rows,
                distance_meters=distance_meters,
                text_latency_ms=text_latency_ms,
                vector_latency_ms=vector_latency_ms,
                filter_latency_ms=filter_latency_ms,
                rank_latency_ms=rank_latency_ms,
                vector_search_used=vector_search_used,
                total_candidates=len(candidates),
                filter_failed=filter_failed,
                ranking_failed=ranking_failed,
                skip_vector=skip_vector,
            )

    async def _hydrate_instructor_results(
        self,
        ranked: List[RankedResult],
        limit: int,
        *,
        location_resolution: Optional["ResolvedLocation"] = None,
        instructor_rows: Optional[List[Dict[str, Any]]] = None,
        distance_meters: Optional[Dict[str, float]] = None,
    ) -> List[NLSearchResultItem]:
        """
        Convert ranked service-level candidates into instructor-level results.

        Uses batch DB queries to avoid N+1:
        - instructor summaries (users + instructor_profiles)
        - ratings aggregates (reviews)
        - coverage areas (instructor_service_areas + region_boundaries)
        - service catalog mapping for selected instructor_services
        """
        if not ranked:
            return []

        # Determine instructor order by first occurrence (ranked list is already sorted by score).
        ordered_instructor_ids: List[str] = []
        seen_instructors: set[str] = set()
        for r in ranked:
            if r.instructor_id in seen_instructors:
                continue
            seen_instructors.add(r.instructor_id)
            ordered_instructor_ids.append(r.instructor_id)
            if len(ordered_instructor_ids) >= limit:
                break

        selected_instructors = set(ordered_instructor_ids)

        # Group services per instructor (keep all ranked services for match_count)
        by_instructor: Dict[str, List[RankedResult]] = {iid: [] for iid in ordered_instructor_ids}
        for r in ranked:
            if r.instructor_id in selected_instructors:
                by_instructor[r.instructor_id].append(r)

        # Pick best_match + other_matches by relevance_score (semantic match) per instructor.
        chosen_by_instructor: Dict[str, List[RankedResult]] = {}
        for instructor_id in ordered_instructor_ids:
            services = sorted(
                by_instructor[instructor_id], key=lambda x: x.relevance_score, reverse=True
            )
            chosen = services[:4]  # best + up to 3 others
            if not chosen:
                continue
            chosen_by_instructor[instructor_id] = chosen

        # Optional distance map (meters) for admin debugging when we have a location reference.
        distance_region_ids: Optional[List[str]] = None
        if location_resolution and location_resolution.region_id:
            distance_region_ids = [str(location_resolution.region_id)]
        elif (
            location_resolution
            and location_resolution.requires_clarification
            and location_resolution.candidates
        ):
            candidate_ids = [
                str(c.get("region_id"))
                for c in location_resolution.candidates
                if isinstance(c, dict) and c.get("region_id")
            ]
            # De-dupe while preserving order
            distance_region_ids = list(dict.fromkeys(candidate_ids)) or None

        if instructor_rows is None:

            def _load_hydration_data() -> tuple[List[Dict[str, Any]], Dict[str, float]]:
                from app.repositories.filter_repository import FilterRepository
                from app.repositories.retriever_repository import RetrieverRepository

                with get_db_session() as db:
                    retriever_repo = RetrieverRepository(db)
                    rows = retriever_repo.get_instructor_cards(ordered_instructor_ids)

                    distance_map: Dict[str, float] = {}
                    if distance_region_ids:
                        filter_repo = FilterRepository(db)
                        distance_map = filter_repo.get_instructor_min_distance_to_regions(
                            ordered_instructor_ids,
                            distance_region_ids,
                        )
                    return rows, distance_map

            instructor_rows, distance_meters = await asyncio.to_thread(_load_hydration_data)

        if distance_meters is None:
            distance_meters = {}

        assert instructor_rows is not None
        instructor_by_id: Dict[str, Dict[str, Any]] = {
            row["instructor_id"]: row for row in instructor_rows
        }

        results: List[NLSearchResultItem] = []
        for instructor_id in ordered_instructor_ids:
            chosen_for_instructor = chosen_by_instructor.get(instructor_id)
            profile = instructor_by_id.get(instructor_id)
            if not chosen_for_instructor or not profile:
                continue

            best_ranked = chosen_for_instructor[0]

            instructor = InstructorSummary(
                id=instructor_id,
                first_name=profile["first_name"],
                last_initial=profile.get("last_initial") or "",
                profile_picture_url=self._build_photo_url(profile.get("profile_picture_key")),
                bio_snippet=profile.get("bio_snippet"),
                verified=bool(profile.get("verified", False)),
                years_experience=profile.get("years_experience"),
            )

            rating_summary = RatingSummary(
                average=round(float(profile["avg_rating"]), 2)
                if profile.get("avg_rating")
                else None,
                count=int(profile.get("review_count", 0) or 0),
            )

            best_match = ServiceMatch(
                service_id=best_ranked.service_id,
                service_catalog_id=best_ranked.service_catalog_id,
                name=best_ranked.name,
                description=best_ranked.description,
                price_per_hour=int(best_ranked.price_per_hour),
                relevance_score=round(float(best_ranked.relevance_score), 3),
            )

            other_matches: List[ServiceMatch] = []
            for other_ranked in chosen_for_instructor[1:]:
                other_matches.append(
                    ServiceMatch(
                        service_id=other_ranked.service_id,
                        service_catalog_id=other_ranked.service_catalog_id,
                        name=other_ranked.name,
                        description=other_ranked.description,
                        price_per_hour=int(other_ranked.price_per_hour),
                        relevance_score=round(float(other_ranked.relevance_score), 3),
                    )
                )

            results.append(
                NLSearchResultItem(
                    instructor_id=instructor_id,
                    instructor=instructor,
                    rating=rating_summary,
                    coverage_areas=profile.get("coverage_areas", []) or [],
                    best_match=best_match,
                    other_matches=other_matches,
                    total_matching_services=len(by_instructor.get(instructor_id, [])) or 1,
                    relevance_score=best_match.relevance_score,
                    distance_km=round(float(distance_meters[instructor_id]) / 1000.0, 1)
                    if distance_meters.get(instructor_id) is not None
                    else None,
                    distance_mi=round(float(distance_meters[instructor_id]) / 1609.34, 1)
                    if distance_meters.get(instructor_id) is not None
                    else None,
                )
            )

        return results

    async def _check_cache(
        self,
        query: str,
        user_location: Optional[Tuple[float, float]],
        limit: int,
    ) -> Optional[Dict[str, Any]]:
        """Check for cached response."""
        try:
            result: Optional[Dict[str, Any]] = await self.search_cache.get_cached_response(
                query,
                user_location,
                limit=limit,
                region_code=self._region_code,
            )
            return result
        except Exception as e:
            logger.warning(f"Cache check failed: {e}")
            return None

    async def _parse_query(
        self,
        query: str,
        metrics: SearchMetrics,
        user_id: Optional[str] = None,
    ) -> ParsedQuery:
        """Parse the search query."""
        start = time.time()

        try:
            # Try cache first
            cached_parsed = await self.search_cache.get_cached_parsed_query(
                query, region_code=self._region_code
            )
            if cached_parsed:
                metrics.parse_latency_ms = int((time.time() - start) * 1000)
                return cached_parsed

            # Parse with hybrid approach
            parsed = await hybrid_parse(query, user_id=user_id, region_code=self._region_code)

            # Cache the parsed query
            await self.search_cache.cache_parsed_query(query, parsed, region_code=self._region_code)

        except Exception as e:
            logger.error(f"Parsing failed, using basic extraction: {e}")

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
        """Retrieve candidate services."""
        start = time.time()

        try:
            result = await self.retriever.search(parsed_query)

            if result.degraded:
                metrics.degraded = True
                if result.degradation_reason:
                    metrics.degradation_reasons.append(result.degradation_reason)

        except Exception as e:
            logger.error(f"Retrieval failed: {e}")
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
            0, total_ms - metrics.embed_latency_ms
        )
        return result

    async def _filter_candidates(
        self,
        retrieval_result: RetrievalResult,
        parsed_query: ParsedQuery,
        user_location: Optional[Tuple[float, float]],
        metrics: SearchMetrics,
    ) -> FilterResult:
        """Apply constraint filters."""
        start = time.time()

        try:
            result = await self.filter_service.filter_candidates(
                retrieval_result.candidates,
                parsed_query,
                user_location=user_location,
            )
        except Exception as e:
            logger.error(f"Filtering failed: {e}")
            # Pass through unfiltered on failure
            result = FilterResult(
                candidates=[
                    FilteredCandidate(
                        service_id=c.service_id,
                        service_catalog_id=c.service_catalog_id,
                        instructor_id=c.instructor_id,
                        hybrid_score=c.hybrid_score,
                        name=c.name,
                        description=c.description,
                        price_per_hour=c.price_per_hour,
                    )
                    for c in retrieval_result.candidates
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
        """Rank filtered candidates."""
        start = time.time()

        try:
            result = self.ranking_service.rank_candidates(
                filter_result.candidates,
                parsed_query,
                user_location=user_location,
            )
        except Exception as e:
            logger.error(f"Ranking failed: {e}")
            # Return unranked results on failure
            result = RankingResult(
                results=[
                    RankedResult(
                        service_id=c.service_id,
                        service_catalog_id=c.service_catalog_id,
                        instructor_id=c.instructor_id,
                        name=c.name,
                        description=c.description,
                        price_per_hour=c.price_per_hour,
                        final_score=c.hybrid_score,
                        rank=i + 1,
                        relevance_score=c.hybrid_score,
                        quality_score=0.5,
                        distance_score=0.5,
                        price_score=0.5,
                        freshness_score=0.5,
                        completeness_score=0.5,
                        available_dates=list(c.available_dates),
                        earliest_available=c.earliest_available,
                    )
                    for i, c in enumerate(filter_result.candidates)
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
        response: NLSearchResponse,
        limit: int,
        *,
        ttl: Optional[int] = None,
    ) -> None:
        """Cache the response."""
        try:
            await self.search_cache.cache_response(
                query,
                response.model_dump(),
                user_location=user_location,
                limit=limit,
                ttl=ttl,
                region_code=self._region_code,
            )
        except Exception as e:
            logger.warning(f"Failed to cache response: {e}")

    def _transform_instructor_results(
        self,
        raw_results: List[Dict[str, Any]],
        parsed_query: ParsedQuery,
    ) -> List[NLSearchResultItem]:
        """
        Transform raw DB results into instructor-level result items.

        Args:
            raw_results: Results from search_with_instructor_data
            parsed_query: Parsed query for price filtering

        Returns:
            List of NLSearchResultItem objects
        """
        results: List[NLSearchResultItem] = []

        for row in raw_results:
            # Parse matching services from JSON
            services = row["matching_services"]
            if not services:
                continue

            # Apply price filter if specified
            if parsed_query.max_price:
                services = [s for s in services if s["price_per_hour"] <= parsed_query.max_price]
                if not services:
                    continue
            match_count = len(services)

            # Build best match
            best = services[0]
            best_match = ServiceMatch(
                service_id=best["service_id"],
                service_catalog_id=best["service_catalog_id"],
                name=best["name"],
                description=best.get("description"),
                price_per_hour=int(best["price_per_hour"]),
                relevance_score=round(float(best["relevance_score"]), 3),
            )

            # Build other matches (max 3)
            other_matches = [
                ServiceMatch(
                    service_id=s["service_id"],
                    service_catalog_id=s["service_catalog_id"],
                    name=s["name"],
                    description=s.get("description"),
                    price_per_hour=int(s["price_per_hour"]),
                    relevance_score=round(float(s["relevance_score"]), 3),
                )
                for s in services[1:4]
            ]

            # Build instructor summary
            instructor = InstructorSummary(
                id=row["instructor_id"],
                first_name=row["first_name"],
                last_initial=row["last_initial"] or "",
                profile_picture_url=self._build_photo_url(row.get("profile_picture_key")),
                bio_snippet=row.get("bio_snippet"),
                verified=bool(row.get("verified", False)),
                years_experience=row.get("years_experience"),
            )

            # Build rating summary
            rating = RatingSummary(
                average=round(row["avg_rating"], 2) if row.get("avg_rating") else None,
                count=row.get("review_count", 0),
            )

            results.append(
                NLSearchResultItem(
                    instructor_id=row["instructor_id"],
                    instructor=instructor,
                    rating=rating,
                    coverage_areas=row.get("coverage_areas", []),
                    best_match=best_match,
                    other_matches=other_matches,
                    total_matching_services=match_count,
                    relevance_score=best_match.relevance_score,
                )
            )

        return results

    def _build_instructor_response(
        self,
        query: str,
        parsed_query: ParsedQuery,
        results: List[NLSearchResultItem],
        limit: int,
        metrics: SearchMetrics,
        *,
        filter_result: Optional[FilterResult] = None,
        budget: Optional[RequestBudget] = None,
    ) -> NLSearchResponse:
        """
        Build the final instructor-level response.

        Args:
            query: Original search query
            parsed_query: Parsed query details
            results: Transformed instructor results
            limit: Requested limit
            metrics: Search metrics

        Returns:
            Complete NLSearchResponse
        """
        # Build parsed query info
        parsed_info = ParsedQueryInfo(
            service_query=parsed_query.service_query,
            location=parsed_query.location_text,
            max_price=parsed_query.max_price,
            date=parsed_query.date.isoformat() if parsed_query.date else None,
            time_after=parsed_query.time_after,
            time_before=parsed_query.time_before,
            audience_hint=parsed_query.audience_hint,
            skill_level=parsed_query.skill_level,
            urgency=parsed_query.urgency,
        )

        # Build metadata
        location_resolution = filter_result.location_resolution if filter_result else None
        location_not_found = bool(getattr(location_resolution, "not_found", False))

        location_resolved = self._format_location_resolved(location_resolution)

        soft_filter_message: Optional[str] = None
        if filter_result and filter_result.soft_filtering_used:
            soft_filter_message = self._generate_soft_filter_message(
                parsed_query,
                filter_result.filter_stats,
                location_resolution,
                location_resolved,
                relaxed_constraints=filter_result.relaxed_constraints,
                result_count=len(results),
            )

        meta = NLSearchMeta(
            query=query,
            corrected_query=parsed_query.corrected_query,
            parsed=parsed_info,
            total_results=len(results),
            limit=limit,
            latency_ms=metrics.total_latency_ms,
            cache_hit=metrics.cache_hit,
            degraded=metrics.degraded,
            degradation_reasons=metrics.degradation_reasons,
            skipped_operations=list(budget.skipped_operations) if budget else [],
            parsing_mode=parsed_query.parsing_mode,
            filters_applied=filter_result.filters_applied if filter_result else [],
            soft_filtering_used=filter_result.soft_filtering_used if filter_result else False,
            filter_stats=filter_result.filter_stats if filter_result else None,
            soft_filter_message=soft_filter_message,
            location_resolved=location_resolved,
            location_not_found=location_not_found,
        )

        return NLSearchResponse(results=results[:limit], meta=meta)

    def _build_search_diagnostics(
        self,
        *,
        timer: PipelineTimer,
        budget: Optional[RequestBudget],
        parsed_query: Optional[ParsedQuery],
        pre_data: Optional[PreOpenAIData],
        post_data: Optional[PostOpenAIData],
        location_resolution: Optional["ResolvedLocation"],
        query_embedding: Optional[List[float]],
        results_count: int,
        cache_hit: bool,
        parsing_mode: str,
        candidates_flow: Dict[str, int],
        total_latency_ms: Optional[int] = None,
    ) -> SearchDiagnostics:
        if budget is None:
            fallback_budget = int(get_search_config().search_budget_ms)
            budget_info = BudgetInfo(
                initial_ms=fallback_budget,
                remaining_ms=fallback_budget,
                over_budget=False,
                skipped_operations=[],
                degradation_level="none",
            )
        else:
            budget_info = BudgetInfo(
                initial_ms=budget.total_ms,
                remaining_ms=budget.remaining_ms,
                over_budget=budget.is_over_budget,
                skipped_operations=list(budget.skipped_operations),
                degradation_level=budget.degradation_level.value,
            )

        after_text_search = candidates_flow.get("after_text_search")
        if after_text_search is None and pre_data is not None:
            after_text_search = len(pre_data.text_results or {})

        after_vector_search = candidates_flow.get("after_vector_search")
        if after_vector_search is None and post_data is not None:
            after_vector_search = int(post_data.total_candidates)

        initial_candidates = candidates_flow.get("initial_candidates")
        if initial_candidates is None and post_data is not None:
            initial_candidates = int(post_data.total_candidates)

        after_location_filter = candidates_flow.get("after_location_filter")
        after_price_filter = candidates_flow.get("after_price_filter")
        after_availability_filter = candidates_flow.get("after_availability_filter")
        if post_data is not None and post_data.filter_result.filter_stats:
            stats = post_data.filter_result.filter_stats
            if after_location_filter is None:
                after_location_filter = stats.get("after_location")
            if after_price_filter is None:
                after_price_filter = stats.get("after_price")
            if after_availability_filter is None:
                after_availability_filter = stats.get("after_availability")

        final_results = candidates_flow.get("final_results")
        if final_results is None:
            final_results = results_count

        location_info: Optional[LocationResolutionInfo] = None
        if parsed_query and parsed_query.location_text:
            resolved_name = None
            resolved_regions: Optional[List[str]] = None
            successful_tier: Optional[int] = None
            if location_resolution:
                if location_resolution.region_name:
                    resolved_name = location_resolution.region_name
                elif location_resolution.borough:
                    resolved_name = location_resolution.borough
                if location_resolution.tier is not None:
                    try:
                        successful_tier = int(location_resolution.tier.value)
                    except Exception:
                        successful_tier = None
                if location_resolution.candidates:
                    names: List[str] = []
                    for candidate in location_resolution.candidates:
                        if not isinstance(candidate, dict):
                            continue
                        name = candidate.get("region_name")
                        if name:
                            names.append(str(name))
                    if names:
                        resolved_regions = list(dict.fromkeys(names))

            location_info = LocationResolutionInfo(
                query=parsed_query.location_text,
                resolved_name=resolved_name,
                resolved_regions=resolved_regions,
                successful_tier=successful_tier,
                tiers=[LocationTierResult(**tier) for tier in timer.location_tiers],
            )

        return SearchDiagnostics(
            total_latency_ms=(
                int(total_latency_ms)
                if total_latency_ms is not None
                else (budget.elapsed_ms if budget else 0)
            ),
            pipeline_stages=[PipelineStage(**stage) for stage in timer.stages],
            budget=budget_info,
            location_resolution=location_info,
            initial_candidates=int(initial_candidates or 0),
            after_text_search=int(after_text_search or 0),
            after_vector_search=int(after_vector_search or 0),
            after_location_filter=int(after_location_filter or 0),
            after_price_filter=int(after_price_filter or 0),
            after_availability_filter=int(after_availability_filter or 0),
            final_results=int(final_results or 0),
            cache_hit=cache_hit,
            parsing_mode=parsing_mode,
            embedding_used=bool(query_embedding),
            vector_search_used=bool(post_data.vector_search_used) if post_data else False,
        )

    def _format_location_resolved(
        self, location_resolution: Optional["ResolvedLocation"]
    ) -> Optional[str]:
        """Format a human-friendly resolved location string for UI/debug."""
        if not location_resolution:
            return None

        if location_resolution.resolved:
            return location_resolution.region_name or location_resolution.borough

        if not (location_resolution.requires_clarification and location_resolution.candidates):
            return None

        candidate_names: List[str] = []
        for candidate in location_resolution.candidates:
            if not isinstance(candidate, dict):
                continue
            name = candidate.get("region_name")
            if name is None:
                continue
            text = str(name).strip()
            if text:
                candidate_names.append(text)

        if not candidate_names:
            return None

        # De-dupe while preserving order for stable display.
        seen: set[str] = set()
        unique_names: List[str] = []
        for name in candidate_names:
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            unique_names.append(name)

        def _split(name: str) -> tuple[str, str]:
            if "-" in name:
                base, suffix = name.split("-", 1)
                return base.strip(), suffix.strip()
            if " (" in name and name.endswith(")"):
                base, rest = name.split(" (", 1)
                return base.strip(), rest[:-1].strip()
            return "", ""

        split_parts = [_split(name) for name in unique_names]
        prefixes = {p for p, s in split_parts if p and s}
        if prefixes and len(prefixes) == 1 and all(s for _, s in split_parts):
            prefix = next(iter(prefixes))
            suffixes = sorted({s for _, s in split_parts}, key=lambda s: s.lower())
            return f"{prefix} ({', '.join(suffixes)})"

        return ", ".join(unique_names[:5])

    def _generate_soft_filter_message(
        self,
        parsed: ParsedQuery,
        filter_stats: Dict[str, int],
        location_resolution: Optional["ResolvedLocation"],
        location_resolved: Optional[str],
        *,
        relaxed_constraints: List[str],
        result_count: int,
    ) -> Optional[str]:
        """Generate a user-facing message when soft filtering/relaxation is used."""
        messages: List[str] = []

        # Location constraint
        if parsed.location_text:
            if location_resolution and location_resolution.not_found:
                messages.append(f"Couldn't find location '{parsed.location_text}'")
            elif filter_stats.get("after_location") == 0:
                messages.append(
                    f"No instructors found in {location_resolved or parsed.location_text}"
                )

        # Availability constraint
        if (parsed.date or parsed.time_after) and filter_stats.get("after_availability") == 0:
            if parsed.date:
                messages.append(f"No availability on {parsed.date.strftime('%A, %b %d')}")
            else:
                messages.append("No availability matching your time constraints")

        # Price constraint
        if parsed.max_price is not None and filter_stats.get("after_price") == 0:
            messages.append(f"No instructors under ${parsed.max_price}")

        if not messages:
            # Even if we don't have a specific "no results" cause, still report what we relaxed.
            messages.append("No exact matches")

        location_related = any(
            m.startswith("No instructors found in") or m.startswith("Couldn't find location")
            for m in messages
        ) or ("location" in relaxed_constraints)

        relaxed = [c for c in relaxed_constraints if c]
        relaxed_text = f"Relaxed: {', '.join(relaxed)}." if relaxed else None

        if result_count > 0:
            lead = (
                f"Showing {result_count} results from nearby areas."
                if location_related
                else f"Showing {result_count} results."
            )
        else:
            lead = "No results found."

        parts = [lead, ". ".join(messages) + ".", relaxed_text]
        return " ".join(p for p in parts if p).strip()

    def _build_photo_url(self, key: Optional[str]) -> Optional[str]:
        """Build Cloudflare R2 URL for profile photo."""
        if not key:
            return None
        # Use R2 assets domain from settings
        assets_domain = getattr(settings, "r2_public_url", "https://assets.instainstru.com")
        return f"{assets_domain}/{key}"
