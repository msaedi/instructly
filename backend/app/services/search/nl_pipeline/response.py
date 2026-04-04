"""Response assembly, caching, and perf-log helpers for NL search."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Dict, List, Optional, Sequence, cast

from app.schemas.nl_search import (
    NLSearchContentFilterDefinition,
    NLSearchMeta,
    NLSearchResponse,
    NLSearchResultItem,
    ParsedQueryInfo,
    StageStatus,
)
from app.services.search import metrics as metrics_module
from app.services.search.nl_pipeline import runtime
from app.services.search.nl_pipeline.protocols import LoggerLike, SearchServiceLike
from app.services.search.nl_pipeline.response_diagnostics import (
    build_budget_diagnostics,
    build_candidate_flow_diagnostics,
    build_candidates_flow,
    build_location_diagnostics,
    build_search_diagnostics,
    format_location_resolved,
    generate_soft_filter_message,
)
from app.services.search.search_cache import SearchCacheService

if TYPE_CHECKING:
    from app.services.search.filter_service import FilterResult
    from app.services.search.location_resolver import ResolvedLocation
    from app.services.search.nl_pipeline.models import (
        PipelineTimer,
        PostOpenAIData,
        PreOpenAIData,
        SearchMetrics,
    )
    from app.services.search.query_parser import ParsedQuery
    from app.services.search.request_budget import RequestBudget

logger = logging.getLogger(__name__)


async def check_cache(
    *,
    search_cache: SearchCacheService,
    query: str,
    user_location: Optional[tuple[float, float]],
    limit: int,
    region_code: str,
    logger: LoggerLike,
    filters: Optional[Dict[str, object]] = None,
) -> Optional[Dict[str, object]]:
    """Check for cached response."""
    try:
        return cast(
            Optional[Dict[str, object]],
            await search_cache.get_cached_response(
                query,
                user_location,
                filters=filters,
                limit=limit,
                region_code=region_code,
            ),
        )
    except Exception as exc:
        logger.warning("Cache check failed: %s", exc)
        return None


async def check_cache_for_service(
    service: SearchServiceLike,
    query: str,
    user_location: Optional[tuple[float, float]],
    limit: int,
    *,
    filters: Optional[Dict[str, object]] = None,
) -> Optional[Dict[str, object]]:
    return await check_cache(
        search_cache=service.search_cache,
        query=query,
        user_location=user_location,
        limit=limit,
        region_code=service._region_code,
        logger=logger,
        filters=filters,
    )


async def cache_response(
    *,
    search_cache: SearchCacheService,
    query: str,
    user_location: Optional[tuple[float, float]],
    response: NLSearchResponse,
    limit: int,
    region_code: str,
    logger: LoggerLike,
    ttl: Optional[int] = None,
    filters: Optional[Dict[str, object]] = None,
) -> None:
    """Cache the response."""
    try:
        await search_cache.cache_response(
            query,
            response.model_dump(),
            user_location=user_location,
            filters=filters,
            limit=limit,
            ttl=ttl,
            region_code=region_code,
        )
    except Exception as exc:
        logger.warning("Failed to cache response: %s", exc)


async def cache_response_for_service(
    service: SearchServiceLike,
    query: str,
    user_location: Optional[tuple[float, float]],
    response_obj: NLSearchResponse,
    limit: int,
    *,
    ttl: Optional[int] = None,
    filters: Optional[Dict[str, object]] = None,
) -> None:
    await cache_response(
        search_cache=service.search_cache,
        query=query,
        user_location=user_location,
        response=response_obj,
        limit=limit,
        region_code=service._region_code,
        logger=logger,
        ttl=ttl,
        filters=filters,
    )


def build_instructor_response(
    query: str,
    parsed_query: ParsedQuery,
    results: Sequence[NLSearchResultItem],
    limit: int,
    metrics: SearchMetrics,
    filter_result: Optional[FilterResult] = None,
    inferred_filters: Optional[Dict[str, List[str]]] = None,
    effective_subcategory_id: Optional[str] = None,
    effective_subcategory_name: Optional[str] = None,
    available_content_filters: Optional[Sequence[NLSearchContentFilterDefinition]] = None,
    budget: Optional[RequestBudget] = None,
) -> NLSearchResponse:
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
        lesson_type=parsed_query.lesson_type,
        use_user_location=parsed_query.use_user_location,
    )
    location_resolution = filter_result.location_resolution if filter_result else None
    location_resolved = format_location_resolved(location_resolution)
    soft_filter_message = None
    if filter_result and filter_result.soft_filtering_used:
        soft_filter_message = generate_soft_filter_message(
            parsed=parsed_query,
            filter_stats=filter_result.filter_stats,
            location_resolution=location_resolution,
            location_resolved=location_resolved,
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
        inferred_filters=inferred_filters or {},
        effective_subcategory_id=effective_subcategory_id,
        effective_subcategory_name=effective_subcategory_name,
        available_content_filters=available_content_filters or [],
        soft_filtering_used=filter_result.soft_filtering_used if filter_result else False,
        filter_stats=filter_result.filter_stats if filter_result else None,
        soft_filter_message=soft_filter_message,
        location_resolved=location_resolved,
        location_not_found=bool(getattr(location_resolution, "not_found", False)),
    )
    return NLSearchResponse(results=list(results[:limit]), meta=meta)


async def get_cached_search_response(
    service: SearchServiceLike,
    *,
    query: str,
    user_location: Optional[tuple[float, float]],
    limit: int,
    timer: Optional[PipelineTimer],
    cache_filters: Optional[Dict[str, object]],
) -> tuple[Optional[Dict[str, object]], int]:
    if timer:
        timer.start_stage("cache_check")
    cache_check_start = time.perf_counter()
    cached = await check_cache(
        search_cache=service.search_cache,
        query=query,
        user_location=user_location,
        limit=limit,
        region_code=service._region_code,
        logger=logger,
        filters=cache_filters,
    )
    cache_check_ms = int((time.perf_counter() - cache_check_start) * 1000)
    if timer:
        timer.end_stage(
            status=StageStatus.CACHE_HIT.value if cached else StageStatus.SUCCESS.value,
            details={"latency_ms": cache_check_ms},
        )
    return cached, cache_check_ms


def build_cached_response(
    service: SearchServiceLike,
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
    metrics_module.record_search_metrics(
        total_latency_ms=cached_total_ms,
        stage_latencies={"cache_check": cache_check_ms},
        cache_hit=True,
        parsing_mode=str(meta.get("parsing_mode") or "regex"),
        result_count=len(cached_results),
        degraded=False,
        degradation_reasons=[],
    )
    if runtime._PERF_LOG_ENABLED and cached_total_ms >= runtime._PERF_LOG_SLOW_MS:
        logger.info(
            "NL search timings (cache_hit): %s",
            {
                "cache_check_ms": cache_check_ms,
                "total_ms": cached_total_ms,
                "limit": meta.get("limit", 0),
                "region": service._region_code,
            },
        )
    response_obj = NLSearchResponse(**cached)
    if include_diagnostics and timer:
        response_obj.meta.diagnostics = build_search_diagnostics(
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


async def record_metrics_and_cache(
    service: SearchServiceLike,
    *,
    query: str,
    user_location: Optional[tuple[float, float]],
    limit: int,
    parsed_query: ParsedQuery,
    response_obj: NLSearchResponse,
    metrics: SearchMetrics,
    cache_check_ms: int,
    hydrate_ms: int,
    response_build_ms: int,
    cache_filters: Optional[Dict[str, object]],
) -> int:
    metrics_module.record_search_metrics(
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
    await cache_response(
        search_cache=service.search_cache,
        query=query,
        user_location=user_location,
        response=response_obj,
        limit=limit,
        region_code=service._region_code,
        logger=logger,
        ttl=degraded_ttl,
        filters=cache_filters,
    )
    return int((time.perf_counter() - cache_write_start) * 1000)


def attach_diagnostics_and_perf_log(
    service: SearchServiceLike,
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
    retrieval_result: object,
    cache_check_ms: int,
    hydrate_ms: int,
    response_build_ms: int,
    cache_write_ms: int,
    limit: int,
    include_diagnostics: bool,
) -> None:
    if include_diagnostics and timer:
        response_obj.meta.diagnostics = build_search_diagnostics(
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
    if runtime._PERF_LOG_ENABLED and metrics.total_latency_ms >= runtime._PERF_LOG_SLOW_MS:
        retrieval_stats = {
            "text_search_ms": int(getattr(retrieval_result, "text_search_latency_ms", 0) or 0),
            "vector_search_ms": int(getattr(retrieval_result, "vector_search_latency_ms", 0) or 0),
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
                "region": service._region_code,
            },
        )


__all__ = [
    "build_budget_diagnostics",
    "build_candidate_flow_diagnostics",
    "build_candidates_flow",
    "build_cached_response",
    "build_instructor_response",
    "build_location_diagnostics",
    "build_search_diagnostics",
    "cache_response",
    "cache_response_for_service",
    "check_cache",
    "check_cache_for_service",
    "format_location_resolved",
    "generate_soft_filter_message",
    "get_cached_search_response",
    "record_metrics_and_cache",
    "attach_diagnostics_and_perf_log",
]
