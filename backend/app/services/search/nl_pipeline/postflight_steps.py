"""Internal step helpers for the post-OpenAI DB burst."""

from __future__ import annotations

from dataclasses import dataclass
import time
from typing import TYPE_CHECKING, Callable, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.schemas.nl_search import NLSearchContentFilterDefinition
from app.services.search import retriever as retriever_module
from app.services.search.filter_service import FilterResult
from app.services.search.nl_pipeline.models import (
    PostBurstCallbacks,
    PostBurstDeps,
    PostBurstInputs,
    PreOpenAIData,
)
from app.services.search.nl_pipeline.postflight_filters import (
    FilterRankPhaseResult,
    TaxonomyPhaseResult,
    execute_filter_and_rank,
    resolve_taxonomy_and_filters,
)
from app.services.search.nl_pipeline.protocols import LoggerLike
from app.services.search.ranking_service import RankingResult
from app.services.search.retriever import ServiceCandidate

if TYPE_CHECKING:
    from app.repositories.filter_repository import FilterRepository
    from app.repositories.ranking_repository import RankingRepository
    from app.repositories.search_batch_repository import SearchBatchRepository
    from app.repositories.taxonomy_filter_repository import TaxonomyFilterRepository
    from app.services.search.filter_service import FilterService
    from app.services.search.location_resolver import LocationResolver, ResolvedLocation
    from app.services.search.query_parser import ParsedQuery
    from app.services.search.ranking_service import RankingService
    from app.services.search.retriever import PostgresRetriever


@dataclass(slots=True)
class PostOpenAIState:
    filter_result: FilterResult
    ranking_result: RankingResult
    retrieval_candidates: List[ServiceCandidate]
    text_latency_ms: int
    vector_latency_ms: int
    filter_latency_ms: int
    rank_latency_ms: int
    vector_search_used: bool
    skip_vector: bool
    filter_failed: bool
    ranking_failed: bool
    inferred_filters: Dict[str, List[str]]
    effective_taxonomy_filters: Dict[str, List[str]]
    effective_subcategory_id: Optional[str]
    effective_subcategory_name: Optional[str]
    available_content_filters: List[NLSearchContentFilterDefinition]


RetrievalPhaseResult = tuple[List[ServiceCandidate], int, int, bool, bool]


def execute_retrieval_and_fusion(
    *,
    batch: SearchBatchRepository,
    pre_data: PreOpenAIData,
    parsed_query: ParsedQuery,
    query_embedding: Optional[List[float]],
    retriever: PostgresRetriever,
    compute_text_match_flags: Callable[
        [str, Dict[str, Tuple[float, Dict[str, object]]]], tuple[float, bool, bool]
    ],
    text_top_k: int,
    vector_top_k: int,
    max_candidates: int,
) -> tuple[List[ServiceCandidate], int, int, bool, bool]:
    text_results = pre_data.text_results
    text_latency_ms = pre_data.text_latency_ms
    require_text_match = pre_data.require_text_match
    skip_vector = pre_data.skip_vector
    if text_results is None:
        text_query = retriever_module.normalize_query_for_trigram(parsed_query.service_query)
        text_start = time.perf_counter()
        text_results = batch.text_search(
            text_query, text_query, limit=min(text_top_k, max_candidates)
        )
        text_latency_ms = int((time.perf_counter() - text_start) * 1000)
        _, require_text_match, skip_vector = compute_text_match_flags(
            parsed_query.service_query,
            text_results,
        )
    vector_results: Dict[str, Tuple[float, Dict[str, object]]] = {}
    vector_latency_ms = 0
    vector_search_used = False
    if query_embedding and not skip_vector:
        vector_start = time.perf_counter()
        vector_results = batch.vector_search(
            query_embedding, limit=min(vector_top_k, max_candidates)
        )
        vector_latency_ms = int((time.perf_counter() - vector_start) * 1000)
        vector_search_used = True
    candidates = retriever.fuse_results(
        vector_results,
        text_results or {},
        max_candidates,
        require_text_match=require_text_match,
    )
    return candidates, text_latency_ms, vector_latency_ms, vector_search_used, skip_vector


def execute_post_openai_steps(
    *,
    db: Session,
    inputs: PostBurstInputs,
    deps: PostBurstDeps,
    callbacks: PostBurstCallbacks,
) -> PostOpenAIState:
    retrieval_result = _execute_retrieval_phase(
        db=db,
        search_batch_repository_cls=deps.search_batch_repository_cls,
        pre_data=inputs.pre_data,
        parsed_query=inputs.parsed_query,
        query_embedding=inputs.query_embedding,
        retriever=deps.retriever,
        compute_text_match_flags=callbacks.compute_text_match_flags,
        region_code=deps.region_code,
        text_top_k=deps.text_top_k,
        vector_top_k=deps.vector_top_k,
        max_candidates=deps.max_candidates,
    )
    taxonomy_result = _execute_taxonomy_phase(
        db=db,
        candidates=retrieval_result[0],
        parsed_query=inputs.parsed_query,
        taxonomy_filter_selections=inputs.taxonomy_filter_selections,
        subcategory_id=inputs.subcategory_id,
        normalize_taxonomy_filter_selections=callbacks.normalize_taxonomy_filter_selections,
        resolve_effective_subcategory_id_fn=callbacks.resolve_effective_subcategory_id_fn,
        taxonomy_filter_repository_cls=deps.taxonomy_filter_repository_cls,
        load_subcategory_filter_metadata_fn=callbacks.load_subcategory_filter_metadata_fn,
        build_available_content_filters_fn=callbacks.build_available_content_filters_fn,
        extract_inferred_filters=callbacks.extract_inferred_filters,
        logger=deps.logger,
    )
    filter_rank_result = _execute_filter_rank_phase(
        db=db,
        candidates=taxonomy_result[0],
        parsed_query=inputs.parsed_query,
        user_location=inputs.user_location,
        location_resolution=inputs.location_resolution,
        requester_timezone=inputs.requester_timezone,
        filter_repository_cls=deps.filter_repository_cls,
        ranking_repository_cls=deps.ranking_repository_cls,
        location_resolver_cls=deps.location_resolver_cls,
        filter_service_cls=deps.filter_service_cls,
        ranking_service_cls=deps.ranking_service_cls,
        region_code=deps.region_code,
        effective_taxonomy_filters=taxonomy_result[2],
        effective_subcategory_id=taxonomy_result[3],
        logger=deps.logger,
    )
    return _build_post_openai_state(
        retrieval_result=retrieval_result,
        taxonomy_result=taxonomy_result,
        filter_rank_result=filter_rank_result,
    )


def _execute_retrieval_phase(
    *,
    db: Session,
    search_batch_repository_cls: type[SearchBatchRepository],
    pre_data: PreOpenAIData,
    parsed_query: ParsedQuery,
    query_embedding: Optional[List[float]],
    retriever: PostgresRetriever,
    compute_text_match_flags: Callable[
        [str, Dict[str, Tuple[float, Dict[str, object]]]], tuple[float, bool, bool]
    ],
    region_code: str,
    text_top_k: int,
    vector_top_k: int,
    max_candidates: int,
) -> RetrievalPhaseResult:
    batch = search_batch_repository_cls(db, region_code=region_code)
    return execute_retrieval_and_fusion(
        batch=batch,
        pre_data=pre_data,
        parsed_query=parsed_query,
        query_embedding=query_embedding,
        retriever=retriever,
        compute_text_match_flags=compute_text_match_flags,
        text_top_k=text_top_k,
        vector_top_k=vector_top_k,
        max_candidates=max_candidates,
    )


def _execute_taxonomy_phase(
    *,
    db: Session,
    candidates: List[ServiceCandidate],
    parsed_query: ParsedQuery,
    taxonomy_filter_selections: Optional[Dict[str, List[str]]],
    subcategory_id: Optional[str],
    normalize_taxonomy_filter_selections: Callable[
        [Optional[Dict[str, List[str]]]], Dict[str, List[str]]
    ],
    resolve_effective_subcategory_id_fn: Callable[
        [List[ServiceCandidate], Optional[str]], Optional[str]
    ],
    taxonomy_filter_repository_cls: type[TaxonomyFilterRepository],
    load_subcategory_filter_metadata_fn: Callable[
        [TaxonomyFilterRepository, str], Tuple[List[Dict[str, object]], Optional[str]]
    ],
    build_available_content_filters_fn: Callable[
        [List[Dict[str, object]]], List[NLSearchContentFilterDefinition]
    ],
    extract_inferred_filters: Callable[..., Dict[str, List[str]]],
    logger: LoggerLike,
) -> TaxonomyPhaseResult:
    return resolve_taxonomy_and_filters(
        db=db,
        candidates=candidates,
        parsed_query=parsed_query,
        taxonomy_filter_selections=taxonomy_filter_selections,
        subcategory_id=subcategory_id,
        normalize_taxonomy_filter_selections=normalize_taxonomy_filter_selections,
        resolve_effective_subcategory_id_fn=resolve_effective_subcategory_id_fn,
        taxonomy_filter_repository_cls=taxonomy_filter_repository_cls,
        load_subcategory_filter_metadata_fn=load_subcategory_filter_metadata_fn,
        build_available_content_filters_fn=build_available_content_filters_fn,
        extract_inferred_filters=extract_inferred_filters,
        logger=logger,
    )


def _execute_filter_rank_phase(
    *,
    db: Session,
    candidates: List[ServiceCandidate],
    parsed_query: ParsedQuery,
    user_location: Optional[Tuple[float, float]],
    location_resolution: Optional[ResolvedLocation],
    requester_timezone: Optional[str],
    filter_repository_cls: type[FilterRepository],
    ranking_repository_cls: type[RankingRepository],
    location_resolver_cls: type[LocationResolver],
    filter_service_cls: type[FilterService],
    ranking_service_cls: type[RankingService],
    region_code: str,
    effective_taxonomy_filters: Dict[str, List[str]],
    effective_subcategory_id: Optional[str],
    logger: LoggerLike,
) -> FilterRankPhaseResult:
    return execute_filter_and_rank(
        db=db,
        candidates=candidates,
        parsed_query=parsed_query,
        user_location=user_location,
        location_resolution=location_resolution,
        requester_timezone=requester_timezone,
        filter_repository_cls=filter_repository_cls,
        ranking_repository_cls=ranking_repository_cls,
        location_resolver_cls=location_resolver_cls,
        filter_service_cls=filter_service_cls,
        ranking_service_cls=ranking_service_cls,
        region_code=region_code,
        effective_taxonomy_filters=effective_taxonomy_filters,
        effective_subcategory_id=effective_subcategory_id,
        logger=logger,
    )


def _build_post_openai_state(
    *,
    retrieval_result: RetrievalPhaseResult,
    taxonomy_result: TaxonomyPhaseResult,
    filter_rank_result: FilterRankPhaseResult,
) -> PostOpenAIState:
    (
        candidates,
        text_latency_ms,
        vector_latency_ms,
        vector_search_used,
        skip_vector,
    ) = retrieval_result
    (
        filtered_candidates,
        inferred_filters,
        effective_taxonomy_filters,
        effective_subcategory_id,
        effective_subcategory_name,
        available_content_filters,
    ) = taxonomy_result
    (
        filter_result,
        ranking_result,
        filter_latency_ms,
        rank_latency_ms,
        filter_failed,
        ranking_failed,
    ) = filter_rank_result
    return PostOpenAIState(
        filter_result=filter_result,
        ranking_result=ranking_result,
        retrieval_candidates=filtered_candidates,
        text_latency_ms=text_latency_ms,
        vector_latency_ms=vector_latency_ms,
        filter_latency_ms=filter_latency_ms,
        rank_latency_ms=rank_latency_ms,
        vector_search_used=vector_search_used,
        skip_vector=skip_vector,
        filter_failed=filter_failed,
        ranking_failed=ranking_failed,
        inferred_filters=inferred_filters,
        effective_taxonomy_filters=effective_taxonomy_filters,
        effective_subcategory_id=effective_subcategory_id,
        effective_subcategory_name=effective_subcategory_name,
        available_content_filters=available_content_filters,
    )
