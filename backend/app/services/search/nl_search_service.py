"""Main NL search service facade."""

from __future__ import annotations

from dataclasses import dataclass
import time
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

from app.core.exceptions import raise_503_if_pool_exhaustion
from app.schemas.nl_search import NLSearchResponse, NLSearchResultItem, StageStatus
from app.services.search.embedding_service import EmbeddingService
from app.services.search.filter_service import FilterService
from app.services.search.location_embedding_service import LocationEmbeddingService
from app.services.search.location_llm_service import LocationLLMService
from app.services.search.nl_pipeline import (
    hydration,
    location,
    postflight,
    preflight,
    response,
    runtime,
)
from app.services.search.nl_pipeline.models import PipelineTimer, SearchMetrics
from app.services.search.ranking_service import RankingService
from app.services.search.retriever import PostgresRetriever
from app.services.search.search_cache import SearchCacheService

if TYPE_CHECKING:
    import asyncio

    from app.services.cache_service import CacheService
    from app.services.search.location_resolver import ResolvedLocation
    from app.services.search.nl_pipeline.models import (
        LocationLLMCache,
        PostOpenAIData,
        PreOpenAIData,
        UnresolvedLocationInfo,
    )
    from app.services.search.query_parser import ParsedQuery
    from app.services.search.request_budget import RequestBudget
    from app.services.search.retriever import RetrievalResult


@dataclass(slots=True)
class _SearchRequest:
    query: str
    user_location: Optional[Tuple[float, float]]
    limit: int
    user_id: Optional[str]
    requester_timezone: Optional[str]
    budget_ms: Optional[int]
    subcategory_id: Optional[str]
    include_diagnostics: bool
    force_skip_tier5: bool
    force_skip_tier4: bool
    force_skip_vector: bool
    force_skip_embedding: bool
    force_high_load: bool


@dataclass(slots=True)
class _SearchContext:
    perf_start: float
    metrics: SearchMetrics
    timer: Optional[PipelineTimer]
    candidates_flow: Dict[str, int]
    effective_filters: Optional[Dict[str, List[str]]]
    effective_skill_levels: List[str]
    cache_filters: Optional[Dict[str, object]]
    cache_check_ms: int = 0
    inflight_incremented: bool = False


@dataclass(slots=True)
class _CachedSearchResult:
    response: NLSearchResponse


@dataclass(slots=True)
class _PreflightStageResult:
    budget: RequestBudget
    parsed_query: ParsedQuery
    pre_data: PreOpenAIData
    embedding_task: Optional[asyncio.Task[tuple[Optional[List[float]], int, Optional[str]]]]
    tier5_task: Optional[location.Tier5Task]
    tier5_started_at: Optional[float]


@dataclass(slots=True)
class _AIStageResult:
    query_embedding: Optional[List[float]]
    embedding_reason: Optional[str]
    location_resolution: ResolvedLocation
    location_llm_cache: Optional[LocationLLMCache]
    unresolved_info: Optional[UnresolvedLocationInfo]


class NLSearchService:
    """Public NL search service entrypoint."""

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

    async def _run_preflight_stage(
        self,
        request: _SearchRequest,
        context: _SearchContext,
    ) -> _CachedSearchResult | _PreflightStageResult:
        cached, context.cache_check_ms = await response.get_cached_search_response(
            self,
            query=request.query,
            user_location=request.user_location,
            limit=request.limit,
            timer=context.timer,
            cache_filters=context.cache_filters,
        )
        if cached:
            return _CachedSearchResult(
                response=response.build_cached_response(
                    self,
                    cached=cached,
                    perf_start=context.perf_start,
                    cache_check_ms=context.cache_check_ms,
                    timer=context.timer,
                    candidates_flow=context.candidates_flow,
                    include_diagnostics=request.include_diagnostics,
                )
            )

        (
            budget,
            parsed_query_cached,
            parsed_query_future,
            notify_parsed,
            embedding_task,
        ) = await preflight.prepare_uncached_pipeline_for_service(
            self,
            query=request.query,
            budget_ms=request.budget_ms,
            force_high_load=request.force_high_load,
            force_skip_vector_search=request.force_skip_vector or request.force_skip_embedding,
        )
        context.inflight_incremented = True
        (
            pre_data,
            parsed_query,
            embedding_task,
            tier5_task,
            tier5_started_at,
        ) = await preflight.run_preflight_and_parse_for_service(
            self,
            query=request.query,
            user_id=request.user_id,
            user_location=request.user_location,
            parsed_query_cached=parsed_query_cached,
            parsed_query_future=parsed_query_future,
            notify_parsed=notify_parsed,
            embedding_task=embedding_task,
            budget=budget,
            effective_skill_levels=context.effective_skill_levels,
            metrics=context.metrics,
            timer=context.timer,
            candidates_flow=context.candidates_flow,
            force_skip_tier5=request.force_skip_tier5,
        )
        return _PreflightStageResult(
            budget=budget,
            parsed_query=parsed_query,
            pre_data=pre_data,
            embedding_task=embedding_task,
            tier5_task=tier5_task,
            tier5_started_at=tier5_started_at,
        )

    async def _run_ai_stage(
        self,
        request: _SearchRequest,
        context: _SearchContext,
        preflight_result: _PreflightStageResult,
    ) -> _AIStageResult:
        query_embedding, embedding_reason = await preflight.resolve_query_embedding_for_service(
            self,
            parsed_query=preflight_result.parsed_query,
            pre_data=preflight_result.pre_data,
            embedding_task=preflight_result.embedding_task,
            budget=preflight_result.budget,
            metrics=context.metrics,
            timer=context.timer,
            force_skip_vector=request.force_skip_vector,
            force_skip_embedding=request.force_skip_embedding,
        )
        (
            location_resolution,
            location_llm_cache,
            unresolved_info,
        ) = await location.resolve_location_stage_for_service(
            self,
            parsed_query=preflight_result.parsed_query,
            pre_data=preflight_result.pre_data,
            user_location=request.user_location,
            budget=preflight_result.budget,
            timer=context.timer,
            force_skip_tier5=request.force_skip_tier5,
            force_skip_tier4=request.force_skip_tier4,
            force_skip_embedding=request.force_skip_embedding,
            tier5_task=preflight_result.tier5_task,
            tier5_started_at=preflight_result.tier5_started_at,
        )
        return _AIStageResult(
            query_embedding=query_embedding,
            embedding_reason=embedding_reason,
            location_resolution=location_resolution,
            location_llm_cache=location_llm_cache,
            unresolved_info=unresolved_info,
        )

    async def _run_postflight_stage(
        self,
        request: _SearchRequest,
        context: _SearchContext,
        preflight_result: _PreflightStageResult,
        ai_result: _AIStageResult,
    ) -> NLSearchResponse:
        post_data, retrieval_result = await postflight.run_postflight_stage_for_service(
            self,
            pre_data=preflight_result.pre_data,
            parsed_query=preflight_result.parsed_query,
            query_embedding=ai_result.query_embedding,
            location_resolution=ai_result.location_resolution,
            location_llm_cache=ai_result.location_llm_cache,
            unresolved_info=ai_result.unresolved_info,
            user_location=request.user_location,
            limit=request.limit,
            requester_timezone=request.requester_timezone,
            taxonomy_filter_selections=context.effective_filters,
            subcategory_id=request.subcategory_id,
            embedding_reason=ai_result.embedding_reason,
            budget=preflight_result.budget,
            metrics=context.metrics,
            timer=context.timer,
            candidates_flow=context.candidates_flow,
        )
        results, hydrate_ms = await hydration.hydrate_results_for_service(
            post_data=post_data,
            limit=request.limit,
            metrics=context.metrics,
            timer=context.timer,
            candidates_flow=context.candidates_flow,
        )
        return await self._build_and_cache_response(
            request=request,
            context=context,
            preflight_result=preflight_result,
            ai_result=ai_result,
            post_data=post_data,
            retrieval_result=retrieval_result,
            hydrate_ms=hydrate_ms,
            results=results,
        )

    async def _build_and_cache_response(
        self,
        *,
        request: _SearchRequest,
        context: _SearchContext,
        preflight_result: _PreflightStageResult,
        ai_result: _AIStageResult,
        post_data: "PostOpenAIData",
        retrieval_result: "RetrievalResult",
        hydrate_ms: int,
        results: List[NLSearchResultItem],
    ) -> NLSearchResponse:
        context.metrics.total_latency_ms = int((time.time() - context.metrics.total_start) * 1000)
        response_build_start = time.perf_counter()
        response_obj = response.build_instructor_response(
            query=request.query,
            parsed_query=preflight_result.parsed_query,
            results=results,
            limit=request.limit,
            metrics=context.metrics,
            filter_result=post_data.filter_result,
            inferred_filters=post_data.inferred_filters,
            effective_subcategory_id=post_data.effective_subcategory_id,
            effective_subcategory_name=post_data.effective_subcategory_name,
            available_content_filters=post_data.available_content_filters,
            budget=preflight_result.budget,
        )
        response_build_ms = int((time.perf_counter() - response_build_start) * 1000)
        if context.timer:
            context.timer.record_stage(
                "build_response",
                response_build_ms,
                StageStatus.SUCCESS.value,
                {"result_count": len(response_obj.results)},
            )
        cache_write_ms = await response.record_metrics_and_cache(
            self,
            query=request.query,
            user_location=request.user_location,
            limit=request.limit,
            parsed_query=preflight_result.parsed_query,
            response_obj=response_obj,
            metrics=context.metrics,
            cache_check_ms=context.cache_check_ms,
            hydrate_ms=hydrate_ms,
            response_build_ms=response_build_ms,
            cache_filters=context.cache_filters,
        )
        response.attach_diagnostics_and_perf_log(
            self,
            response_obj=response_obj,
            timer=context.timer,
            budget=preflight_result.budget,
            parsed_query=preflight_result.parsed_query,
            pre_data=preflight_result.pre_data,
            post_data=post_data,
            location_resolution=ai_result.location_resolution,
            query_embedding=ai_result.query_embedding,
            candidates_flow=context.candidates_flow,
            metrics=context.metrics,
            retrieval_result=retrieval_result,
            cache_check_ms=context.cache_check_ms,
            hydrate_ms=hydrate_ms,
            response_build_ms=response_build_ms,
            cache_write_ms=cache_write_ms,
            limit=request.limit,
            include_diagnostics=request.include_diagnostics,
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
        effective_filters, effective_skill_levels, cache_filters = preflight.prepare_search_filters(
            explicit_skill_levels=explicit_skill_levels,
            taxonomy_filter_selections=taxonomy_filter_selections,
            subcategory_id=subcategory_id,
        )
        request = _SearchRequest(
            query=query,
            user_location=user_location,
            limit=limit,
            user_id=user_id,
            requester_timezone=requester_timezone,
            budget_ms=budget_ms,
            subcategory_id=subcategory_id,
            include_diagnostics=include_diagnostics,
            force_skip_tier5=force_skip_tier5,
            force_skip_tier4=force_skip_tier4,
            force_skip_vector=force_skip_vector,
            force_skip_embedding=force_skip_embedding,
            force_high_load=force_high_load,
        )
        context = _SearchContext(
            perf_start=time.perf_counter(),
            metrics=SearchMetrics(total_start=time.time()),
            timer=PipelineTimer() if include_diagnostics else None,
            candidates_flow=response.build_candidates_flow(include_diagnostics),
            effective_filters=effective_filters,
            effective_skill_levels=effective_skill_levels,
            cache_filters=cache_filters,
        )

        try:
            preflight_result = await self._run_preflight_stage(request, context)
            if isinstance(preflight_result, _CachedSearchResult):
                return preflight_result.response

            ai_result = await self._run_ai_stage(request, context, preflight_result)
            return await self._run_postflight_stage(request, context, preflight_result, ai_result)
        except Exception as exc:
            raise_503_if_pool_exhaustion(exc)
            raise
        finally:
            if context.inflight_incremented:
                await runtime._decrement_search_inflight()
