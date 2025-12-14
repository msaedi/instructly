# backend/app/services/search/filter_service.py
"""
Constraint filtering service for NL search.
Applies price, location, and availability filters to candidates.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import date, time
import logging
from typing import TYPE_CHECKING, Dict, List, Optional

from app.repositories.filter_repository import FilterRepository
from app.services.search.location_resolver import LocationResolver, ResolvedLocation
from app.services.search.retriever import ServiceCandidate

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.services.search.query_parser import ParsedQuery

logger = logging.getLogger(__name__)

# Configuration
MIN_RESULTS_BEFORE_SOFT_FILTER = 5
SOFT_PRICE_MULTIPLIER = 1.25  # Allow 25% over budget
SOFT_DISTANCE_METERS = 10000  # 10km for soft location filter


@dataclass
class FilteredCandidate:
    """A candidate that passed filtering."""

    service_id: str
    service_catalog_id: str
    instructor_id: str
    hybrid_score: float

    name: str
    description: Optional[str]
    price_per_hour: int

    passed_price: bool = True
    passed_location: bool = True
    passed_availability: bool = True

    soft_filtered: bool = False
    soft_filter_reasons: List[str] = field(default_factory=list)

    available_dates: List[date] = field(default_factory=list)
    earliest_available: Optional[date] = None


@dataclass
class FilterResult:
    """Result of constraint filtering."""

    candidates: List[FilteredCandidate]
    total_before_filter: int
    total_after_filter: int
    filters_applied: List[str] = field(default_factory=list)
    soft_filtering_used: bool = False
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
    If < 5 results after hard filters, relax constraints and mark results.
    """

    def __init__(
        self,
        db: "Session",
        repository: Optional[FilterRepository] = None,
        region_code: str = "nyc",
    ) -> None:
        self.db = db
        self.repository = repository or FilterRepository(db)
        self.location_resolver = LocationResolver(db, region_code=region_code)

    async def filter_candidates(
        self,
        candidates: List[ServiceCandidate],
        parsed_query: "ParsedQuery",
        user_location: Optional[tuple[float, float]] = None,
        default_duration: int = 60,
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
        return await asyncio.to_thread(
            self._filter_candidates_sync,
            candidates,
            parsed_query,
            user_location,
            default_duration,
        )

    def _filter_candidates_sync(
        self,
        candidates: List[ServiceCandidate],
        parsed_query: "ParsedQuery",
        user_location: Optional[tuple[float, float]],
        default_duration: int,
    ) -> FilterResult:
        total_before = len(candidates)
        filters_applied: List[str] = []
        filter_stats: Dict[str, int] = {"initial_candidates": total_before}

        # Convert candidates to working list
        working = [
            FilteredCandidate(
                service_id=c.service_id,
                service_catalog_id=c.service_catalog_id,
                instructor_id=c.instructor_id,
                hybrid_score=c.hybrid_score,
                name=c.name,
                description=c.description,
                price_per_hour=c.price_per_hour,
            )
            for c in candidates
        ]

        # Step 1: Price filter
        if parsed_query.max_price:
            working = self._filter_price(working, parsed_query.max_price)
            filters_applied.append("price")
            filter_stats["after_price"] = len(working)

        # Step 2: Location filter
        location_resolution: Optional[ResolvedLocation] = None
        resolved_location = user_location
        if resolved_location:
            working = self._filter_location(working, resolved_location)
            filters_applied.append("location")
            filter_stats["after_location"] = len(working)
        elif parsed_query.location_text and parsed_query.location_type != "near_me":
            # Ensure filter funnel always includes an "after_location" stage when a location was parsed.
            # Even if we end up skipping the filter (unresolved/ambiguous), we want observability.
            before_location_count = len(working)
            filter_stats.setdefault("after_location", before_location_count)

            location_resolution = self.location_resolver.resolve(
                parsed_query.location_text,
                original_query=parsed_query.original_query,
                track_unresolved=True,
            )
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

                filtered = (
                    self._filter_location_regions(working, candidate_ids) if candidate_ids else []
                )
                if filtered:
                    working = filtered
                    filters_applied.append("location")
                    filter_stats["after_location"] = len(working)
                    logger.info(
                        "Ambiguous location '%s' resolved to %d candidate regions; applied union filter (%d -> %d)",
                        parsed_query.location_text,
                        len(candidate_ids),
                        before_location_count,
                        len(working),
                    )
                else:
                    # Best-effort borough fallback if all candidates share a borough.
                    boroughs = {
                        c.get("borough")
                        for c in (location_resolution.candidates or [])
                        if c.get("borough")
                    }
                    if len(boroughs) == 1:
                        borough = next(iter(boroughs))
                        borough_filtered = self._filter_location_borough(working, str(borough))
                        if borough_filtered:
                            working = borough_filtered
                            filters_applied.append("location")
                            filter_stats["after_location"] = len(working)
                            logger.info(
                                "Ambiguous location '%s' fell back to borough '%s' (%d -> %d)",
                                parsed_query.location_text,
                                borough,
                                before_location_count,
                                len(working),
                            )
                        else:
                            logger.info(
                                "Ambiguous location '%s' (region=%s); no candidate coverage match; skipping location filter",
                                parsed_query.location_text,
                                self.location_resolver.region_code,
                            )
                    else:
                        logger.info(
                            "Ambiguous location '%s' (region=%s); skipping location filter",
                            parsed_query.location_text,
                            self.location_resolver.region_code,
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
        if parsed_query.date or parsed_query.date_range_start or parsed_query.time_after:
            working = self._filter_availability(working, parsed_query, default_duration)
            filters_applied.append("availability")
            filter_stats["after_availability"] = len(working)

        # Step 4: Soft filtering if too few results
        soft_filtering_used = False
        if len(working) < MIN_RESULTS_BEFORE_SOFT_FILTER and total_before > 0:
            logger.info(f"Only {len(working)} results, applying soft filtering")
            working = self._apply_soft_filtering(
                candidates, parsed_query, resolved_location, default_duration
            )
            soft_filtering_used = True
            filter_stats["after_soft_filtering"] = len(working)

        filter_stats["final_candidates"] = len(working)
        return FilterResult(
            candidates=working,
            total_before_filter=total_before,
            total_after_filter=len(working),
            filters_applied=filters_applied,
            soft_filtering_used=soft_filtering_used,
            location_resolution=location_resolution,
            filter_stats=filter_stats,
        )

    def _filter_price(
        self,
        candidates: List[FilteredCandidate],
        max_price: int,
    ) -> List[FilteredCandidate]:
        """Apply price filter."""
        filtered = []
        for c in candidates:
            if c.price_per_hour <= max_price:
                c.passed_price = True
                filtered.append(c)
            else:
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
        location: Optional[tuple[float, float]],
        duration_minutes: int,
    ) -> List[FilteredCandidate]:
        """
        Apply relaxed filters when hard filters return too few results.

        Relaxation rules:
        - Price: Allow up to 1.25x max_price
        - Location: Expand distance to 10km
        - Availability: Check next 7 days instead of specific date
        """
        working = [
            FilteredCandidate(
                service_id=c.service_id,
                service_catalog_id=c.service_catalog_id,
                instructor_id=c.instructor_id,
                hybrid_score=c.hybrid_score,
                name=c.name,
                description=c.description,
                price_per_hour=c.price_per_hour,
                soft_filtered=True,
            )
            for c in original_candidates
        ]

        # Soft price filter
        if parsed_query.max_price:
            soft_max = int(parsed_query.max_price * SOFT_PRICE_MULTIPLIER)
            new_working = []
            for c in working:
                if c.price_per_hour <= soft_max:
                    if c.price_per_hour > parsed_query.max_price:
                        c.soft_filter_reasons.append("price_relaxed")
                    new_working.append(c)
            working = new_working

        # Soft location filter
        if location:
            lng, lat = location
            instructor_ids = list({c.instructor_id for c in working})
            passing_ids = set(self.repository.filter_by_location_soft(instructor_ids, lng, lat))
            hard_passing_ids = (
                set(self.repository.filter_by_location(list(passing_ids), lng, lat))
                if passing_ids
                else set()
            )

            new_working = []
            for c in working:
                if c.instructor_id in passing_ids:
                    if c.instructor_id not in hard_passing_ids:
                        c.soft_filter_reasons.append("location_relaxed")
                    new_working.append(c)
            working = new_working

        # Soft availability filter (always check 7 days)
        instructor_ids = list({c.instructor_id for c in working})
        availability_map = self.repository.filter_by_availability(
            instructor_ids,
            target_date=None,  # Check next 7 days
            time_after=self._parse_time(parsed_query.time_after),
            time_before=self._parse_time(parsed_query.time_before),
            duration_minutes=duration_minutes,
        )

        final = []
        for c in working:
            available_dates = availability_map.get(c.instructor_id, [])
            if available_dates:
                c.available_dates = available_dates
                c.earliest_available = min(available_dates)

                # Check if original date constraint wasn't met
                if parsed_query.date and parsed_query.date not in available_dates:
                    c.soft_filter_reasons.append("availability_relaxed")

                final.append(c)

        # Apply score penalty for soft-filtered results
        for c in final:
            if c.soft_filter_reasons:
                c.hybrid_score *= 0.7

        return final
