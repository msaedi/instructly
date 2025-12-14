# backend/app/repositories/filter_repository.py
"""
Repository for filter-related database queries.
Handles PostGIS location checks and availability validation.

Adapted to actual InstaInstru schema:
- instructor_service_areas + region_boundaries: Service area polygons
- availability_days + check_availability function: Bitmap availability
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Dict, List, Optional

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
    def filter_by_region_coverage(
        self, instructor_ids: List[str], region_boundary_id: str
    ) -> List[str]:
        """Return instructor IDs that cover the given region boundary."""
        if not instructor_ids:
            return []

        query = text(
            """
            SELECT DISTINCT isa.instructor_id
            FROM instructor_service_areas isa
            WHERE isa.instructor_id = ANY(:instructor_ids)
              AND isa.is_active = true
              AND isa.neighborhood_id = :region_id
            """
        )
        rows = self.db.execute(
            query,
            {"instructor_ids": instructor_ids, "region_id": region_boundary_id},
        ).fetchall()
        return [row[0] for row in rows]

    def filter_by_any_region_coverage(
        self, instructor_ids: List[str], region_boundary_ids: List[str]
    ) -> List[str]:
        """Return instructor IDs that cover any of the given region boundaries."""
        if not instructor_ids or not region_boundary_ids:
            return []

        query = text(
            """
            SELECT DISTINCT isa.instructor_id
            FROM instructor_service_areas isa
            WHERE isa.instructor_id = ANY(:instructor_ids)
              AND isa.is_active = true
              AND isa.neighborhood_id = ANY(:region_ids)
            """
        )
        rows = self.db.execute(
            query,
            {"instructor_ids": instructor_ids, "region_ids": region_boundary_ids},
        ).fetchall()
        return [row[0] for row in rows]

    def get_instructor_min_distance_to_region(
        self, instructor_ids: List[str], region_boundary_id: str
    ) -> Dict[str, float]:
        """
        Get the minimum distance (meters) from a region centroid to each instructor's service areas.

        This is used for admin/debug display to sanity-check that results are geographically sensible.
        Returns a mapping of instructor_id -> distance_meters (float).

        Notes:
        - Requires Postgres + PostGIS; returns {} in non-Postgres environments.
        - Uses region_boundaries.centroid as the reference point and distances to each covered polygon.
        """
        if not instructor_ids or not region_boundary_id:
            return {}
        if self.db.bind is None or self.db.bind.dialect.name != "postgresql":
            return {}

        query = text(
            """
            WITH target AS (
                SELECT centroid::geography AS centroid_geo
                FROM region_boundaries
                WHERE id = :region_id
                  AND centroid IS NOT NULL
            )
            SELECT
                isa.instructor_id,
                MIN(ST_Distance(rb.boundary::geography, t.centroid_geo)) AS distance_m
            FROM instructor_service_areas isa
            JOIN region_boundaries rb ON rb.id = isa.neighborhood_id
            CROSS JOIN target t
            WHERE isa.instructor_id = ANY(:instructor_ids)
              AND isa.is_active = true
              AND rb.boundary IS NOT NULL
            GROUP BY isa.instructor_id
            """
        )

        rows = self.db.execute(
            query,
            {"instructor_ids": instructor_ids, "region_id": region_boundary_id},
        ).fetchall()

        out: Dict[str, float] = {}
        for row in rows:
            instructor_id = str(row[0])
            distance_m = row[1]
            if distance_m is None:
                continue
            out[instructor_id] = float(distance_m)
        return out

    def filter_by_parent_region(self, instructor_ids: List[str], parent_region: str) -> List[str]:
        """Return instructor IDs that cover any neighborhood in the given parent region (e.g., borough)."""
        if not instructor_ids:
            return []

        query = text(
            """
            SELECT DISTINCT isa.instructor_id
            FROM instructor_service_areas isa
            JOIN region_boundaries rb ON rb.id = isa.neighborhood_id
            WHERE isa.instructor_id = ANY(:instructor_ids)
              AND isa.is_active = true
              AND rb.parent_region IS NOT NULL
              AND LOWER(rb.parent_region) = LOWER(:parent_region)
            """
        )
        rows = self.db.execute(
            query,
            {"instructor_ids": instructor_ids, "parent_region": parent_region},
        ).fetchall()
        return [row[0] for row in rows]

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
        Filter instructors by availability using a single batched query.

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

        if target_date:
            dates_to_check = [target_date]
        else:
            # Check next 7 days using NYC timezone
            today = _get_today_nyc()
            dates_to_check = [today + timedelta(days=i) for i in range(7)]

        # Single batched query for all instructors and all dates
        query = text(
            """
            SELECT ad.instructor_id, ad.day_date
            FROM availability_days ad
            WHERE ad.instructor_id = ANY(:instructor_ids)
              AND ad.day_date = ANY(:dates)
              AND ad.bits IS NOT NULL
              AND check_availability(
                  ad.instructor_id,
                  ad.day_date,
                  :time_after,
                  :time_before,
                  :duration
              )
            ORDER BY ad.instructor_id, ad.day_date
        """
        )

        result = self.db.execute(
            query,
            {
                "instructor_ids": instructor_ids,
                "dates": dates_to_check,
                "time_after": time_after,
                "time_before": time_before,
                "duration": duration_minutes,
            },
        )

        # Group results by instructor
        results: Dict[str, List[date]] = {}
        for row in result:
            instructor_id = row.instructor_id
            day_date = row.day_date
            if instructor_id not in results:
                results[instructor_id] = []
            results[instructor_id].append(day_date)

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
        Check availability for weekend (Saturday OR Sunday) using batched query.

        Instructor passes if available on EITHER day.

        Returns:
            Dict mapping instructor_id to list of available weekend dates
        """
        if not instructor_ids:
            return {}

        # Use single batched query for both weekend days
        query = text(
            """
            SELECT ad.instructor_id, ad.day_date
            FROM availability_days ad
            WHERE ad.instructor_id = ANY(:instructor_ids)
              AND ad.day_date = ANY(:dates)
              AND ad.bits IS NOT NULL
              AND check_availability(
                  ad.instructor_id,
                  ad.day_date,
                  :time_after,
                  :time_before,
                  :duration
              )
            ORDER BY ad.instructor_id, ad.day_date
        """
        )

        result = self.db.execute(
            query,
            {
                "instructor_ids": instructor_ids,
                "dates": [saturday, sunday],
                "time_after": time_after,
                "time_before": time_before,
                "duration": duration_minutes,
            },
        )

        # Group results by instructor
        results: Dict[str, List[date]] = {}
        for row in result:
            instructor_id = row.instructor_id
            day_date = row.day_date
            if instructor_id not in results:
                results[instructor_id] = []
            results[instructor_id].append(day_date)

        return results
