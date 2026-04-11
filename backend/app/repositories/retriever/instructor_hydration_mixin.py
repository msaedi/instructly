"""Instructor hydration queries for the retriever repository."""

from typing import Any, Dict, List

from sqlalchemy import text

from ._sql_helpers import _build_instructor_cards_sql, _map_instructor_card_row, _price_cte_query
from .mixin_base import RetrieverRepositoryMixinBase


class InstructorHydrationMixin(RetrieverRepositoryMixinBase):
    """Instructor and service hydration helpers for search results."""

    def get_services_by_ids(
        self,
        service_ids: List[str],
    ) -> List[Dict[str, Any]]:
        """
        Fetch full service data for a list of instructor service IDs.

        Useful when you need to reload service data after filtering.

        Args:
            service_ids: List of instructor_service IDs

        Returns:
            List of service data dicts
        """
        if not service_ids:
            return []

        query = text(
            _price_cte_query(
                """
            SELECT
                ins.id as instructor_service_id,
                sc.id as catalog_id,
                sc.name,
                sc.description,
                sps.min_hourly_rate,
                CASE WHEN sps.has_student_location = 1 THEN true ELSE false END AS offers_travel,
                CASE WHEN sps.has_instructor_location = 1 THEN true ELSE false END AS offers_at_location,
                CASE WHEN sps.has_online = 1 THEN true ELSE false END AS offers_online,
                ip.user_id as instructor_id,
                ins.duration_options,
                ins.filter_selections,
                ins.age_groups,
                ss.name as subcategory_name,
                scat.name as category_name
            FROM instructor_services ins
            JOIN service_catalog sc ON sc.id = ins.service_catalog_id
            JOIN service_price_summary sps ON sps.service_id = ins.id
            JOIN service_subcategories ss ON ss.id = sc.subcategory_id
            JOIN service_categories scat ON scat.id = ss.category_id
            JOIN instructor_profiles ip ON ip.id = ins.instructor_profile_id
            WHERE ins.id = ANY(:ids)
                AND ins.is_active = true
                AND sc.is_active = true
                AND ip.is_live = true
                AND ip.bgc_status = 'passed'
        """,
                full=True,
            )
        )

        result = self.db.execute(query, {"ids": service_ids})

        return [
            {
                "id": str(row.instructor_service_id),
                "catalog_id": str(row.catalog_id),
                "name": row.name,
                "description": row.description,
                "min_hourly_rate": float(row.min_hourly_rate),
                "price_per_hour": float(row.min_hourly_rate),
                "offers_travel": row.offers_travel,
                "offers_at_location": row.offers_at_location,
                "offers_online": row.offers_online,
                "instructor_id": str(row.instructor_id),
                "duration_options": row.duration_options,
                "filter_selections": row.filter_selections
                if isinstance(row.filter_selections, dict)
                else {},
                "age_groups": row.age_groups,
                "subcategory_name": row.subcategory_name,
                "category_name": row.category_name,
            }
            for row in result
        ]

    def get_instructor_summaries(self, instructor_ids: List[str]) -> List[Dict[str, Any]]:
        """
        Fetch instructor summary data for a list of instructor (user) IDs.

        Returns:
            List of dicts with keys:
              - instructor_id (users.id)
              - first_name
              - last_initial
              - bio_snippet
              - years_experience
              - profile_picture_key
              - verified
        """
        if not instructor_ids:
            return []

        query = text(
            """
            SELECT
                ip.user_id as instructor_id,
                u.first_name,
                CASE WHEN COALESCE(u.last_name, '') = '' THEN '' ELSE LEFT(u.last_name, 1) || '.' END as last_initial,
                LEFT(ip.bio, 150) as bio_snippet,
                ip.years_experience,
                u.profile_picture_key,
                (ip.identity_verified_at IS NOT NULL) as verified
            FROM instructor_profiles ip
            JOIN users u ON u.id = ip.user_id
            WHERE ip.user_id = ANY(:instructor_ids)
              AND ip.is_live = true
              AND ip.bgc_status = 'passed'
        """
        )

        result = self.db.execute(query, {"instructor_ids": instructor_ids})

        return [
            {
                "instructor_id": str(row.instructor_id),
                "first_name": row.first_name,
                "last_initial": row.last_initial,
                "bio_snippet": row.bio_snippet,
                "years_experience": int(row.years_experience)
                if row.years_experience is not None
                else None,
                "profile_picture_key": row.profile_picture_key,
                "verified": bool(row.verified),
            }
            for row in result
        ]

    def get_instructor_ratings(self, instructor_ids: List[str]) -> List[Dict[str, Any]]:
        """
        Fetch aggregated instructor ratings for a list of instructor (user) IDs.

        Reviews are filtered to published only.

        Returns:
            List of dicts with keys:
              - instructor_id
              - avg_rating
              - review_count
        """
        if not instructor_ids:
            return []

        query = text(
            """
            SELECT
                r.instructor_id,
                AVG(r.rating)::float as avg_rating,
                COUNT(*)::int as review_count
            FROM reviews r
            WHERE r.instructor_id = ANY(:instructor_ids)
              AND r.status = 'published'
            GROUP BY r.instructor_id
        """
        )

        result = self.db.execute(query, {"instructor_ids": instructor_ids})

        return [
            {
                "instructor_id": str(row.instructor_id),
                "avg_rating": float(row.avg_rating) if row.avg_rating is not None else None,
                "review_count": int(row.review_count or 0),
            }
            for row in result
        ]

    def get_instructor_coverage_areas(self, instructor_ids: List[str]) -> List[Dict[str, Any]]:
        """
        Fetch coverage area names for a list of instructor (user) IDs.

        Uses instructor_service_areas.neighborhood_id → region_boundaries.id and
        returns display-friendly region labels.

        Returns:
            List of dicts with keys:
              - instructor_id
              - coverage_areas (list[str])
        """
        if not instructor_ids:
            return []

        query = text(
            """
            SELECT
                isa.instructor_id,
                array_agg(
                    DISTINCT COALESCE(rb.display_name, rb.region_name)
                    ORDER BY COALESCE(rb.display_name, rb.region_name)
                ) as coverage_areas
            FROM instructor_service_areas isa
            JOIN region_boundaries rb ON rb.id = isa.neighborhood_id
            WHERE isa.instructor_id = ANY(:instructor_ids)
              AND isa.is_active = true
            GROUP BY isa.instructor_id
        """
        )

        result = self.db.execute(query, {"instructor_ids": instructor_ids})

        return [
            {
                "instructor_id": str(row.instructor_id),
                "coverage_areas": list(row.coverage_areas) if row.coverage_areas else [],
            }
            for row in result
        ]

    def get_instructor_cards(self, instructor_ids: List[str]) -> List[Dict[str, Any]]:
        """
        Fetch instructor "card" data for the search response in one query.

        Combines:
        - instructor profile + user fields (name, photo, bio, verified)
        - aggregated ratings (avg + count)
        - coverage area names
        """
        if not instructor_ids:
            return []

        query = text(_build_instructor_cards_sql())
        result = self.db.execute(query, {"instructor_ids": instructor_ids})
        return [_map_instructor_card_row(row) for row in result]
