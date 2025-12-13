# backend/app/repositories/filter_repository.py
"""
Repository for filter-related database queries.
Handles PostGIS location checks and availability validation.

Adapted to actual InstaInstru schema:
- nyc_locations: Simple lat/lng columns
- instructor_service_areas + region_boundaries: Service area polygons
- availability_days + check_availability function: Bitmap availability
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Dict, List, Optional, Tuple

import pytz
from sqlalchemy import text
from sqlalchemy.orm import Session

# NYC timezone for availability calculations (platform default)
NYC_TZ = pytz.timezone("America/New_York")


def _get_today_nyc() -> date:
    """Get today's date in NYC timezone."""
    return datetime.now(NYC_TZ).date()


class FilterRepository:
    """
    Repository for search filtering queries.

    Handles:
    - PostGIS location containment checks via region_boundaries
    - Availability bitmap validation via check_availability function
    - Price filtering (done in-memory, not here)
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    # =========================================================================
    # Location Filtering (PostGIS)
    # =========================================================================

    def get_location_centroid(
        self,
        location_name: str,
    ) -> Optional[Tuple[float, float]]:
        """
        Get centroid coordinates for a NYC location name.

        Uses the nyc_locations table which has simple lat/lng columns.

        Returns:
            (longitude, latitude) or None if not found.
        """
        query = text(
            """
            SELECT lng, lat
            FROM nyc_locations
            WHERE LOWER(name) = LOWER(:name)
               OR LOWER(:name) = ANY(
                   SELECT LOWER(unnest(aliases))
               )
            LIMIT 1
        """
        )

        result = self.db.execute(query, {"name": location_name}).first()

        if result:
            return (float(result.lng), float(result.lat))
        return None

    def filter_by_location(
        self,
        instructor_ids: List[str],
        user_lng: float,
        user_lat: float,
        max_distance_meters: int = 5000,
    ) -> List[str]:
        """
        Filter instructors by location using PostGIS.

        Checks if user point is within instructor's service area regions
        (via instructor_service_areas + region_boundaries).

        Returns instructor IDs that either:
        1. Have a service area region containing the user point
        2. Have a service area region within max_distance_meters of user point

        Args:
            instructor_ids: List of instructor IDs to check
            user_lng: User longitude
            user_lat: User latitude
            max_distance_meters: Max distance from service area edge

        Returns:
            List of instructor IDs that pass location filter
        """
        if not instructor_ids:
            return []

        query = text(
            """
            WITH user_point AS (
                SELECT ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography as geom
            )
            SELECT DISTINCT isa.instructor_id
            FROM instructor_service_areas isa
            JOIN region_boundaries rb ON rb.id = isa.neighborhood_id
            CROSS JOIN user_point up
            WHERE isa.instructor_id = ANY(:instructor_ids)
              AND isa.is_active = true
              AND (
                -- Point inside polygon
                ST_Contains(rb.boundary::geometry, up.geom::geometry)
                OR
                -- Within distance of polygon edge
                ST_DWithin(rb.boundary::geography, up.geom, :max_distance)
              )
        """
        )

        result = self.db.execute(
            query,
            {
                "instructor_ids": instructor_ids,
                "lng": user_lng,
                "lat": user_lat,
                "max_distance": max_distance_meters,
            },
        )

        return [row.instructor_id for row in result]

    def filter_by_location_soft(
        self,
        instructor_ids: List[str],
        user_lng: float,
        user_lat: float,
        max_distance_meters: int = 10000,
    ) -> List[str]:
        """
        Soft location filter with relaxed distance.

        Used when hard filter returns too few results.
        """
        return self.filter_by_location(instructor_ids, user_lng, user_lat, max_distance_meters)

    # =========================================================================
    # Availability Filtering (Bitmap)
    # =========================================================================

    def check_availability_single_date(
        self,
        instructor_id: str,
        target_date: date,
        time_after: Optional[time] = None,
        time_before: Optional[time] = None,
        duration_minutes: int = 60,
    ) -> bool:
        """
        Check if instructor has availability on a specific date.

        Uses the check_availability function defined in the database.

        Args:
            instructor_id: Instructor user ID
            target_date: Date to check
            time_after: Earliest acceptable time (optional)
            time_before: Latest acceptable time (optional)
            duration_minutes: Required lesson duration

        Returns:
            True if instructor has availability matching constraints
        """
        query = text(
            """
            SELECT check_availability(
                :instructor_id,
                :target_date,
                :time_after,
                :time_before,
                :duration
            ) as available
        """
        )

        result = self.db.execute(
            query,
            {
                "instructor_id": instructor_id,
                "target_date": target_date,
                "time_after": time_after,
                "time_before": time_before,
                "duration": duration_minutes,
            },
        ).first()

        return bool(result.available) if result else False

    def filter_by_availability(
        self,
        instructor_ids: List[str],
        target_date: Optional[date] = None,
        time_after: Optional[time] = None,
        time_before: Optional[time] = None,
        duration_minutes: int = 60,
    ) -> Dict[str, List[date]]:
        """
        Filter instructors by availability.

        If target_date specified: Check that date only
        If no date: Check next 7 days, return dates with availability

        Args:
            instructor_ids: Instructor IDs to check
            target_date: Specific date to check (optional)
            time_after: Earliest acceptable time
            time_before: Latest acceptable time
            duration_minutes: Required lesson duration

        Returns:
            Dict mapping instructor_id to list of available dates
        """
        if not instructor_ids:
            return {}

        results: Dict[str, List[date]] = {}

        if target_date:
            dates_to_check = [target_date]
        else:
            # Check next 7 days using NYC timezone
            today = _get_today_nyc()
            dates_to_check = [today + timedelta(days=i) for i in range(7)]

        for instructor_id in instructor_ids:
            available_dates = []
            for check_date in dates_to_check:
                if self.check_availability_single_date(
                    instructor_id,
                    check_date,
                    time_after,
                    time_before,
                    duration_minutes,
                ):
                    available_dates.append(check_date)

            if available_dates:
                results[instructor_id] = available_dates

        return results

    def batch_check_availability(
        self,
        instructor_ids: List[str],
        target_date: date,
        time_after: Optional[time] = None,
        time_before: Optional[time] = None,
        duration_minutes: int = 60,
    ) -> List[str]:
        """
        Batch check availability for multiple instructors on same date.

        More efficient than individual checks for single-date queries.

        Returns:
            List of instructor IDs that have availability
        """
        if not instructor_ids:
            return []

        # Use set-based query for efficiency
        query = text(
            """
            SELECT DISTINCT ad.instructor_id
            FROM availability_days ad
            WHERE ad.instructor_id = ANY(:instructor_ids)
              AND ad.day_date = :target_date
              AND ad.bits IS NOT NULL
              AND check_availability(
                  ad.instructor_id,
                  :target_date,
                  :time_after,
                  :time_before,
                  :duration
              )
        """
        )

        result = self.db.execute(
            query,
            {
                "instructor_ids": instructor_ids,
                "target_date": target_date,
                "time_after": time_after,
                "time_before": time_before,
                "duration": duration_minutes,
            },
        )

        return [row.instructor_id for row in result]

    def check_weekend_availability(
        self,
        instructor_ids: List[str],
        saturday: date,
        sunday: date,
        time_after: Optional[time] = None,
        time_before: Optional[time] = None,
        duration_minutes: int = 60,
    ) -> Dict[str, List[date]]:
        """
        Check availability for weekend (Saturday OR Sunday).

        Instructor passes if available on EITHER day.

        Returns:
            Dict mapping instructor_id to list of available weekend dates
        """
        results: Dict[str, List[date]] = {}

        for instructor_id in instructor_ids:
            available_dates = []

            # Check Saturday
            if self.check_availability_single_date(
                instructor_id, saturday, time_after, time_before, duration_minutes
            ):
                available_dates.append(saturday)

            # Check Sunday
            if self.check_availability_single_date(
                instructor_id, sunday, time_after, time_before, duration_minutes
            ):
                available_dates.append(sunday)

            if available_dates:
                results[instructor_id] = available_dates

        return results
