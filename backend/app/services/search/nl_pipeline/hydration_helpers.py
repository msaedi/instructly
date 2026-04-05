"""Hydration helpers shared by NL search result assembly."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import TYPE_CHECKING, Dict, List, Optional, Sequence, TypedDict, cast

from app.core.config import settings
from app.schemas.nl_search import (
    InstructorSummary,
    InstructorTeachingLocationSummary,
    NLSearchResultItem,
    RatingSummary,
    ServiceMatch,
)
from app.services.search.location_resolver import LocationResolver
from app.services.search.nl_pipeline.protocols import AsyncioLike, DBSessionFactory

if TYPE_CHECKING:
    from app.repositories.filter_repository import FilterRepository
    from app.repositories.retriever_repository import RetrieverRepository
    from app.repositories.service_format_pricing_repository import ServiceFormatPricingRepository
    from app.services.search.location_resolver import ResolvedLocation
    from app.services.search.query_parser import ParsedQuery
    from app.services.search.ranking_service import RankedResult

logger = logging.getLogger(__name__)


class SerializedFormatPrice(TypedDict):
    format: str
    hourly_rate: float


class InstructorProfileRow(TypedDict):
    instructor_id: str
    first_name: str
    last_initial: Optional[str]
    avg_rating: Optional[float]
    review_count: int
    profile_picture_key: Optional[str]
    bio_snippet: Optional[str]
    verified: bool
    is_founding_instructor: bool
    years_experience: Optional[int]
    teaching_locations: List[InstructorTeachingLocationSummary]
    coverage_areas: List[str]


class RawMatchingService(TypedDict, total=False):
    service_id: str
    service_catalog_id: str
    name: str
    description: Optional[str]
    min_hourly_rate: float
    relevance_score: float


class RawInstructorResultRow(InstructorProfileRow, total=False):
    matching_services: List[RawMatchingService]


@dataclass(slots=True)
class HydrationGrouping:
    ordered_instructor_ids: List[str]
    by_instructor: Dict[str, List[RankedResult]]
    chosen_by_instructor: Dict[str, List[RankedResult]]
    service_ids: List[str]


def serialize_format_prices(price_rows: Sequence[object]) -> List[SerializedFormatPrice]:
    """Serialize pricing rows for NL search responses."""
    return [
        {
            "format": str(getattr(row, "format", "")),
            "hourly_rate": float(getattr(row, "hourly_rate", 0)),
        }
        for row in price_rows
        if getattr(row, "format", None) is not None
    ]


def derive_service_offers(format_prices: List[SerializedFormatPrice]) -> Dict[str, bool]:
    """Derive lesson-format booleans from serialized format prices."""
    enabled_formats = {
        str(price_row.get("format"))
        for price_row in format_prices
        if isinstance(price_row, dict) and price_row.get("format")
    }
    return {
        "offers_travel": "student_location" in enabled_formats,
        "offers_at_location": "instructor_location" in enabled_formats,
        "offers_online": "online" in enabled_formats,
    }


def build_photo_url(key: Optional[str], *, assets_domain: Optional[str] = None) -> Optional[str]:
    """Build Cloudflare R2 URL for profile photo."""
    if not key:
        return None
    domain = assets_domain or getattr(settings, "r2_public_url", "https://assets.instainstru.com")
    return f"{domain}/{key}"


def group_results_by_instructor(ranked: List[RankedResult], limit: int) -> HydrationGrouping:
    ordered_instructor_ids: List[str] = []
    seen_instructors: set[str] = set()
    for result in ranked:
        if result.instructor_id in seen_instructors:
            continue
        seen_instructors.add(result.instructor_id)
        ordered_instructor_ids.append(result.instructor_id)
        if len(ordered_instructor_ids) >= limit:
            break
    selected_instructors = set(ordered_instructor_ids)
    by_instructor: Dict[str, List[RankedResult]] = {iid: [] for iid in ordered_instructor_ids}
    for result in ranked:
        if result.instructor_id in selected_instructors:
            by_instructor[result.instructor_id].append(result)
    chosen_by_instructor: Dict[str, List[RankedResult]] = {}
    for instructor_id in ordered_instructor_ids:
        services = sorted(
            by_instructor[instructor_id], key=lambda item: item.relevance_score, reverse=True
        )
        chosen = services[:4]
        if chosen:
            chosen_by_instructor[instructor_id] = chosen
    service_ids = [
        match.service_id
        for matches in chosen_by_instructor.values()
        for match in matches
        if match.service_id
    ]
    return HydrationGrouping(
        ordered_instructor_ids=ordered_instructor_ids,
        by_instructor=by_instructor,
        chosen_by_instructor=chosen_by_instructor,
        service_ids=list(dict.fromkeys(service_ids)),
    )


async def load_service_format_prices(
    *,
    service_ids: List[str],
    asyncio_module: AsyncioLike,
    get_db_session: DBSessionFactory,
    pricing_repository_cls: type[ServiceFormatPricingRepository],
) -> Dict[str, List[SerializedFormatPrice]]:
    if not service_ids:
        return {}

    def _load_service_format_prices() -> Dict[str, List[SerializedFormatPrice]]:
        try:
            with get_db_session() as db:
                pricing_repo = pricing_repository_cls(db)
                grouped = pricing_repo.get_prices_for_services(service_ids)
                return {
                    service_id: serialize_format_prices(price_rows)
                    for service_id, price_rows in grouped.items()
                }
        except Exception:
            logger.warning(
                "Failed to load async NL hydration service format prices",
                extra={"service_count": len(service_ids)},
                exc_info=True,
            )
            return {}

    return cast(
        Dict[str, List[SerializedFormatPrice]],
        await asyncio_module.to_thread(_load_service_format_prices),
    )


async def load_hydration_data(
    *,
    grouping: HydrationGrouping,
    location_resolution: Optional[ResolvedLocation],
    instructor_rows: Optional[List[InstructorProfileRow]],
    distance_meters: Optional[Dict[str, float]],
    asyncio_module: AsyncioLike,
    get_db_session: DBSessionFactory,
    retriever_repository_cls: type[RetrieverRepository],
    filter_repository_cls: type[FilterRepository],
) -> tuple[List[InstructorProfileRow], Dict[str, float]]:
    if instructor_rows is not None:
        return instructor_rows, distance_meters or {}
    distance_region_ids = LocationResolver.effective_region_ids(location_resolution) or None

    def _load_hydration_data() -> tuple[List[InstructorProfileRow], Dict[str, float]]:
        with get_db_session() as db:
            retriever_repo = retriever_repository_cls(db)
            rows = cast(
                List[InstructorProfileRow],
                retriever_repo.get_instructor_cards(grouping.ordered_instructor_ids),
            )
            distance_map: Dict[str, float] = {}
            if distance_region_ids:
                filter_repo = filter_repository_cls(db)
                distance_map = filter_repo.get_instructor_min_distance_to_regions(
                    grouping.ordered_instructor_ids,
                    distance_region_ids,
                )
            return rows, distance_map

    return cast(
        tuple[List[InstructorProfileRow], Dict[str, float]],
        await asyncio_module.to_thread(_load_hydration_data),
    )


def build_service_match(
    *,
    service_id: str,
    service_catalog_id: str,
    name: str,
    description: Optional[str],
    min_hourly_rate: float,
    relevance_score: float,
    effective_hourly_rate: Optional[float],
    format_prices: List[SerializedFormatPrice],
) -> ServiceMatch:
    offers = derive_service_offers(format_prices)
    extra = {}
    if effective_hourly_rate is not None and effective_hourly_rate != min_hourly_rate:
        extra["effective_hourly_rate"] = effective_hourly_rate
    return ServiceMatch(
        service_id=service_id,
        service_catalog_id=service_catalog_id,
        name=name,
        description=description,
        min_hourly_rate=min_hourly_rate,
        format_prices=format_prices,
        relevance_score=round(float(relevance_score), 3),
        offers_travel=offers["offers_travel"],
        offers_at_location=offers["offers_at_location"],
        offers_online=offers["offers_online"],
        **extra,
    )


def build_instructor_dto(
    *,
    instructor_id: str,
    chosen_for_instructor: List[RankedResult],
    all_matches: List[RankedResult],
    profile: InstructorProfileRow,
    format_prices_by_service: Dict[str, List[SerializedFormatPrice]],
    distance_meters: Dict[str, float],
) -> NLSearchResultItem:
    avg_rating = profile.get("avg_rating")
    instructor = InstructorSummary(
        id=instructor_id,
        first_name=profile["first_name"],
        last_initial=profile.get("last_initial") or "",
        profile_picture_url=build_photo_url(profile.get("profile_picture_key")),
        bio_snippet=profile.get("bio_snippet"),
        verified=bool(profile.get("verified", False)),
        is_founding_instructor=bool(profile.get("is_founding_instructor", False)),
        years_experience=profile.get("years_experience"),
        teaching_locations=profile.get("teaching_locations", []) or [],
    )
    rating_summary = RatingSummary(
        average=round(float(avg_rating), 2) if isinstance(avg_rating, (int, float)) else None,
        count=int(profile.get("review_count", 0) or 0),
    )
    best_ranked = chosen_for_instructor[0]
    best_match = build_service_match(
        service_id=best_ranked.service_id,
        service_catalog_id=best_ranked.service_catalog_id,
        name=best_ranked.name,
        description=best_ranked.description,
        min_hourly_rate=best_ranked.min_hourly_rate,
        relevance_score=best_ranked.relevance_score,
        effective_hourly_rate=best_ranked.effective_hourly_rate,
        format_prices=format_prices_by_service.get(best_ranked.service_id, []),
    )
    other_matches = [
        build_service_match(
            service_id=match.service_id,
            service_catalog_id=match.service_catalog_id,
            name=match.name,
            description=match.description,
            min_hourly_rate=match.min_hourly_rate,
            relevance_score=match.relevance_score,
            effective_hourly_rate=match.effective_hourly_rate,
            format_prices=format_prices_by_service.get(match.service_id, []),
        )
        for match in chosen_for_instructor[1:]
    ]
    meters = distance_meters.get(instructor_id)
    return NLSearchResultItem(
        instructor_id=instructor_id,
        instructor=instructor,
        rating=rating_summary,
        coverage_areas=profile.get("coverage_areas", []) or [],
        best_match=best_match,
        other_matches=other_matches,
        total_matching_services=len(all_matches) or 1,
        relevance_score=best_match.relevance_score,
        distance_km=round(float(meters) / 1000.0, 1) if meters is not None else None,
        distance_mi=round(float(meters) / 1609.34, 1) if meters is not None else None,
    )


def load_service_format_prices_sync(
    *,
    service_ids: List[str],
    get_db_session: DBSessionFactory,
    pricing_repository_cls: type[ServiceFormatPricingRepository],
) -> Dict[str, List[SerializedFormatPrice]]:
    if not service_ids:
        return {}
    try:
        with get_db_session() as db:
            pricing_repo = pricing_repository_cls(db)
            grouped = pricing_repo.get_prices_for_services(service_ids)
            return {
                service_id: serialize_format_prices(price_rows)
                for service_id, price_rows in grouped.items()
            }
    except Exception:
        logger.warning(
            "Failed to load sync NL hydration service format prices",
            extra={"service_count": len(service_ids)},
            exc_info=True,
        )
        return {}


def build_transformed_result_row(
    *,
    row: RawInstructorResultRow,
    parsed_query: ParsedQuery,
    format_prices_by_service: Dict[str, List[SerializedFormatPrice]],
) -> Optional[NLSearchResultItem]:
    services = list(row.get("matching_services") or [])
    if not services:
        return None
    if parsed_query.max_price:
        services = [
            service
            for service in services
            if float(service.get("min_hourly_rate", 0)) <= parsed_query.max_price
        ]
        if not services:
            return None
    best = services[0]
    best_match = build_service_match(
        service_id=best["service_id"],
        service_catalog_id=best["service_catalog_id"],
        name=best["name"],
        description=best.get("description"),
        min_hourly_rate=float(best.get("min_hourly_rate", 0)),
        relevance_score=float(best["relevance_score"]),
        effective_hourly_rate=None,
        format_prices=format_prices_by_service.get(str(best["service_id"]), []),
    )
    other_matches = [
        build_service_match(
            service_id=service["service_id"],
            service_catalog_id=service["service_catalog_id"],
            name=service["name"],
            description=service.get("description"),
            min_hourly_rate=float(service.get("min_hourly_rate", 0)),
            relevance_score=float(service["relevance_score"]),
            effective_hourly_rate=None,
            format_prices=format_prices_by_service.get(str(service["service_id"]), []),
        )
        for service in services[1:4]
    ]
    instructor = InstructorSummary(
        id=row["instructor_id"],
        first_name=row["first_name"],
        last_initial=row["last_initial"] or "",
        profile_picture_url=build_photo_url(row.get("profile_picture_key")),
        bio_snippet=row.get("bio_snippet"),
        verified=bool(row.get("verified", False)),
        is_founding_instructor=bool(row.get("is_founding_instructor", False)),
        years_experience=row.get("years_experience"),
        teaching_locations=row.get("teaching_locations", []) or [],
    )
    avg_rating = row.get("avg_rating")
    rating = RatingSummary(
        average=round(float(avg_rating), 2) if isinstance(avg_rating, (int, float)) else None,
        count=int(row.get("review_count", 0) or 0),
    )
    return NLSearchResultItem(
        instructor_id=row["instructor_id"],
        instructor=instructor,
        rating=rating,
        coverage_areas=row.get("coverage_areas", []),
        best_match=best_match,
        other_matches=other_matches,
        total_matching_services=len(services),
        relevance_score=best_match.relevance_score,
    )


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
    "load_hydration_data",
    "load_service_format_prices",
    "load_service_format_prices_sync",
    "serialize_format_prices",
]
