# backend/app/services/search/filter_service.py
"""
Constraint filtering service for NL search.
Applies price, location, and availability filters to candidates.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date, time
import logging
import os
import time as time_module
from typing import TYPE_CHECKING, Dict, List, Optional, cast

from app.database import get_db_session
from app.repositories.filter_repository import FilterRepository
from app.services.config_service import ConfigService
from app.services.search.location_resolver import LocationResolver, ResolvedLocation
from app.services.search.retriever import ServiceCandidate
from app.utils.bitset import windows_from_bits
from app.utils.time_helpers import string_to_time

if TYPE_CHECKING:
    from app.services.search.query_parser import ParsedQuery

logger = logging.getLogger(__name__)

# Optional perf logging for profiling in staging/dev.
# NOTE: Read at module load time — changes require process restart.
_PERF_LOG_ENABLED = os.getenv("NL_SEARCH_PERF_LOG") == "1"
_PERF_LOG_SLOW_MS = int(os.getenv("NL_SEARCH_PERF_LOG_SLOW_MS", "0"))

# Configuration
MIN_RESULTS_BEFORE_SOFT_FILTER = 5
SOFT_PRICE_MULTIPLIER = 1.25  # Allow 25% over budget
SOFT_DISTANCE_METERS = 10000  # 10km for soft location filter


@dataclass(init=False)
class FilteredCandidate:
    """A candidate that passed filtering."""

    service_id: str
    service_catalog_id: str
    instructor_id: str
    hybrid_score: float

    name: str
    description: Optional[str]
    min_hourly_rate: float
    lesson_type_hourly_rate: Optional[float]

    passed_price: bool = True
    passed_location: bool = True
    passed_availability: bool = True

    soft_filtered: bool = False
    soft_filter_reasons: List[str] = field(default_factory=list)

    available_dates: List[date] = field(default_factory=list)
    earliest_available: Optional[date] = None

    def __init__(
        self,
        *,
        service_id: str,
        service_catalog_id: str,
        instructor_id: str,
        hybrid_score: float,
        name: str,
        description: Optional[str],
        min_hourly_rate: Optional[float] = None,
        price_per_hour: Optional[float] = None,
        lesson_type_hourly_rate: Optional[float] = None,
        passed_price: bool = True,
        passed_location: bool = True,
        passed_availability: bool = True,
        soft_filtered: bool = False,
        soft_filter_reasons: Optional[List[str]] = None,
        available_dates: Optional[List[date]] = None,
        earliest_available: Optional[date] = None,
    ) -> None:
        rate = min_hourly_rate if min_hourly_rate is not None else price_per_hour
        if rate is None:
            raise ValueError("min_hourly_rate is required")

        self.service_id = service_id
        self.service_catalog_id = service_catalog_id
        self.instructor_id = instructor_id
        self.hybrid_score = hybrid_score
        self.name = name
        self.description = description
        self.min_hourly_rate = float(rate)
        self.lesson_type_hourly_rate = (
            float(lesson_type_hourly_rate) if lesson_type_hourly_rate is not None else None
        )
        self.passed_price = passed_price
        self.passed_location = passed_location
        self.passed_availability = passed_availability
        self.soft_filtered = soft_filtered
        self.soft_filter_reasons = list(soft_filter_reasons or [])
        self.available_dates = list(available_dates or [])
        self.earliest_available = earliest_available

    @property
    def price_per_hour(self) -> float:
        """Legacy alias for tests and callers still reading price_per_hour."""
        return float(self.min_hourly_rate)

    @property
    def effective_hourly_rate(self) -> float:
        """Return the lesson-type-specific rate when available, else the global minimum."""
        if self.lesson_type_hourly_rate is not None:
            return float(self.lesson_type_hourly_rate)
        return float(self.min_hourly_rate)


@dataclass
class FilterResult:
    """Result of constraint filtering."""

    candidates: List[FilteredCandidate]
    total_before_filter: int
    total_after_filter: int
    filters_applied: List[str] = field(default_factory=list)
    soft_filtering_used: bool = False
    relaxed_constraints: List[str] = field(default_factory=list)
    location_resolution: Optional[ResolvedLocation] = None
    filter_stats: Dict[str, int] = field(default_factory=dict)


class FilterService:
    """
    Service for applying constraint filters to search candidates.

    Filter Order (most selective first):
    1. Price - removes candidates over budget
    2. Location - PostGIS containment check
    3. Availability - bitmap validation

    Soft Filtering:
    If < 5 results after hard filters, progressively relax constraints in this order:
    1) time -> 2) date -> 3) location -> 4) price
    """

    def __init__(
        self,
        repository: Optional[FilterRepository] = None,
        location_resolver: Optional[LocationResolver] = None,
        region_code: str = "nyc",
    ) -> None:
        self._region_code = region_code
        self._repository_override = repository
        self._location_resolver_override = location_resolver

        # These are initialized per-call in the worker thread (or injected for unit tests).
        self.repository: FilterRepository = repository or cast(FilterRepository, None)
        self.location_resolver: LocationResolver = location_resolver or cast(LocationResolver, None)

    async def filter_candidates(
        self,
        candidates: List[ServiceCandidate],
        parsed_query: "ParsedQuery",
        user_location: Optional[tuple[float, float]] = None,
        default_duration: int = 60,
        *,
        location_resolution: Optional[ResolvedLocation] = None,
    ) -> FilterResult:
        """
        Apply all constraint filters to candidates.

        Args:
            candidates: Candidates from retrieval phase
            parsed_query: Parsed query with constraints
            user_location: User's (lng, lat) or None to resolve from query
            default_duration: Default lesson duration in minutes

        Returns:
            FilterResult with filtered candidates
        """
        if self._repository_override is not None and self._location_resolver_override is not None:
            # Unit tests can inject mocks to avoid DB access.
            self.repository = self._repository_override
            self.location_resolver = self._location_resolver_override
            if (
                location_resolution is None
                and parsed_query.location_text
                and parsed_query.location_type != "near_me"
                and user_location is None
            ):
                location_resolution = await self.location_resolver.resolve(
                    parsed_query.location_text,
                    original_query=parsed_query.original_query,
                    track_unresolved=True,
                    enable_semantic=True,
                )
            return self._filter_candidates_core(
                candidates,
                parsed_query,
                user_location,
                default_duration,
                location_resolution=location_resolution,
            )

        import asyncio

        with get_db_session() as db:
            self.repository = self._repository_override or FilterRepository(db)
            self.location_resolver = self._location_resolver_override or LocationResolver(
                db, region_code=self._region_code
            )
            if (
                location_resolution is None
                and parsed_query.location_text
                and parsed_query.location_type != "near_me"
                and user_location is None
            ):
                location_resolution = await self.location_resolver.resolve(
                    parsed_query.location_text,
                    original_query=parsed_query.original_query,
                    track_unresolved=True,
                    enable_semantic=True,
                )

            return await asyncio.to_thread(
                self._filter_candidates_core,
                candidates,
                parsed_query,
                user_location,
                default_duration,
                location_resolution=location_resolution,
            )

    def filter_candidates_sync(
        self,
        candidates: List[ServiceCandidate],
        parsed_query: "ParsedQuery",
        user_location: Optional[tuple[float, float]] = None,
        default_duration: int = 60,
        *,
        location_resolution: Optional[ResolvedLocation] = None,
    ) -> FilterResult:
        """
        Sync filtering variant for use inside batched DB bursts.

        Avoids OpenAI calls; resolves location with sync tiers only when needed.
        """
        if self._repository_override is None or self._location_resolver_override is None:
            raise RuntimeError("filter_candidates_sync requires repository and resolver overrides")

        self.repository = self._repository_override
        self.location_resolver = self._location_resolver_override

        if (
            location_resolution is None
            and parsed_query.location_text
            and parsed_query.location_type != "near_me"
            and user_location is None
        ):
            location_resolution = self.location_resolver.resolve_sync(
                parsed_query.location_text,
                original_query=parsed_query.original_query,
                track_unresolved=False,
            )

        return self._filter_candidates_core(
            candidates,
            parsed_query,
            user_location,
            default_duration,
            location_resolution=location_resolution,
        )

    def _filter_candidates_core(
        self,
        candidates: List[ServiceCandidate],
        parsed_query: "ParsedQuery",
        user_location: Optional[tuple[float, float]],
        default_duration: int,
        *,
        location_resolution: Optional[ResolvedLocation],
    ) -> FilterResult:
        perf_start = time_module.perf_counter()
        perf: Dict[str, int] = {}

        total_before = len(candidates)
        filters_applied: List[str] = []
        filter_stats: Dict[str, int] = {"initial_candidates": total_before}
        lesson_type = (
            parsed_query.lesson_type
            if parsed_query.lesson_type and parsed_query.lesson_type != "any"
            else None
        )

        # Convert candidates to working list
        working = [
            FilteredCandidate(
                service_id=c.service_id,
                service_catalog_id=c.service_catalog_id,
                instructor_id=c.instructor_id,
                hybrid_score=c.hybrid_score,
                name=c.name,
                description=c.description,
                min_hourly_rate=c.min_hourly_rate,
            )
            for c in candidates
        ]

        # Step 1: Price filter
        price_start = time_module.perf_counter()
        if parsed_query.max_price:
            working = self._filter_price(
                working,
                parsed_query.max_price,
                lesson_type=lesson_type,
            )
            filters_applied.append("price")
            filter_stats["after_price"] = len(working)
        perf["price_ms"] = int((time_module.perf_counter() - price_start) * 1000)

        # Step 1.5: Lesson type filter (online/in-person)
        lesson_type_start = time_module.perf_counter()
        if lesson_type:
            if parsed_query.max_price is None:
                working = self._filter_lesson_type(working, lesson_type)
            filters_applied.append("lesson_type")
            filter_stats["after_lesson_type"] = len(working)
        perf["lesson_type_ms"] = int((time_module.perf_counter() - lesson_type_start) * 1000)

        # Step 2: Location filter
        resolved_location = user_location
        location_start = time_module.perf_counter()
        if resolved_location:
            working = self._filter_location(working, resolved_location)
            filters_applied.append("location")
            filter_stats["after_location"] = len(working)
        elif parsed_query.location_text and parsed_query.location_type != "near_me":
            # Ensure filter funnel always includes an "after_location" stage when a location was parsed.
            # Even if we end up skipping the filter (unresolved/ambiguous), we want observability.
            before_location_count = len(working)
            filter_stats.setdefault("after_location", before_location_count)
            if location_resolution is None:
                location_resolution = ResolvedLocation.from_not_found()
            if location_resolution.requires_clarification:
                # In practice, "ambiguous" often means one user-facing neighborhood maps to multiple
                # region_boundaries rows (e.g., "Upper East Side" -> multiple UES subregions).
                # Apply a union filter across candidates to avoid ignoring location entirely.
                candidate_ids = [
                    c["region_id"]
                    for c in (location_resolution.candidates or [])
                    if c.get("region_id")
                ]
                candidate_ids = list(dict.fromkeys(candidate_ids))

                # Apply a strict union filter across candidate regions (may yield 0).
                working = (
                    self._filter_location_regions(working, candidate_ids) if candidate_ids else []
                )
                filters_applied.append("location")
                filter_stats["after_location"] = len(working)
                logger.info(
                    "Ambiguous location '%s' resolved to %d candidate regions; applied union filter (%d -> %d)",
                    parsed_query.location_text,
                    len(candidate_ids),
                    before_location_count,
                    len(working),
                )
            elif location_resolution.resolved:
                if location_resolution.region_id:
                    working = self._filter_location_region(working, location_resolution.region_id)
                    filters_applied.append("location")
                    filter_stats["after_location"] = len(working)
                elif location_resolution.borough:
                    working = self._filter_location_borough(working, location_resolution.borough)
                    filters_applied.append("location")
                    filter_stats["after_location"] = len(working)
            else:
                logger.info(
                    "Unresolved location '%s' (region=%s); skipping location filter",
                    parsed_query.location_text,
                    self.location_resolver.region_code,
                    extra={
                        "location_text": parsed_query.location_text,
                        "region_code": self.location_resolver.region_code,
                        "original_query": parsed_query.original_query,
                    },
                )

        # Step 3: Availability filter
        perf["location_ms"] = int((time_module.perf_counter() - location_start) * 1000)

        availability_start = time_module.perf_counter()
        if parsed_query.date or parsed_query.date_range_start or parsed_query.time_after:
            working = self._filter_availability(working, parsed_query, default_duration)
            filters_applied.append("availability")
            filter_stats["after_availability"] = len(working)
        perf["availability_ms"] = int((time_module.perf_counter() - availability_start) * 1000)

        # Step 4: Soft filtering if too few results
        soft_start = time_module.perf_counter()
        soft_filtering_used = False
        relaxed_constraints: List[str] = []
        has_relaxable_constraints = bool(
            parsed_query.max_price
            or parsed_query.date
            or parsed_query.date_range_start
            or parsed_query.date_range_end
            or parsed_query.time_after
            or parsed_query.time_before
            or resolved_location
            or (
                parsed_query.location_text
                and parsed_query.location_type != "near_me"
                and location_resolution
                and not location_resolution.not_found
            )
        )

        if (
            has_relaxable_constraints
            and len(working) < MIN_RESULTS_BEFORE_SOFT_FILTER
            and total_before > 0
        ):
            logger.info("Only %d results, applying soft filtering", len(working))
            working, relaxed_constraints = self._apply_soft_filtering(
                original_candidates=candidates,
                parsed_query=parsed_query,
                user_location=resolved_location,
                location_resolution=location_resolution,
                duration_minutes=default_duration,
                strict_service_ids={c.service_id for c in working},
                filter_stats=filter_stats,
            )
            soft_filtering_used = bool(relaxed_constraints)
            if soft_filtering_used:
                filter_stats["after_soft_filtering"] = len(working)
        perf["soft_filter_ms"] = int((time_module.perf_counter() - soft_start) * 1000)

        filter_stats["final_candidates"] = len(working)
        perf_total_ms = int((time_module.perf_counter() - perf_start) * 1000)
        if _PERF_LOG_ENABLED and (perf_total_ms >= _PERF_LOG_SLOW_MS):
            logger.info(
                "NL search filter timings: %s",
                {
                    **perf,
                    "total_ms": perf_total_ms,
                    "initial": total_before,
                    "final": len(working),
                    "soft_filtered": soft_filtering_used,
                    "relaxed": list(relaxed_constraints),
                    "region": self.location_resolver.region_code,
                },
            )

        return FilterResult(
            candidates=working,
            total_before_filter=total_before,
            total_after_filter=len(working),
            filters_applied=filters_applied,
            soft_filtering_used=soft_filtering_used,
            relaxed_constraints=relaxed_constraints,
            location_resolution=location_resolution,
            filter_stats=filter_stats,
        )

    def _filter_price(
        self,
        candidates: List[FilteredCandidate],
        max_price: int,
        *,
        lesson_type: Optional[str] = None,
    ) -> List[FilteredCandidate]:
        """Apply price filter, intersecting with lesson type when requested."""
        if lesson_type and lesson_type != "any":
            return self._filter_lesson_type_rates(
                candidates,
                lesson_type,
                max_price=max_price,
            )

        filtered = []
        for c in candidates:
            if c.min_hourly_rate <= max_price:
                c.passed_price = True
                filtered.append(c)
            else:
                c.passed_price = False
        return filtered

    def _filter_lesson_type(
        self,
        candidates: List[FilteredCandidate],
        lesson_type: str,
    ) -> List[FilteredCandidate]:
        """
        Apply lesson type filter (online vs in-person).

        Uses the FilterRepository to check whether matching per-format price rows exist.

        Args:
            candidates: Current candidate list
            lesson_type: "online" or "in_person"

        Returns:
            Filtered list of candidates matching the lesson type
        """
        return self._filter_lesson_type_rates(candidates, lesson_type)

    def _filter_lesson_type_rates(
        self,
        candidates: List[FilteredCandidate],
        lesson_type: str,
        *,
        max_price: Optional[int] = None,
    ) -> List[FilteredCandidate]:
        """Filter candidates to services with qualifying lesson-type pricing rows."""
        if not candidates or lesson_type == "any":
            return candidates

        _KNOWN_LESSON_TYPES = {"online", "in_person"}
        if lesson_type not in _KNOWN_LESSON_TYPES:
            logger.warning("Unknown lesson_type %r — skipping format filter", lesson_type)
            return candidates

        service_ids = [c.service_id for c in candidates]
        rate_map = self.repository.get_lesson_type_rates(
            service_ids,
            lesson_type,
            max_price=max_price,
        )

        filtered: List[FilteredCandidate] = []
        for c in candidates:
            lesson_rate = rate_map.get(c.service_id)
            c.lesson_type_hourly_rate = lesson_rate
            if lesson_rate is not None:
                # max_price filtering already applied by the repository query
                # (get_lesson_type_rates), so presence in rate_map means the
                # candidate passed both lesson-type and price constraints.
                if max_price is not None:
                    c.passed_price = True
                filtered.append(c)
            elif max_price is not None:
                c.passed_price = False
        return filtered

    def _filter_location(
        self,
        candidates: List[FilteredCandidate],
        location: tuple[float, float],
    ) -> List[FilteredCandidate]:
        """Apply PostGIS location filter."""
        if not candidates:
            return []

        lng, lat = location
        instructor_ids = list({c.instructor_id for c in candidates})

        passing_ids = set(self.repository.filter_by_location(instructor_ids, lng, lat))

        filtered = []
        for c in candidates:
            if c.instructor_id in passing_ids:
                c.passed_location = True
                filtered.append(c)
            else:
                c.passed_location = False

        return filtered

    def _filter_location_region(
        self,
        candidates: List[FilteredCandidate],
        region_boundary_id: str,
    ) -> List[FilteredCandidate]:
        """Filter candidates to instructors covering a specific region boundary."""
        if not candidates:
            return []

        instructor_ids = list({c.instructor_id for c in candidates})
        passing_ids = set(
            self.repository.filter_by_region_coverage(instructor_ids, region_boundary_id)
        )

        filtered: List[FilteredCandidate] = []
        for c in candidates:
            if c.instructor_id in passing_ids:
                c.passed_location = True
                filtered.append(c)
            else:
                c.passed_location = False
        return filtered

    def _filter_location_regions(
        self,
        candidates: List[FilteredCandidate],
        region_boundary_ids: List[str],
    ) -> List[FilteredCandidate]:
        """Filter candidates to instructors covering any of the given region boundaries."""
        if not candidates or not region_boundary_ids:
            return candidates

        instructor_ids = list({c.instructor_id for c in candidates})
        passing_ids = set(
            self.repository.filter_by_any_region_coverage(instructor_ids, region_boundary_ids)
        )

        filtered: List[FilteredCandidate] = []
        for c in candidates:
            if c.instructor_id in passing_ids:
                c.passed_location = True
                filtered.append(c)
            else:
                c.passed_location = False
        return filtered

    def _filter_location_borough(
        self,
        candidates: List[FilteredCandidate],
        borough_name: str,
    ) -> List[FilteredCandidate]:
        """Filter candidates to instructors covering any neighborhood in the borough."""
        if not candidates:
            return []

        instructor_ids = list({c.instructor_id for c in candidates})
        passing_ids = set(self.repository.filter_by_parent_region(instructor_ids, borough_name))

        filtered: List[FilteredCandidate] = []
        for c in candidates:
            if c.instructor_id in passing_ids:
                c.passed_location = True
                filtered.append(c)
            else:
                c.passed_location = False
        return filtered

    def _filter_availability(
        self,
        candidates: List[FilteredCandidate],
        parsed_query: "ParsedQuery",
        duration_minutes: int,
    ) -> List[FilteredCandidate]:
        """Apply availability filter using bitmap check."""
        if not candidates:
            return []

        instructor_ids = list({c.instructor_id for c in candidates})

        # Parse time constraints
        time_after = self._parse_time(parsed_query.time_after)
        time_before = self._parse_time(parsed_query.time_before)

        # Determine dates to check
        target_date = parsed_query.date

        if parsed_query.date_type == "weekend":
            # Check both Saturday and Sunday
            if parsed_query.date_range_start and parsed_query.date_range_end:
                availability_map = self.repository.check_weekend_availability(
                    instructor_ids,
                    parsed_query.date_range_start,
                    parsed_query.date_range_end,
                    time_after,
                    time_before,
                    duration_minutes,
                )
            else:
                # No specific weekend, check next 7 days
                availability_map = self.repository.filter_by_availability(
                    instructor_ids,
                    target_date=None,
                    time_after=time_after,
                    time_before=time_before,
                    duration_minutes=duration_minutes,
                )
        elif target_date:
            # Single date
            availability_map = self.repository.filter_by_availability(
                instructor_ids,
                target_date,
                time_after,
                time_before,
                duration_minutes,
            )
        else:
            # No date specified - check next 7 days
            availability_map = self.repository.filter_by_availability(
                instructor_ids,
                target_date=None,
                time_after=time_after,
                time_before=time_before,
                duration_minutes=duration_minutes,
            )
        availability_map = self._refine_buffered_availability_map(
            availability_map,
            instructor_ids=instructor_ids,
            parsed_query=parsed_query,
            time_after=time_after,
            time_before=time_before,
            duration_minutes=duration_minutes,
        )

        filtered = []
        for c in candidates:
            available_dates = availability_map.get(c.instructor_id, [])
            if available_dates:
                c.passed_availability = True
                c.available_dates = available_dates
                c.earliest_available = min(available_dates) if available_dates else None
                filtered.append(c)
            else:
                c.passed_availability = False

        return filtered

    @staticmethod
    def _search_requested_location_type(parsed_query: "ParsedQuery") -> str:
        return "online" if parsed_query.lesson_type == "online" else "student_location"

    def _refine_buffered_availability_map(
        self,
        availability_map: Dict[str, List[date]],
        *,
        instructor_ids: List[str],
        parsed_query: "ParsedQuery",
        time_after: time | None,
        time_before: time | None,
        duration_minutes: int,
    ) -> Dict[str, List[date]]:
        if not availability_map:
            return availability_map

        dates_to_check = sorted(
            {available_date for dates in availability_map.values() for available_date in dates}
        )
        if not dates_to_check:
            return availability_map

        context_getter = getattr(self.repository, "get_buffered_availability_context", None)
        if not callable(context_getter):
            return availability_map

        context = context_getter(instructor_ids, dates_to_check)
        if not isinstance(context, dict):
            return availability_map

        bits_by_key = context.get("bits_by_key")
        format_tags_by_key = context.get("format_tags_by_key")
        bookings_by_key = context.get("bookings_by_key")
        profiles_by_instructor = context.get("profiles_by_instructor")
        if not isinstance(bits_by_key, dict):
            return availability_map
        if not isinstance(format_tags_by_key, dict):
            format_tags_by_key = {}
        if not isinstance(bookings_by_key, dict):
            bookings_by_key = {}
        if not isinstance(profiles_by_instructor, dict):
            profiles_by_instructor = {}

        from app.services.availability_service import AvailabilityService

        requested_location_type = self._search_requested_location_type(parsed_query)
        repository_db = getattr(self.repository, "db", None)
        default_non_travel_buffer_minutes = 15
        default_travel_buffer_minutes = 60
        if repository_db is not None:
            config_service = ConfigService(repository_db)
            default_non_travel_buffer_minutes = config_service.get_default_buffer_minutes("online")
            default_travel_buffer_minutes = config_service.get_default_buffer_minutes(
                "student_location"
            )

        refined: Dict[str, List[date]] = {}
        for instructor_id, available_dates in availability_map.items():
            kept_dates: List[date] = []
            profile = profiles_by_instructor.get(instructor_id)
            (
                non_travel_buffer_minutes,
                travel_buffer_minutes,
            ) = AvailabilityService._resolve_buffer_profile_values(
                profile,
                default_non_travel_buffer_minutes=default_non_travel_buffer_minutes,
                default_travel_buffer_minutes=default_travel_buffer_minutes,
            )
            for available_date in available_dates:
                bits = bits_by_key.get((instructor_id, available_date))
                if bits is None:
                    continue
                base_windows = [
                    (string_to_time(start_str), string_to_time(end_str))
                    for start_str, end_str in windows_from_bits(bits)
                ]
                remaining_windows = AvailabilityService._subtract_buffered_bookings_from_windows(
                    base_windows,
                    bookings_by_key.get((instructor_id, available_date), []),
                    requested_location_type=requested_location_type,
                    non_travel_buffer_minutes=non_travel_buffer_minutes,
                    travel_buffer_minutes=travel_buffer_minutes,
                )
                remaining_windows = AvailabilityService._filter_windows_by_format_tags(
                    remaining_windows,
                    format_tags_by_key.get((instructor_id, available_date)),
                    requested_location_type=requested_location_type,
                )
                if AvailabilityService._windows_support_booking_request(
                    remaining_windows,
                    time_after=time_after,
                    time_before=time_before,
                    duration_minutes=duration_minutes,
                ):
                    kept_dates.append(available_date)
            if kept_dates:
                refined[instructor_id] = kept_dates
        return refined

    def _parse_time(self, time_str: Optional[str]) -> Optional[time]:
        """Parse time string (HH:MM) to time object."""
        if not time_str:
            return None

        try:
            parts = time_str.split(":")
            return time(hour=int(parts[0]), minute=int(parts[1]))
        except (ValueError, IndexError):
            return None

    def _apply_soft_filtering(
        self,
        original_candidates: List[ServiceCandidate],
        parsed_query: "ParsedQuery",
        user_location: Optional[tuple[float, float]],
        location_resolution: Optional[ResolvedLocation],
        duration_minutes: int,
        strict_service_ids: set[str],
        filter_stats: Dict[str, int],
    ) -> tuple[List[FilteredCandidate], List[str]]:
        """
        Progressively relax constraints until we reach a minimum result threshold.

        Relaxation order (least important -> most important):
        1) time: remove time_after/time_before
        2) date: remove date constraints (still require availability in next 7 days)
        3) location: expand to nearby areas
        4) price: increase max_price by SOFT_PRICE_MULTIPLIER

        Returns:
            (relaxed_candidates, relaxed_constraints)
        """

        def _build_base_candidates() -> List[FilteredCandidate]:
            # Note: lesson_type_hourly_rate is intentionally omitted here.
            # Soft filtering rebuilds from the original retrieval set, and
            # lesson-type rates are recomputed during _filter_lesson_type_rates.
            return [
                FilteredCandidate(
                    service_id=c.service_id,
                    service_catalog_id=c.service_catalog_id,
                    instructor_id=c.instructor_id,
                    hybrid_score=c.hybrid_score,
                    name=c.name,
                    description=c.description,
                    min_hourly_rate=c.min_hourly_rate,
                )
                for c in original_candidates
            ]

        def _has_availability_constraint(query: "ParsedQuery") -> bool:
            return bool(
                query.date
                or query.date_range_start
                or query.date_range_end
                or query.time_after
                or query.time_before
            )

        def _apply_location_hard(
            candidates: List[FilteredCandidate],
        ) -> List[FilteredCandidate]:
            if user_location:
                return self._filter_location(candidates, user_location)

            if not (parsed_query.location_text and parsed_query.location_type != "near_me"):
                return candidates

            if not location_resolution or not (
                location_resolution.resolved or location_resolution.requires_clarification
            ):
                return candidates

            if location_resolution.requires_clarification:
                candidate_ids = [
                    c["region_id"]
                    for c in (location_resolution.candidates or [])
                    if isinstance(c, dict) and c.get("region_id")
                ]
                candidate_ids = list(dict.fromkeys(candidate_ids))
                return (
                    self._filter_location_regions(candidates, candidate_ids)
                    if candidate_ids
                    else []
                )

            if location_resolution.region_id:
                return self._filter_location_region(candidates, str(location_resolution.region_id))

            if location_resolution.borough:
                return self._filter_location_borough(candidates, str(location_resolution.borough))

            return candidates

        def _apply_location_soft(
            candidates: List[FilteredCandidate],
        ) -> List[FilteredCandidate]:
            if user_location:
                lng, lat = user_location
                instructor_ids = list({c.instructor_id for c in candidates})
                passing_ids = set(self.repository.filter_by_location_soft(instructor_ids, lng, lat))
                return [c for c in candidates if c.instructor_id in passing_ids]

            if not (parsed_query.location_text and parsed_query.location_type != "near_me"):
                return candidates

            if not location_resolution or not (
                location_resolution.resolved or location_resolution.requires_clarification
            ):
                return candidates

            region_ids: List[str] = []
            if location_resolution.region_id:
                region_ids = [str(location_resolution.region_id)]
            elif location_resolution.requires_clarification:
                region_ids = [
                    str(c.get("region_id"))
                    for c in (location_resolution.candidates or [])
                    if isinstance(c, dict) and c.get("region_id")
                ]
                region_ids = list(dict.fromkeys(region_ids))

            if region_ids:
                instructor_ids = list({c.instructor_id for c in candidates})
                distances = self.repository.get_instructor_min_distance_to_regions(
                    instructor_ids, region_ids
                )
                passing_ids = {
                    iid for iid, dist_m in distances.items() if dist_m <= SOFT_DISTANCE_METERS
                }
                return [c for c in candidates if c.instructor_id in passing_ids]

            # Borough-only locations are already quite broad; if we can't resolve to concrete regions,
            # relaxing location falls back to skipping the filter (last-resort).
            return candidates

        def _run_filters(
            query: "ParsedQuery",
            *,
            relax_location: bool,
            enforce_availability: bool,
        ) -> List[FilteredCandidate]:
            working = _build_base_candidates()
            lesson_type = (
                query.lesson_type if query.lesson_type and query.lesson_type != "any" else None
            )

            if query.max_price:
                working = self._filter_price(
                    working,
                    query.max_price,
                    lesson_type=lesson_type,
                )

            if lesson_type and query.max_price is None:
                working = self._filter_lesson_type(working, lesson_type)

            working = (
                _apply_location_soft(working) if relax_location else _apply_location_hard(working)
            )

            if enforce_availability or _has_availability_constraint(query):
                working = self._filter_availability(working, query, duration_minutes)

            return working

        # If the user specified any availability constraint, keep a baseline requirement that
        # instructors have availability within the next 7 days (even after relaxing date/time).
        enforce_availability = _has_availability_constraint(parsed_query)

        original_max_price = parsed_query.max_price
        time_relaxed = False
        date_relaxed = False
        location_relax_enabled = False
        price_relaxed = False

        relaxed_constraints: List[str] = []
        relax_location = False
        relaxed_query = replace(parsed_query)

        # Start from the strict constraints and progressively relax.
        best = _run_filters(
            relaxed_query, relax_location=relax_location, enforce_availability=enforce_availability
        )

        def _mark_soft(candidates: List[FilteredCandidate], constraints: List[str]) -> None:
            for c in candidates:
                if c.service_id in strict_service_ids:
                    continue
                if constraints:
                    c.soft_filtered = True
                    c.soft_filter_reasons = [f"{step}_relaxed" for step in constraints]
                    c.hybrid_score *= 0.7

        if len(best) >= MIN_RESULTS_BEFORE_SOFT_FILTER:
            _mark_soft(best, relaxed_constraints)
            return best, relaxed_constraints

        # TIME relaxation
        if relaxed_query.time_after or relaxed_query.time_before:
            relaxed_query.time_after = None
            relaxed_query.time_before = None
            relaxed_query.time_window = None
            time_relaxed = True
            relaxed_constraints.append("time")
            best = _run_filters(
                relaxed_query,
                relax_location=relax_location,
                enforce_availability=enforce_availability,
            )
            filter_stats["after_relax_time"] = len(best)
            if len(best) >= MIN_RESULTS_BEFORE_SOFT_FILTER:
                _mark_soft(best, relaxed_constraints)
                return best, relaxed_constraints

        # DATE relaxation
        if relaxed_query.date or relaxed_query.date_range_start or relaxed_query.date_range_end:
            relaxed_query.date = None
            relaxed_query.date_range_start = None
            relaxed_query.date_range_end = None
            relaxed_query.date_type = None
            date_relaxed = True
            relaxed_constraints.append("date")
            best = _run_filters(
                relaxed_query,
                relax_location=relax_location,
                enforce_availability=enforce_availability,
            )
            filter_stats["after_relax_date"] = len(best)
            if len(best) >= MIN_RESULTS_BEFORE_SOFT_FILTER:
                _mark_soft(best, relaxed_constraints)
                return best, relaxed_constraints

        # LOCATION relaxation
        strict_location_matches_exist = bool(filter_stats.get("after_location", 0) > 0)
        can_relax_location = False
        if user_location:
            can_relax_location = True
        elif (
            parsed_query.location_text
            and parsed_query.location_type != "near_me"
            and location_resolution
            and not location_resolution.not_found
        ):
            can_relax_location = True

        # IMPORTANT: If the strict location filter produced any results, keep location strict.
        # Users explicitly asked for a location; don't expand to nearby areas just to pad count.
        if can_relax_location and not strict_location_matches_exist:
            relax_location = True
            location_relax_enabled = True
            best = _run_filters(
                relaxed_query,
                relax_location=relax_location,
                enforce_availability=enforce_availability,
            )
            filter_stats["after_relax_location"] = len(best)
            if len(best) >= MIN_RESULTS_BEFORE_SOFT_FILTER:
                relaxed_constraints.append("location")
                _mark_soft(best, relaxed_constraints)
                return best, relaxed_constraints

        # PRICE relaxation (last resort)
        if relaxed_query.max_price:
            relaxed_query.max_price = int(relaxed_query.max_price * SOFT_PRICE_MULTIPLIER)
            price_relaxed = True
            relaxed_constraints.append("price")
            best = _run_filters(
                relaxed_query,
                relax_location=relax_location,
                enforce_availability=enforce_availability,
            )
            filter_stats["after_relax_price"] = len(best)

        def _service_ids(cands: List[FilteredCandidate]) -> set[str]:
            return {c.service_id for c in cands}

        # Only report constraints that actually affected the final candidate set.
        best_ids = _service_ids(best)
        effective_constraints: List[str] = []

        if time_relaxed:
            with_time_query = replace(relaxed_query)
            with_time_query.time_after = parsed_query.time_after
            with_time_query.time_before = parsed_query.time_before
            with_time_query.time_window = parsed_query.time_window
            with_time = _run_filters(
                with_time_query,
                relax_location=relax_location,
                enforce_availability=enforce_availability,
            )
            if _service_ids(with_time) != best_ids:
                effective_constraints.append("time")

        if date_relaxed:
            with_date_query = replace(relaxed_query)
            with_date_query.date = parsed_query.date
            with_date_query.date_range_start = parsed_query.date_range_start
            with_date_query.date_range_end = parsed_query.date_range_end
            with_date_query.date_type = parsed_query.date_type
            with_date = _run_filters(
                with_date_query,
                relax_location=relax_location,
                enforce_availability=enforce_availability,
            )
            if _service_ids(with_date) != best_ids:
                effective_constraints.append("date")

        if location_relax_enabled:
            without_location = _run_filters(
                relaxed_query,
                relax_location=False,
                enforce_availability=enforce_availability,
            )
            if _service_ids(without_location) != best_ids:
                effective_constraints.append("location")

        if price_relaxed and original_max_price is not None:
            without_price_query = replace(relaxed_query)
            without_price_query.max_price = original_max_price
            without_price = _run_filters(
                without_price_query,
                relax_location=relax_location,
                enforce_availability=enforce_availability,
            )
            if _service_ids(without_price) != best_ids:
                effective_constraints.append("price")

        _mark_soft(best, effective_constraints)
        return best, effective_constraints
