"""Shared postflight helpers used by the NL search orchestration layer."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Callable, Dict, List, Optional, Tuple, cast

from sqlalchemy.orm import Session

from app.repositories.filter_repository import FilterRepository
from app.repositories.retriever_repository import RetrieverRepository
from app.repositories.unresolved_location_query_repository import (
    UnresolvedLocationQueryRepository,
)
from app.services.search import (
    filter_service as filter_service_module,
    ranking_service as ranking_service_module,
    retriever as retriever_module,
)
from app.services.search.nl_pipeline.models import (
    LocationLLMCache,
    PostOpenAIData,
    PreOpenAIData,
    UnresolvedLocationInfo,
)
from app.services.search.nl_pipeline.postflight_steps import PostOpenAIState
from app.services.search.nl_pipeline.protocols import SearchServiceLike

if TYPE_CHECKING:
    from app.services.search.location_resolver import LocationResolver, ResolvedLocation
    from app.services.search.nl_pipeline.models import SearchMetrics
    from app.services.search.query_parser import ParsedQuery
    from app.services.search.ranking_service import RankedResult, RankingResult
    from app.services.search.request_budget import RequestBudget
    from app.services.search.retriever import RetrievalResult

logger = logging.getLogger(__name__)


def select_instructor_ids(ranked: List[RankedResult], limit: int) -> List[str]:
    ordered: List[str] = []
    seen: set[str] = set()
    for result in ranked:
        if result.instructor_id in seen:
            continue
        seen.add(result.instructor_id)
        ordered.append(result.instructor_id)
        if len(ordered) >= limit:
            break
    return ordered


def build_post_openai_data(
    *,
    state: PostOpenAIState,
    instructor_rows: List[Dict[str, object]],
    distance_meters: Dict[str, float],
) -> PostOpenAIData:
    return PostOpenAIData(
        filter_result=state.filter_result,
        ranking_result=state.ranking_result,
        retrieval_candidates=state.retrieval_candidates,
        instructor_rows=instructor_rows,
        distance_meters=distance_meters,
        text_latency_ms=state.text_latency_ms,
        vector_latency_ms=state.vector_latency_ms,
        filter_latency_ms=state.filter_latency_ms,
        rank_latency_ms=state.rank_latency_ms,
        vector_search_used=state.vector_search_used,
        total_candidates=len(state.retrieval_candidates),
        filter_failed=state.filter_failed,
        ranking_failed=state.ranking_failed,
        skip_vector=state.skip_vector,
        inferred_filters=state.inferred_filters,
        effective_taxonomy_filters=state.effective_taxonomy_filters,
        effective_subcategory_id=state.effective_subcategory_id,
        effective_subcategory_name=state.effective_subcategory_name,
        available_content_filters=state.available_content_filters,
    )


def load_instructor_cards(
    *,
    retriever_repository: RetrieverRepository,
    filter_repository: FilterRepository,
    ranking_result: RankingResult,
    limit: int,
    location_resolution: Optional[ResolvedLocation],
    select_instructor_ids_fn: Callable[[List[RankedResult], int], List[str]],
    distance_region_ids_fn: Callable[[Optional[ResolvedLocation]], Optional[List[str]]],
) -> tuple[List[Dict[str, object]], Dict[str, float]]:
    ordered_instructor_ids = select_instructor_ids_fn(ranking_result.results, limit)
    instructor_rows = cast(
        List[Dict[str, object]],
        retriever_repository.get_instructor_cards(ordered_instructor_ids),
    )
    distance_meters: Dict[str, float] = {}
    region_ids = distance_region_ids_fn(location_resolution)
    if region_ids:
        distance_meters = filter_repository.get_instructor_min_distance_to_regions(
            ordered_instructor_ids,
            region_ids,
        )
    return instructor_rows, distance_meters


def persist_search_side_effects(
    *,
    db: Session,
    pre_data: PreOpenAIData,
    location_llm_cache: Optional[LocationLLMCache],
    unresolved_info: Optional[UnresolvedLocationInfo],
    location_resolver: LocationResolver,
    unresolved_location_query_repository_cls: type[UnresolvedLocationQueryRepository],
) -> None:
    if location_llm_cache:
        location_resolver.cache_llm_alias(
            location_llm_cache.normalized,
            location_llm_cache.region_ids,
            confidence=location_llm_cache.confidence,
        )
    if pre_data.cached_alias_normalized:
        cached_alias = location_resolver.repository.find_cached_alias(
            pre_data.cached_alias_normalized,
            source="llm",
        )
        if cached_alias:
            location_resolver.repository.increment_alias_user_count(cached_alias)
    if unresolved_info:
        unresolved_repo = unresolved_location_query_repository_cls(db)
        unresolved_repo.track_unresolved(
            unresolved_info.normalized,
            original_query=unresolved_info.original_query,
        )


async def retrieve_candidates(
    service: SearchServiceLike,
    parsed_query: ParsedQuery,
    metrics: SearchMetrics,
) -> RetrievalResult:
    start = time.time()
    try:
        result = await service.retriever.search(parsed_query)
        if result.degraded:
            metrics.degraded = True
            if result.degradation_reason:
                metrics.degradation_reasons.append(result.degradation_reason)
    except Exception as exc:
        logger.error("Retrieval failed: %s", exc)
        result = retriever_module.RetrievalResult(
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
    return cast(retriever_module.RetrievalResult, result)


async def filter_candidates(
    service: SearchServiceLike,
    retrieval_result: RetrievalResult,
    parsed_query: ParsedQuery,
    user_location: Optional[Tuple[float, float]],
    metrics: SearchMetrics,
    *,
    requester_timezone: Optional[str] = None,
) -> filter_service_module.FilterResult:
    start = time.time()
    try:
        result = await service.filter_service.filter_candidates(
            retrieval_result.candidates,
            parsed_query,
            user_location=user_location,
            requester_timezone=requester_timezone,
        )
    except Exception as exc:
        logger.error("Filtering failed: %s", exc)
        result = filter_service_module.FilterResult(
            candidates=[
                filter_service_module.FilteredCandidate(
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
    return cast(filter_service_module.FilterResult, result)


def rank_results(
    service: SearchServiceLike,
    filter_result: filter_service_module.FilterResult,
    parsed_query: ParsedQuery,
    user_location: Optional[Tuple[float, float]],
    metrics: SearchMetrics,
) -> ranking_service_module.RankingResult:
    start = time.time()
    try:
        result = service.ranking_service.rank_candidates(
            filter_result.candidates,
            parsed_query,
            user_location=user_location,
        )
    except Exception as exc:
        logger.error("Ranking failed: %s", exc)
        result = ranking_service_module.RankingResult(
            results=[
                ranking_service_module.RankedResult(
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
    return cast(ranking_service_module.RankingResult, result)


def apply_budget_degradation(metrics: SearchMetrics, budget: RequestBudget) -> None:
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


__all__ = [
    "apply_budget_degradation",
    "build_post_openai_data",
    "filter_candidates",
    "load_instructor_cards",
    "persist_search_side_effects",
    "rank_results",
    "retrieve_candidates",
    "select_instructor_ids",
]
