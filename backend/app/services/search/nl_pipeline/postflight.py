"""Post-OpenAI DB burst orchestration helpers."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Callable, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app import database as database_module
from app.repositories import search_batch_repository as search_batch_repository_module
from app.repositories.filter_repository import FilterRepository
from app.repositories.ranking_repository import RankingRepository
from app.repositories.retriever_repository import RetrieverRepository
from app.repositories.taxonomy_filter_repository import TaxonomyFilterRepository
from app.repositories.unresolved_location_query_repository import (
    UnresolvedLocationQueryRepository,
)
from app.schemas.nl_search import NLSearchContentFilterDefinition
from app.services.search import (
    filter_service as filter_service_module,
    ranking_service as ranking_service_module,
    retriever as retriever_module,
)
from app.services.search.nl_pipeline import location_helpers, preflight, taxonomy
from app.services.search.nl_pipeline.models import (
    LocationLLMCache,
    PostOpenAIData,
    PreOpenAIData,
    UnresolvedLocationInfo,
)
from app.services.search.nl_pipeline.postflight_runtime import (
    apply_budget_degradation,
    build_post_openai_data,
    filter_candidates,
    load_instructor_cards,
    persist_search_side_effects,
    rank_results,
    retrieve_candidates,
    select_instructor_ids,
)
from app.services.search.nl_pipeline.postflight_steps import (
    PostOpenAIState,
    execute_post_openai_steps,
)
from app.services.search.nl_pipeline.protocols import (
    DBSessionFactory,
    LoggerLike,
    SearchServiceLike,
)
from app.services.search.taxonomy_filter_extractor import extract_inferred_filters

if TYPE_CHECKING:
    from app.repositories.search_batch_repository import SearchBatchRepository
    from app.services.search.filter_service import FilterService
    from app.services.search.location_resolver import LocationResolver, ResolvedLocation
    from app.services.search.nl_pipeline.models import PipelineTimer, SearchMetrics
    from app.services.search.query_parser import ParsedQuery
    from app.services.search.ranking_service import RankedResult, RankingService
    from app.services.search.request_budget import RequestBudget
    from app.services.search.retriever import PostgresRetriever, RetrievalResult, ServiceCandidate

logger = logging.getLogger(__name__)


def run_post_openai_burst(
    *,
    get_db_session: DBSessionFactory,
    search_batch_repository_cls: type[SearchBatchRepository],
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
    retriever: PostgresRetriever,
    compute_text_match_flags: Callable[
        [str, Dict[str, Tuple[float, Dict[str, object]]]], tuple[float, bool, bool]
    ],
    normalize_taxonomy_filter_selections: Callable[
        [Optional[Dict[str, List[str]]]], Dict[str, List[str]]
    ],
    resolve_effective_subcategory_id_fn: Callable[
        [List[ServiceCandidate], Optional[str]], Optional[str]
    ],
    load_subcategory_filter_metadata_fn: Callable[
        [TaxonomyFilterRepository, str], Tuple[List[Dict[str, object]], Optional[str]]
    ],
    build_available_content_filters_fn: Callable[
        [List[Dict[str, object]]], List[NLSearchContentFilterDefinition]
    ],
    select_instructor_ids_fn: Callable[[List[RankedResult], int], List[str]],
    distance_region_ids_fn: Callable[[Optional[ResolvedLocation]], Optional[List[str]]],
    filter_service_cls: type[FilterService],
    ranking_service_cls: type[RankingService],
    filter_repository_cls: type[FilterRepository],
    ranking_repository_cls: type[RankingRepository],
    retriever_repository_cls: type[RetrieverRepository],
    taxonomy_filter_repository_cls: type[TaxonomyFilterRepository],
    unresolved_location_query_repository_cls: type[UnresolvedLocationQueryRepository],
    location_resolver_cls: type[LocationResolver],
    extract_inferred_filters: Callable[..., Dict[str, List[str]]],
    region_code: str,
    text_top_k: int,
    vector_top_k: int,
    max_candidates: int,
    logger: LoggerLike,
) -> PostOpenAIData:
    with get_db_session() as db:
        state = _execute_post_openai_state(
            db=db,
            search_batch_repository_cls=search_batch_repository_cls,
            pre_data=pre_data,
            parsed_query=parsed_query,
            query_embedding=query_embedding,
            location_resolution=location_resolution,
            user_location=user_location,
            requester_timezone=requester_timezone,
            taxonomy_filter_selections=taxonomy_filter_selections,
            subcategory_id=subcategory_id,
            retriever=retriever,
            compute_text_match_flags=compute_text_match_flags,
            normalize_taxonomy_filter_selections=normalize_taxonomy_filter_selections,
            resolve_effective_subcategory_id_fn=resolve_effective_subcategory_id_fn,
            load_subcategory_filter_metadata_fn=load_subcategory_filter_metadata_fn,
            build_available_content_filters_fn=build_available_content_filters_fn,
            filter_service_cls=filter_service_cls,
            ranking_service_cls=ranking_service_cls,
            filter_repository_cls=filter_repository_cls,
            ranking_repository_cls=ranking_repository_cls,
            taxonomy_filter_repository_cls=taxonomy_filter_repository_cls,
            location_resolver_cls=location_resolver_cls,
            extract_inferred_filters=extract_inferred_filters,
            region_code=region_code,
            text_top_k=text_top_k,
            vector_top_k=vector_top_k,
            max_candidates=max_candidates,
            logger=logger,
        )
        instructor_rows, distance_meters = _load_post_openai_results(
            db=db,
            state=state,
            limit=limit,
            location_resolution=location_resolution,
            location_llm_cache=location_llm_cache,
            unresolved_info=unresolved_info,
            pre_data=pre_data,
            select_instructor_ids_fn=select_instructor_ids_fn,
            distance_region_ids_fn=distance_region_ids_fn,
            filter_repository_cls=filter_repository_cls,
            retriever_repository_cls=retriever_repository_cls,
            unresolved_location_query_repository_cls=unresolved_location_query_repository_cls,
            location_resolver_cls=location_resolver_cls,
            region_code=region_code,
        )
    return build_post_openai_data(
        state=state,
        instructor_rows=instructor_rows,
        distance_meters=distance_meters,
    )


def _execute_post_openai_state(
    *,
    db: Session,
    search_batch_repository_cls: type[SearchBatchRepository],
    pre_data: PreOpenAIData,
    parsed_query: ParsedQuery,
    query_embedding: Optional[List[float]],
    location_resolution: Optional[ResolvedLocation],
    user_location: Optional[Tuple[float, float]],
    requester_timezone: Optional[str],
    taxonomy_filter_selections: Optional[Dict[str, List[str]]],
    subcategory_id: Optional[str],
    retriever: PostgresRetriever,
    compute_text_match_flags: Callable[
        [str, Dict[str, Tuple[float, Dict[str, object]]]], tuple[float, bool, bool]
    ],
    normalize_taxonomy_filter_selections: Callable[
        [Optional[Dict[str, List[str]]]], Dict[str, List[str]]
    ],
    resolve_effective_subcategory_id_fn: Callable[
        [List[ServiceCandidate], Optional[str]], Optional[str]
    ],
    load_subcategory_filter_metadata_fn: Callable[
        [TaxonomyFilterRepository, str], Tuple[List[Dict[str, object]], Optional[str]]
    ],
    build_available_content_filters_fn: Callable[
        [List[Dict[str, object]]], List[NLSearchContentFilterDefinition]
    ],
    filter_service_cls: type[FilterService],
    ranking_service_cls: type[RankingService],
    filter_repository_cls: type[FilterRepository],
    ranking_repository_cls: type[RankingRepository],
    taxonomy_filter_repository_cls: type[TaxonomyFilterRepository],
    location_resolver_cls: type[LocationResolver],
    extract_inferred_filters: Callable[..., Dict[str, List[str]]],
    region_code: str,
    text_top_k: int,
    vector_top_k: int,
    max_candidates: int,
    logger: LoggerLike,
) -> PostOpenAIState:
    return execute_post_openai_steps(
        db=db,
        search_batch_repository_cls=search_batch_repository_cls,
        pre_data=pre_data,
        parsed_query=parsed_query,
        query_embedding=query_embedding,
        location_resolution=location_resolution,
        user_location=user_location,
        requester_timezone=requester_timezone,
        taxonomy_filter_selections=taxonomy_filter_selections,
        subcategory_id=subcategory_id,
        retriever=retriever,
        compute_text_match_flags=compute_text_match_flags,
        normalize_taxonomy_filter_selections=normalize_taxonomy_filter_selections,
        resolve_effective_subcategory_id_fn=resolve_effective_subcategory_id_fn,
        load_subcategory_filter_metadata_fn=load_subcategory_filter_metadata_fn,
        build_available_content_filters_fn=build_available_content_filters_fn,
        filter_service_cls=filter_service_cls,
        ranking_service_cls=ranking_service_cls,
        filter_repository_cls=filter_repository_cls,
        ranking_repository_cls=ranking_repository_cls,
        taxonomy_filter_repository_cls=taxonomy_filter_repository_cls,
        location_resolver_cls=location_resolver_cls,
        extract_inferred_filters=extract_inferred_filters,
        region_code=region_code,
        text_top_k=text_top_k,
        vector_top_k=vector_top_k,
        max_candidates=max_candidates,
        logger=logger,
    )


def _load_post_openai_results(
    *,
    db: Session,
    state: PostOpenAIState,
    limit: int,
    location_resolution: Optional[ResolvedLocation],
    location_llm_cache: Optional[LocationLLMCache],
    unresolved_info: Optional[UnresolvedLocationInfo],
    pre_data: PreOpenAIData,
    select_instructor_ids_fn: Callable[[List[RankedResult], int], List[str]],
    distance_region_ids_fn: Callable[[Optional[ResolvedLocation]], Optional[List[str]]],
    filter_repository_cls: type[FilterRepository],
    retriever_repository_cls: type[RetrieverRepository],
    unresolved_location_query_repository_cls: type[UnresolvedLocationQueryRepository],
    location_resolver_cls: type[LocationResolver],
    region_code: str,
) -> tuple[List[Dict[str, object]], Dict[str, float]]:
    retriever_repository = retriever_repository_cls(db)
    filter_repository = filter_repository_cls(db)
    location_resolver = location_resolver_cls(db, region_code=region_code)
    instructor_rows, distance_meters = load_instructor_cards(
        retriever_repository=retriever_repository,
        filter_repository=filter_repository,
        ranking_result=state.ranking_result,
        limit=limit,
        location_resolution=location_resolution,
        select_instructor_ids_fn=select_instructor_ids_fn,
        distance_region_ids_fn=distance_region_ids_fn,
    )
    persist_search_side_effects(
        db=db,
        pre_data=pre_data,
        location_llm_cache=location_llm_cache,
        unresolved_info=unresolved_info,
        location_resolver=location_resolver,
        unresolved_location_query_repository_cls=unresolved_location_query_repository_cls,
    )
    return instructor_rows, distance_meters


def run_post_openai_burst_for_service(
    service: SearchServiceLike,
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
    from app.repositories.filter_repository import FilterRepository as FilterRepositoryCls
    from app.repositories.ranking_repository import RankingRepository as RankingRepositoryCls
    from app.repositories.retriever_repository import RetrieverRepository as RetrieverRepositoryCls
    from app.repositories.taxonomy_filter_repository import (
        TaxonomyFilterRepository as TaxonomyFilterRepositoryCls,
    )
    from app.repositories.unresolved_location_query_repository import (
        UnresolvedLocationQueryRepository as UnresolvedLocationQueryRepositoryCls,
    )
    from app.services.search.location_resolver import LocationResolver

    return run_post_openai_burst(
        get_db_session=database_module.get_db_session,
        search_batch_repository_cls=search_batch_repository_module.SearchBatchRepository,
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
        retriever=service.retriever,
        compute_text_match_flags=preflight.compute_text_match_flags,
        normalize_taxonomy_filter_selections=preflight.normalize_taxonomy_filter_selections,
        resolve_effective_subcategory_id_fn=taxonomy.resolve_effective_subcategory_id,
        load_subcategory_filter_metadata_fn=taxonomy.load_subcategory_filter_metadata,
        build_available_content_filters_fn=taxonomy.build_available_content_filters,
        select_instructor_ids_fn=select_instructor_ids,
        distance_region_ids_fn=location_helpers.distance_region_ids,
        filter_service_cls=filter_service_module.FilterService,
        ranking_service_cls=ranking_service_module.RankingService,
        filter_repository_cls=FilterRepositoryCls,
        ranking_repository_cls=RankingRepositoryCls,
        retriever_repository_cls=RetrieverRepositoryCls,
        taxonomy_filter_repository_cls=TaxonomyFilterRepositoryCls,
        unresolved_location_query_repository_cls=UnresolvedLocationQueryRepositoryCls,
        location_resolver_cls=LocationResolver,
        extract_inferred_filters=extract_inferred_filters,
        region_code=service._region_code,
        text_top_k=retriever_module.TEXT_TOP_K,
        vector_top_k=retriever_module.VECTOR_TOP_K,
        max_candidates=retriever_module.MAX_CANDIDATES,
        logger=logger,
    )


async def run_postflight_stage_for_service(
    service: SearchServiceLike,
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
        run_post_openai_burst_for_service,
        service,
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
            "success",
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
    apply_budget_degradation(metrics, budget)
    metrics.retrieve_latency_ms = post_data.text_latency_ms + post_data.vector_latency_ms
    retrieval_result = retriever_module.RetrievalResult(
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


__all__ = [
    "filter_candidates",
    "load_instructor_cards",
    "persist_search_side_effects",
    "rank_results",
    "retrieve_candidates",
    "run_post_openai_burst",
    "run_post_openai_burst_for_service",
    "run_postflight_stage_for_service",
    "select_instructor_ids",
]
