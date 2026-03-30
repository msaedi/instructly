"""Taxonomy, filtering, and ranking helpers for the post-OpenAI DB burst."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Callable, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.repositories.filter_repository import FilterRepository
from app.repositories.ranking_repository import RankingRepository
from app.repositories.taxonomy_filter_repository import TaxonomyFilterRepository
from app.schemas.nl_search import NLSearchContentFilterDefinition
from app.services.search.filter_service import FilteredCandidate, FilterResult
from app.services.search.nl_pipeline.protocols import LoggerLike
from app.services.search.ranking_service import RankingResult
from app.services.search.retriever import ServiceCandidate

if TYPE_CHECKING:
    from app.services.search.filter_service import FilterService
    from app.services.search.location_resolver import LocationResolver, ResolvedLocation
    from app.services.search.query_parser import ParsedQuery
    from app.services.search.ranking_service import RankingService


TaxonomyPhaseResult = tuple[
    List[ServiceCandidate],
    Dict[str, List[str]],
    Dict[str, List[str]],
    Optional[str],
    Optional[str],
    List[NLSearchContentFilterDefinition],
]

FilterRankPhaseResult = tuple[FilterResult, RankingResult, int, int, bool, bool]


def resolve_taxonomy_and_filters(
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
    explicit_taxonomy_filters = normalize_taxonomy_filter_selections(taxonomy_filter_selections)
    explicit_subcategory_id = str(subcategory_id).strip() if subcategory_id else None
    effective_subcategory_id = resolve_effective_subcategory_id_fn(
        candidates, explicit_subcategory_id
    )
    taxonomy_repository = taxonomy_filter_repository_cls(db)
    inferred_filters: Dict[str, List[str]] = {}
    effective_subcategory_name: Optional[str] = None
    available_content_filters: List[NLSearchContentFilterDefinition] = []
    if effective_subcategory_id:
        (
            inferred_filters,
            effective_subcategory_name,
            available_content_filters,
        ) = _load_inferred_taxonomy_context(
            taxonomy_repository=taxonomy_repository,
            parsed_query=parsed_query,
            explicit_taxonomy_filters=explicit_taxonomy_filters,
            effective_subcategory_id=effective_subcategory_id,
            load_subcategory_filter_metadata_fn=load_subcategory_filter_metadata_fn,
            build_available_content_filters_fn=build_available_content_filters_fn,
            extract_inferred_filters=extract_inferred_filters,
            logger=logger,
        )
    filtered_candidates = _apply_taxonomy_hard_filters(
        taxonomy_repository=taxonomy_repository,
        candidates=candidates,
        explicit_subcategory_id=explicit_subcategory_id,
        explicit_taxonomy_filters=explicit_taxonomy_filters,
        logger=logger,
    )
    return (
        filtered_candidates,
        inferred_filters,
        explicit_taxonomy_filters,
        effective_subcategory_id,
        effective_subcategory_name,
        available_content_filters,
    )


def _load_inferred_taxonomy_context(
    *,
    taxonomy_repository: TaxonomyFilterRepository,
    parsed_query: ParsedQuery,
    explicit_taxonomy_filters: Dict[str, List[str]],
    effective_subcategory_id: str,
    load_subcategory_filter_metadata_fn: Callable[
        [TaxonomyFilterRepository, str], Tuple[List[Dict[str, object]], Optional[str]]
    ],
    build_available_content_filters_fn: Callable[
        [List[Dict[str, object]]], List[NLSearchContentFilterDefinition]
    ],
    extract_inferred_filters: Callable[..., Dict[str, List[str]]],
    logger: LoggerLike,
) -> tuple[Dict[str, List[str]], Optional[str], List[NLSearchContentFilterDefinition]]:
    try:
        subcategory_filters, effective_subcategory_name = load_subcategory_filter_metadata_fn(
            taxonomy_repository,
            effective_subcategory_id,
        )
        available_content_filters = build_available_content_filters_fn(subcategory_filters)
        inferred_filters = extract_inferred_filters(
            original_query=parsed_query.original_query,
            filter_definitions=subcategory_filters,
            existing_explicit_filters=explicit_taxonomy_filters,
            parser_skill_level=parsed_query.skill_level,
        )
        return inferred_filters, effective_subcategory_name, available_content_filters
    except Exception:
        logger.warning(
            "taxonomy_filter_load_failed",
            extra={"subcategory_id": effective_subcategory_id},
            exc_info=True,
        )
        return {}, None, []


def _apply_taxonomy_hard_filters(
    *,
    taxonomy_repository: TaxonomyFilterRepository,
    candidates: List[ServiceCandidate],
    explicit_subcategory_id: Optional[str],
    explicit_taxonomy_filters: Dict[str, List[str]],
    logger: LoggerLike,
) -> List[ServiceCandidate]:
    if not (explicit_taxonomy_filters or explicit_subcategory_id):
        return candidates
    try:
        candidate_service_ids = [candidate.service_id for candidate in candidates]
        matching_service_ids = taxonomy_repository.find_matching_service_ids(
            service_ids=candidate_service_ids,
            subcategory_id=explicit_subcategory_id,
            filter_selections=explicit_taxonomy_filters,
            active_only=True,
        )
        if not matching_service_ids:
            return []
        return [
            candidate for candidate in candidates if candidate.service_id in matching_service_ids
        ]
    except Exception as exc:
        logger.warning(
            "taxonomy_filter_service_ids_failed",
            extra={
                "subcategory_id": explicit_subcategory_id,
                "filter_count": len(explicit_taxonomy_filters) if explicit_taxonomy_filters else 0,
                "error": str(exc),
            },
            exc_info=True,
        )
        return candidates


def execute_filter_and_rank(
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
    filter_repo = filter_repository_cls(db)
    ranking_repo = ranking_repository_cls(db)
    resolver = location_resolver_cls(db, region_code=region_code)
    filter_start = time.perf_counter()
    filter_service = filter_service_cls(
        repository=filter_repo,
        location_resolver=resolver,
        region_code=region_code,
    )
    filter_failed = False
    try:
        filter_result = filter_service.filter_candidates_sync(
            candidates,
            parsed_query,
            user_location=user_location,
            location_resolution=location_resolution,
            requester_timezone=requester_timezone,
        )
    except Exception as exc:
        logger.error("Filtering failed: %s", exc)
        filter_failed = True
        filter_result = _build_filter_fallback(candidates, location_resolution)
    _append_taxonomy_filter_labels(
        filter_result=filter_result,
        effective_taxonomy_filters=effective_taxonomy_filters,
        effective_subcategory_id=effective_subcategory_id,
    )
    filter_latency_ms = int((time.perf_counter() - filter_start) * 1000)
    ranking_result, rank_latency_ms, ranking_failed = _rank_filtered_candidates(
        ranking_service_cls=ranking_service_cls,
        ranking_repo=ranking_repo,
        filter_result=filter_result,
        parsed_query=parsed_query,
        user_location=user_location,
        logger=logger,
    )
    return (
        filter_result,
        ranking_result,
        filter_latency_ms,
        rank_latency_ms,
        filter_failed,
        ranking_failed,
    )


def _build_filter_fallback(
    candidates: List[ServiceCandidate],
    location_resolution: Optional[ResolvedLocation],
) -> FilterResult:
    return FilterResult(
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
            for candidate in candidates
        ],
        total_before_filter=len(candidates),
        total_after_filter=len(candidates),
        filters_applied=[],
        soft_filtering_used=False,
        location_resolution=location_resolution,
    )


def _append_taxonomy_filter_labels(
    *,
    filter_result: FilterResult,
    effective_taxonomy_filters: Dict[str, List[str]],
    effective_subcategory_id: Optional[str],
) -> None:
    if not (effective_taxonomy_filters or effective_subcategory_id):
        return
    taxonomy_filters_applied = list(filter_result.filters_applied)
    if effective_subcategory_id:
        taxonomy_filters_applied.append("subcategory")
    for key in sorted(effective_taxonomy_filters.keys()):
        taxonomy_filters_applied.append(f"taxonomy:{key}")
    filter_result.filters_applied = list(dict.fromkeys(taxonomy_filters_applied))


def _rank_filtered_candidates(
    *,
    ranking_service_cls: type[RankingService],
    ranking_repo: RankingRepository,
    filter_result: FilterResult,
    parsed_query: ParsedQuery,
    user_location: Optional[Tuple[float, float]],
    logger: LoggerLike,
) -> tuple[RankingResult, int, bool]:
    rank_start = time.perf_counter()
    ranking_service = ranking_service_cls(repository=ranking_repo)
    try:
        ranking_result = ranking_service.rank_candidates(
            filter_result.candidates,
            parsed_query,
            user_location=user_location,
        )
        return ranking_result, int((time.perf_counter() - rank_start) * 1000), False
    except Exception as exc:
        logger.error("Ranking failed: %s", exc)
        return (
            RankingResult(results=[], total_results=0),
            int((time.perf_counter() - rank_start) * 1000),
            True,
        )
