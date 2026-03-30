"""Post-OpenAI DB burst orchestration helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Dict, List, Optional, Tuple, cast

from sqlalchemy.orm import Session

from app.repositories.filter_repository import FilterRepository
from app.repositories.ranking_repository import RankingRepository
from app.repositories.retriever_repository import RetrieverRepository
from app.repositories.taxonomy_filter_repository import TaxonomyFilterRepository
from app.repositories.unresolved_location_query_repository import (
    UnresolvedLocationQueryRepository,
)
from app.schemas.nl_search import NLSearchContentFilterDefinition
from app.services.search.nl_pipeline.models import (
    LocationLLMCache,
    PostOpenAIData,
    PreOpenAIData,
    UnresolvedLocationInfo,
)
from app.services.search.nl_pipeline.postflight_steps import (
    PostOpenAIState,
    execute_post_openai_steps,
)
from app.services.search.nl_pipeline.protocols import DBSessionFactory, LoggerLike

if TYPE_CHECKING:
    from app.repositories.search_batch_repository import SearchBatchRepository
    from app.services.search.filter_service import FilterService
    from app.services.search.location_resolver import LocationResolver, ResolvedLocation
    from app.services.search.query_parser import ParsedQuery
    from app.services.search.ranking_service import RankedResult, RankingResult, RankingService
    from app.services.search.retriever import PostgresRetriever, ServiceCandidate


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


def _build_post_openai_data(
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
    return _build_post_openai_data(
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
