"""Result hydration helpers for the NL search pipeline."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Dict, List, Optional, cast

from app import database as database_module
from app.repositories import (
    filter_repository as filter_repository_module,
    retriever_repository as retriever_repository_module,
    service_format_pricing_repository as pricing_repository_module,
)
from app.schemas.nl_search import NLSearchResultItem, StageStatus
from app.services.search.nl_pipeline.hydration_helpers import (
    HydrationGrouping,
    InstructorProfileRow,
    RawInstructorResultRow,
    SerializedFormatPrice,
    build_instructor_dto,
    build_photo_url,
    build_service_match,
    build_transformed_result_row,
    derive_service_offers,
    group_results_by_instructor,
    load_hydration_data,
    load_service_format_prices,
    load_service_format_prices_sync,
    serialize_format_prices,
)
from app.services.search.nl_pipeline.protocols import AsyncioLike, DBSessionFactory

if TYPE_CHECKING:
    from app.repositories.filter_repository import FilterRepository
    from app.repositories.retriever_repository import RetrieverRepository
    from app.repositories.service_format_pricing_repository import ServiceFormatPricingRepository
    from app.services.search.location_resolver import ResolvedLocation
    from app.services.search.nl_pipeline.models import PipelineTimer, PostOpenAIData, SearchMetrics
    from app.services.search.query_parser import ParsedQuery
    from app.services.search.ranking_service import RankedResult

logger = logging.getLogger(__name__)


async def hydrate_instructor_results(
    *,
    ranked: List[RankedResult],
    limit: int,
    location_resolution: Optional[ResolvedLocation] = None,
    instructor_rows: Optional[List[InstructorProfileRow]] = None,
    distance_meters: Optional[Dict[str, float]] = None,
    asyncio_module: AsyncioLike,
    get_db_session: DBSessionFactory,
    pricing_repository_cls: type[ServiceFormatPricingRepository],
    retriever_repository_cls: type[RetrieverRepository],
    filter_repository_cls: type[FilterRepository],
) -> List[NLSearchResultItem]:
    if not ranked:
        return []
    grouping = group_results_by_instructor(ranked, limit)
    format_prices_by_service = await load_service_format_prices(
        service_ids=grouping.service_ids,
        asyncio_module=asyncio_module,
        get_db_session=get_db_session,
        pricing_repository_cls=pricing_repository_cls,
    )
    instructor_rows, distance_meters = await load_hydration_data(
        grouping=grouping,
        location_resolution=location_resolution,
        instructor_rows=instructor_rows,
        distance_meters=distance_meters,
        asyncio_module=asyncio_module,
        get_db_session=get_db_session,
        retriever_repository_cls=retriever_repository_cls,
        filter_repository_cls=filter_repository_cls,
    )
    if instructor_rows is None:
        raise RuntimeError("Instructor hydration returned no rows")
    instructor_by_id = {row["instructor_id"]: row for row in instructor_rows}
    return [
        build_instructor_dto(
            instructor_id=instructor_id,
            chosen_for_instructor=chosen,
            all_matches=grouping.by_instructor.get(instructor_id, []),
            profile=instructor_by_id[instructor_id],
            format_prices_by_service=format_prices_by_service,
            distance_meters=distance_meters,
        )
        for instructor_id, chosen in grouping.chosen_by_instructor.items()
        if instructor_by_id.get(instructor_id)
    ]


def transform_instructor_results(
    *,
    raw_results: List[RawInstructorResultRow],
    parsed_query: ParsedQuery,
    get_db_session: DBSessionFactory,
    pricing_repository_cls: type[ServiceFormatPricingRepository],
) -> List[NLSearchResultItem]:
    service_ids = [
        str(service["service_id"])
        for row in raw_results
        for service in (row.get("matching_services") or [])
        if isinstance(service, dict) and service.get("service_id")
    ]
    format_prices_by_service = load_service_format_prices_sync(
        service_ids=list(dict.fromkeys(service_ids)),
        get_db_session=get_db_session,
        pricing_repository_cls=pricing_repository_cls,
    )
    results = [
        build_transformed_result_row(
            row=row,
            parsed_query=parsed_query,
            format_prices_by_service=format_prices_by_service,
        )
        for row in raw_results
    ]
    return [result for result in results if result is not None]


async def hydrate_instructor_results_for_service(
    service: object,
    ranked: List[RankedResult],
    limit: int,
    *,
    location_resolution: Optional[ResolvedLocation] = None,
    instructor_rows: Optional[List[InstructorProfileRow]] = None,
    distance_meters: Optional[Dict[str, float]] = None,
) -> List[NLSearchResultItem]:
    return await hydrate_instructor_results(
        ranked=ranked,
        limit=limit,
        location_resolution=location_resolution,
        instructor_rows=instructor_rows,
        distance_meters=distance_meters,
        asyncio_module=asyncio,
        get_db_session=database_module.get_db_session,
        pricing_repository_cls=pricing_repository_module.ServiceFormatPricingRepository,
        retriever_repository_cls=retriever_repository_module.RetrieverRepository,
        filter_repository_cls=filter_repository_module.FilterRepository,
    )


def transform_instructor_results_for_service(
    service: object,
    raw_results: List[RawInstructorResultRow],
    parsed_query: ParsedQuery,
) -> List[NLSearchResultItem]:
    return transform_instructor_results(
        raw_results=raw_results,
        parsed_query=parsed_query,
        get_db_session=database_module.get_db_session,
        pricing_repository_cls=pricing_repository_module.ServiceFormatPricingRepository,
    )


async def hydrate_results_for_service(
    service: object,
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
        results = await hydrate_instructor_results_for_service(
            service,
            post_data.ranking_result.results,
            limit=limit,
            location_resolution=post_data.filter_result.location_resolution,
            instructor_rows=cast(List[InstructorProfileRow], post_data.instructor_rows),
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


__all__ = [
    "HydrationGrouping",
    "InstructorProfileRow",
    "RawInstructorResultRow",
    "SerializedFormatPrice",
    "build_instructor_dto",
    "build_photo_url",
    "build_service_match",
    "build_transformed_result_row",
    "derive_service_offers",
    "group_results_by_instructor",
    "hydrate_instructor_results",
    "hydrate_instructor_results_for_service",
    "hydrate_results_for_service",
    "load_hydration_data",
    "load_service_format_prices",
    "load_service_format_prices_sync",
    "serialize_format_prices",
    "transform_instructor_results",
    "transform_instructor_results_for_service",
]
