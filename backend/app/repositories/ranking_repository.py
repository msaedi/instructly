# backend/app/repositories/ranking_repository.py
"""
Repository for ranking-related database queries.
Fetches instructor metrics needed for scoring.

Adapted to actual InstaInstru schema:
- Reviews aggregated from reviews table (not stored on instructor_profiles)
- Photo presence checked via users.profile_picture_key
- Background check status via instructor_profiles.bgc_status
- Service audience/skills via instructor_services.age_groups and filter_selections.skill_level
"""
from __future__ import annotations

import json
import os
import threading
import time
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..models.service_catalog import InstructorService

_GLOBAL_AVG_RATING_TTL_S = int(os.getenv("NL_SEARCH_GLOBAL_AVG_RATING_TTL_S", "600"))
_GLOBAL_AVG_RATING_CACHE: Optional[float] = None
_GLOBAL_AVG_RATING_CACHED_AT: float = 0.0
_GLOBAL_AVG_RATING_LOCK = threading.Lock()


class RankingRepository:
    """
    Repository for fetching instructor ranking signals.

    Queries multiple tables to gather metrics for ranking:
    - users: profile picture presence
    - instructor_profiles: bio, last_active_at, response_rate, bgc_status, identity_verified_at
    - reviews: aggregated ratings and review counts
    - instructor_services: age_groups, filter_selections.skill_level
    - instructor_service_areas + region_boundaries: distance calculations
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_instructor_metrics(
        self,
        instructor_ids: List[str],
    ) -> Dict[str, Dict[str, Any]]:
        """
        Fetch ranking metrics for multiple instructors.

        Returns dict mapping instructor_id to:
        - avg_rating: float (1-5) - aggregated from reviews
        - review_count: int - count of published reviews
        - last_active_at: datetime
        - response_rate: float (0-1)
        - has_photo: bool
        - has_bio: bool
        - has_background_check: bool
        - has_identity_verified: bool
        - profile_completeness: float (0-1)
        """
        if not instructor_ids:
            return {}

        # Query with LEFT JOIN to reviews for aggregation
        query = text(
            """
            SELECT
                ip.user_id as instructor_id,
                ip.last_active_at,
                ip.response_rate,
                ip.profile_completeness,
                ip.is_founding_instructor,
                -- Photo check from users table
                u.profile_picture_key IS NOT NULL as has_photo,
                -- Bio check (>= 100 chars)
                LENGTH(COALESCE(ip.bio, '')) >= 100 as has_bio,
                -- Background check passed
                ip.bgc_status = 'passed' as has_background_check,
                -- Identity verified
                ip.identity_verified_at IS NOT NULL as has_identity_verified,
                -- Aggregated review stats
                COALESCE(rs.avg_rating, 0) as avg_rating,
                COALESCE(rs.review_count, 0) as review_count
            FROM instructor_profiles ip
            JOIN users u ON u.id = ip.user_id
            LEFT JOIN (
                SELECT
                    instructor_id,
                    AVG(rating)::float as avg_rating,
                    COUNT(*) as review_count
                FROM reviews
                WHERE status = 'published'
                  AND instructor_id = ANY(:instructor_ids)
                GROUP BY instructor_id
            ) rs ON rs.instructor_id = ip.user_id
            WHERE ip.user_id = ANY(:instructor_ids)
        """
        )

        result = self.db.execute(query, {"instructor_ids": instructor_ids})

        metrics: Dict[str, Dict[str, Any]] = {}
        for row in result:
            metrics[row.instructor_id] = {
                "avg_rating": float(row.avg_rating) if row.avg_rating else 0.0,
                "review_count": int(row.review_count) if row.review_count else 0,
                "last_active_at": row.last_active_at,
                "response_rate": float(row.response_rate) if row.response_rate else 0.0,
                "is_founding_instructor": bool(row.is_founding_instructor),
                "has_photo": bool(row.has_photo),
                "has_bio": bool(row.has_bio),
                "has_background_check": bool(row.has_background_check),
                "has_identity_verified": bool(row.has_identity_verified),
                "profile_completeness": float(row.profile_completeness)
                if row.profile_completeness
                else 0.0,
            }

        return metrics

    def get_global_average_rating(self) -> float:
        """
        Get global average rating across all instructors.
        Used for Bayesian averaging.

        Returns:
            Global average rating (default 4.2 if no reviews exist)
        """
        query = text(
            """
            SELECT AVG(rating)::float as global_avg
            FROM reviews
            WHERE status = 'published'
        """
        )

        global _GLOBAL_AVG_RATING_CACHE, _GLOBAL_AVG_RATING_CACHED_AT

        ttl_s = _GLOBAL_AVG_RATING_TTL_S
        if ttl_s > 0:
            now = time.monotonic()
            cached = _GLOBAL_AVG_RATING_CACHE
            if cached is not None and (now - _GLOBAL_AVG_RATING_CACHED_AT) < ttl_s:
                return cached

            with _GLOBAL_AVG_RATING_LOCK:
                now = time.monotonic()
                cached = _GLOBAL_AVG_RATING_CACHE
                if cached is not None and (now - _GLOBAL_AVG_RATING_CACHED_AT) < ttl_s:
                    return cached

                result = self.db.execute(query).first()
                avg = float(result.global_avg) if result and result.global_avg else 4.2
                _GLOBAL_AVG_RATING_CACHE = avg
                _GLOBAL_AVG_RATING_CACHED_AT = now
                return avg

        result = self.db.execute(query).first()
        return float(result.global_avg) if result and result.global_avg else 4.2

    def get_service_audience(
        self,
        service_ids: List[str],
    ) -> Dict[str, str]:
        """
        Get audience type for services based on age_groups.

        Maps age_groups array to audience categories:
        - Only children age groups → "kids"
        - Only adult age groups → "adults"
        - Mixed or all age groups → "both"

        Returns dict mapping service_id to audience ("kids", "adults", "both").
        """
        if not service_ids:
            return {}

        query = text(
            """
            SELECT
                id as service_id,
                COALESCE(age_groups, ARRAY[]::text[]) as age_groups
            FROM instructor_services
            WHERE id = ANY(:service_ids)
        """
        )

        result = self.db.execute(query, {"service_ids": service_ids})

        audiences: Dict[str, str] = {}
        for row in result:
            age_groups = list(row.age_groups) if row.age_groups else []
            audiences[row.service_id] = self._classify_audience(age_groups)

        return audiences

    def _classify_audience(self, age_groups: List[str]) -> str:
        """
        Classify age groups into audience category.

        Child-related: 'children', 'kids', 'teens', 'youth', 'preschool', 'elementary'
        Adult-related: 'adults', 'seniors', 'college'
        """
        if not age_groups:
            return "both"

        child_terms = {"children", "kids", "teens", "youth", "preschool", "elementary"}
        adult_terms = {"adults", "seniors", "college"}

        age_set = {ag.lower() for ag in age_groups}

        has_child = bool(age_set & child_terms)
        has_adult = bool(age_set & adult_terms)

        if has_child and not has_adult:
            return "kids"
        elif has_adult and not has_child:
            return "adults"
        else:
            return "both"

    def get_service_skill_levels(
        self,
        service_ids: List[str],
    ) -> Dict[str, List[str]]:
        """
        Get skill levels for services from filter_selections.skill_level.

        Returns dict mapping service_id to list of skill levels.
        Empty or null defaults to ["all"].
        """
        if not service_ids:
            return {}

        skills: Dict[str, List[str]] = {}
        rows = (
            self.db.query(InstructorService.id, InstructorService.filter_selections)
            .filter(InstructorService.id.in_(service_ids))
            .all()
        )
        for service_id, filter_selections in rows:
            skill_levels: List[str] = []
            selections: Dict[str, Any] = {}
            if isinstance(filter_selections, dict):
                selections = filter_selections
            elif isinstance(filter_selections, str):
                try:
                    decoded = json.loads(filter_selections)
                    if isinstance(decoded, dict):
                        selections = decoded
                except Exception:
                    selections = {}

            if selections:
                raw_levels = selections.get("skill_level", [])
                if isinstance(raw_levels, list):
                    skill_levels = [
                        str(level).strip().lower() for level in raw_levels if str(level).strip()
                    ]
            skills[str(service_id)] = skill_levels or ["all"]

        return skills

    def get_instructor_distances(
        self,
        instructor_ids: List[str],
        user_lng: float,
        user_lat: float,
    ) -> Dict[str, float]:
        """
        Get distance from user to each instructor's service area.

        Uses PostGIS to calculate minimum distance from user point
        to instructor service area polygons (via region_boundaries).

        Returns dict mapping instructor_id to distance in km.
        """
        if not instructor_ids:
            return {}

        query = text(
            """
            WITH user_point AS (
                SELECT ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography as geom
            )
            SELECT
                isa.instructor_id,
                MIN(ST_Distance(rb.boundary::geography, up.geom) / 1000.0) as distance_km
            FROM instructor_service_areas isa
            JOIN region_boundaries rb ON rb.id = isa.neighborhood_id
            CROSS JOIN user_point up
            WHERE isa.instructor_id = ANY(:instructor_ids)
              AND isa.is_active = true
            GROUP BY isa.instructor_id
        """
        )

        result = self.db.execute(
            query,
            {
                "instructor_ids": instructor_ids,
                "lng": user_lng,
                "lat": user_lat,
            },
        )

        distances: Dict[str, float] = {}
        for row in result:
            distances[row.instructor_id] = float(row.distance_km)

        return distances

    def get_instructor_tenure_date(
        self,
        instructor_ids: List[str],
    ) -> Dict[str, Optional[Any]]:
        """
        Get the date each instructor joined (for tie-breaking).

        Uses users.created_at as the tenure start date.

        Returns dict mapping instructor_id to created_at datetime.
        """
        if not instructor_ids:
            return {}

        query = text(
            """
            SELECT id as instructor_id, created_at
            FROM users
            WHERE id = ANY(:instructor_ids)
        """
        )

        result = self.db.execute(query, {"instructor_ids": instructor_ids})

        tenure: Dict[str, Optional[Any]] = {}
        for row in result:
            tenure[row.instructor_id] = row.created_at

        return tenure
