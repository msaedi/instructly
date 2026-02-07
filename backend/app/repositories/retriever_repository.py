# backend/app/repositories/retriever_repository.py
"""
Repository for candidate retrieval queries.
Separates raw SQL from business logic per repository pattern.

Note: Queries join service_catalog (for embedding/name) with instructor_services
(for price/instructor) since searchable metadata is on catalog, but bookable
services are instructor offerings.
"""
from typing import Any, Dict, List

from sqlalchemy import text
from sqlalchemy.orm import Session


class RetrieverRepository:
    """
    Repository for search retrieval queries.

    Handles the raw SQL for vector and text search.
    Joins service_catalog with instructor_services to get bookable results.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def vector_search(
        self,
        embedding: List[float],
        limit: int = 30,
    ) -> List[Dict[str, Any]]:
        """
        Execute pgvector similarity search.

        Joins with instructor_services to get bookable services with pricing.
        Returns list of dicts with service data and vector_score.

        Args:
            embedding: Query embedding vector (1536 dimensions)
            limit: Maximum results to return

        Returns:
            List of service candidates with scores
        """
        embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"

        query = text(
            """
            SELECT
                ins.id as instructor_service_id,
                sc.id as catalog_id,
                sc.name,
                sc.description,
                ins.hourly_rate as price_per_hour,
                ip.user_id as instructor_id,
                ss.name as subcategory_name,
                scat.name as category_name,
                -- Normalize cosine distance to similarity score (0-1)
                -- pgvector <=> returns cosine distance [0, 2] (1 - cosine_similarity),
                -- so 1 - distance yields similarity [0, 1] for the common case (clamped at 0).
                -- Use CAST() instead of :: to avoid SQLAlchemy parameter binding conflict.
                GREATEST(0, 1 - (sc.embedding_v2 <=> CAST(:embedding AS vector))) as vector_score
            FROM service_catalog sc
            JOIN service_subcategories ss ON ss.id = sc.subcategory_id
            JOIN service_categories scat ON scat.id = ss.category_id
            JOIN instructor_services ins ON ins.service_catalog_id = sc.id
            JOIN instructor_profiles ip ON ip.id = ins.instructor_profile_id
            WHERE sc.is_active = true
                AND ins.is_active = true
                AND sc.embedding_v2 IS NOT NULL
                AND ip.is_live = true
                AND ip.bgc_status = 'passed'
            ORDER BY sc.embedding_v2 <=> CAST(:embedding AS vector)
            LIMIT :limit
        """
        )

        result = self.db.execute(
            query,
            {
                "embedding": embedding_str,
                "limit": limit,
            },
        )

        return [
            {
                "id": row.instructor_service_id,
                "catalog_id": row.catalog_id,
                "name": row.name,
                "description": row.description,
                "price_per_hour": int(row.price_per_hour),
                "instructor_id": row.instructor_id,
                "subcategory_name": row.subcategory_name,
                "category_name": row.category_name,
                "vector_score": float(row.vector_score),
            }
            for row in result
        ]

    def text_search(
        self,
        corrected_query: str,
        original_query: str,
        limit: int = 30,
    ) -> List[Dict[str, Any]]:
        """
        Execute pg_trgm trigram similarity search.

        Searches both corrected and original query for robustness.
        Joins with instructor_services to get bookable services with pricing.

        Args:
            corrected_query: Typo-corrected query text
            original_query: Original user query
            limit: Maximum results to return

        Returns:
            List of service candidates with scores
        """
        query = text(
            """
            SELECT
                ins.id as instructor_service_id,
                sc.id as catalog_id,
                sc.name,
                sc.description,
                ins.hourly_rate as price_per_hour,
                ip.user_id as instructor_id,
                ss.name as subcategory_name,
                scat.name as category_name,
                GREATEST(
                    similarity(sc.name, :corrected_query),
                    similarity(sc.name, :original_query),
                    similarity(COALESCE(sc.description, ''), :corrected_query) * 0.8
                ) as text_score
            FROM service_catalog sc
            JOIN service_subcategories ss ON ss.id = sc.subcategory_id
            JOIN service_categories scat ON scat.id = ss.category_id
            JOIN instructor_services ins ON ins.service_catalog_id = sc.id
            JOIN instructor_profiles ip ON ip.id = ins.instructor_profile_id
            WHERE sc.is_active = true
                AND ins.is_active = true
                AND ip.is_live = true
                AND ip.bgc_status = 'passed'
                AND (
                    sc.name % :corrected_query
                    OR sc.name % :original_query
                    OR (sc.description IS NOT NULL AND sc.description % :corrected_query)
                )
            ORDER BY text_score DESC
            LIMIT :limit
        """
        )

        result = self.db.execute(
            query,
            {
                "corrected_query": corrected_query,
                "original_query": original_query,
                "limit": limit,
            },
        )

        return [
            {
                "id": row.instructor_service_id,
                "catalog_id": row.catalog_id,
                "name": row.name,
                "description": row.description,
                "price_per_hour": int(row.price_per_hour),
                "instructor_id": row.instructor_id,
                "subcategory_name": row.subcategory_name,
                "category_name": row.category_name,
                "text_score": float(row.text_score),
            }
            for row in result
        ]

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
            """
            SELECT
                ins.id as instructor_service_id,
                sc.id as catalog_id,
                sc.name,
                sc.description,
                ins.hourly_rate as price_per_hour,
                ins.offers_travel,
                ins.offers_at_location,
                ins.offers_online,
                ip.user_id as instructor_id,
                ins.duration_options,
                ins.levels_taught,
                ins.age_groups,
                ss.name as subcategory_name,
                scat.name as category_name
            FROM instructor_services ins
            JOIN service_catalog sc ON sc.id = ins.service_catalog_id
            JOIN service_subcategories ss ON ss.id = sc.subcategory_id
            JOIN service_categories scat ON scat.id = ss.category_id
            JOIN instructor_profiles ip ON ip.id = ins.instructor_profile_id
            WHERE ins.id = ANY(:ids)
                AND ins.is_active = true
                AND sc.is_active = true
                AND ip.is_live = true
                AND ip.bgc_status = 'passed'
        """
        )

        result = self.db.execute(query, {"ids": service_ids})

        return [
            {
                "id": str(row.instructor_service_id),
                "catalog_id": str(row.catalog_id),
                "name": row.name,
                "description": row.description,
                "price_per_hour": int(row.price_per_hour),
                "offers_travel": row.offers_travel,
                "offers_at_location": row.offers_at_location,
                "offers_online": row.offers_online,
                "instructor_id": str(row.instructor_id),
                "duration_options": row.duration_options,
                "levels_taught": row.levels_taught,
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
                COALESCE(LEFT(u.last_name, 1), '') as last_initial,
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
        returns region_boundaries.region_name values.

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
                array_agg(DISTINCT rb.region_name ORDER BY rb.region_name) as coverage_areas
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

        query = text(
            """
            SELECT
                ip.user_id as instructor_id,
                u.first_name,
                COALESCE(LEFT(u.last_name, 1), '') as last_initial,
                LEFT(ip.bio, 150) as bio_snippet,
                ip.years_experience,
                u.profile_picture_key,
                (ip.identity_verified_at IS NOT NULL) as verified,
                ip.is_founding_instructor,
                rs.avg_rating,
                COALESCE(rs.review_count, 0) as review_count,
                COALESCE(c.coverage_areas, ARRAY[]::text[]) as coverage_areas,
                COALESCE(tl.teaching_locations, '[]'::jsonb) as teaching_locations
            FROM instructor_profiles ip
            JOIN users u ON u.id = ip.user_id
            LEFT JOIN (
                SELECT
                    r.instructor_id,
                    AVG(r.rating)::float as avg_rating,
                    COUNT(*)::int as review_count
                FROM reviews r
                WHERE r.instructor_id = ANY(:instructor_ids)
                  AND r.status = 'published'
                GROUP BY r.instructor_id
            ) rs ON rs.instructor_id = ip.user_id
            LEFT JOIN (
                SELECT
                    isa.instructor_id,
                    array_agg(DISTINCT rb.region_name ORDER BY rb.region_name) as coverage_areas
                FROM instructor_service_areas isa
                JOIN region_boundaries rb ON rb.id = isa.neighborhood_id
                WHERE isa.instructor_id = ANY(:instructor_ids)
                  AND isa.is_active = true
                GROUP BY isa.instructor_id
            ) c ON c.instructor_id = ip.user_id
            LEFT JOIN (
                SELECT
                    ipp.instructor_id,
                    jsonb_agg(
                        jsonb_build_object(
                            'approx_lat', ipp.approx_lat,
                            'approx_lng', ipp.approx_lng,
                            'neighborhood', ipp.neighborhood
                        )
                        ORDER BY ipp.position
                    ) FILTER (WHERE ipp.approx_lat IS NOT NULL AND ipp.approx_lng IS NOT NULL) as teaching_locations
                FROM instructor_preferred_places ipp
                WHERE ipp.instructor_id = ANY(:instructor_ids)
                  AND ipp.kind = 'teaching_location'
                GROUP BY ipp.instructor_id
            ) tl ON tl.instructor_id = ip.user_id
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
                "is_founding_instructor": bool(row.is_founding_instructor),
                "avg_rating": float(row.avg_rating) if row.avg_rating is not None else None,
                "review_count": int(row.review_count or 0),
                "coverage_areas": list(row.coverage_areas) if row.coverage_areas else [],
                "teaching_locations": list(row.teaching_locations)
                if row.teaching_locations
                else [],
            }
            for row in result
        ]

    def count_embeddings(self) -> int:
        """
        Count services with embeddings populated.

        Used to check if vector search will work before attempting it.
        Returns 0 if no embeddings exist, indicating text-only fallback needed.

        Returns:
            Number of active services with embedding_v2 populated
        """
        result = self.db.execute(
            text(
                """
                SELECT COUNT(*)
                FROM service_catalog
                WHERE embedding_v2 IS NOT NULL AND is_active = true
            """
            )
        )
        return result.scalar() or 0

    def has_embeddings(self) -> bool:
        """
        Return True if any active services have embeddings populated.

        This is a cheaper alternative to count_embeddings() for request-time checks.
        """
        result = self.db.execute(
            text(
                """
                SELECT EXISTS(
                    SELECT 1
                    FROM service_catalog
                    WHERE embedding_v2 IS NOT NULL AND is_active = true
                    LIMIT 1
                ) as has_embeddings
            """
            )
        ).first()
        return bool(result.has_embeddings) if result else False

    def search_with_instructor_data(
        self,
        embedding: List[float],
        limit: int = 20,
        max_price: int | None = None,
    ) -> List[Dict[str, Any]]:
        """
        Search services and return instructor-grouped results with all embedded data.

        This method returns instructor-level results (one row per instructor) with:
        - Instructor profile info (first_name, last_initial, bio, verified, etc.)
        - Aggregated ratings (average, count)
        - Coverage areas (list of region names)
        - All matching services with relevance scores

        This eliminates N+1 queries by embedding all data the frontend needs.

        Args:
            embedding: Query embedding vector (1536 dimensions)
            limit: Maximum instructors to return
            max_price: Optional hard max hourly rate filter (applied at service level)

        Returns:
            List of instructor data dicts with embedded profile, ratings, services
        """
        embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"

        query = text(
            """
            WITH matched_services AS (
                -- Step 1: Vector search to find matching services
                SELECT
                    ins.id as service_id,
                    sc.id as service_catalog_id,
                    sc.name as service_name,
                    sc.description as service_description,
                    ins.hourly_rate as price_per_hour,
                    ip.user_id as instructor_id,
                    ip.id as profile_id,
                    ss.name as subcategory_name,
                    scat.name as category_name,
                    -- Normalize cosine distance to similarity score (0-1)
                    GREATEST(0, 1 - ((sc.embedding_v2 <=> CAST(:embedding AS vector)) / 2)) as relevance_score
                FROM instructor_services ins
                JOIN service_catalog sc ON sc.id = ins.service_catalog_id
                JOIN service_subcategories ss ON ss.id = sc.subcategory_id
                JOIN service_categories scat ON scat.id = ss.category_id
                JOIN instructor_profiles ip ON ip.id = ins.instructor_profile_id
                WHERE sc.is_active = true
                    AND ins.is_active = true
                    AND sc.embedding_v2 IS NOT NULL
                    AND ip.is_live = true
                    AND ip.bgc_status = 'passed'
                    AND (:max_price IS NULL OR ins.hourly_rate <= :max_price)
                ORDER BY sc.embedding_v2 <=> CAST(:embedding AS vector)
                LIMIT :search_limit
            ),

            -- Step 2: Group by instructor, aggregate services
            instructor_matches AS (
                SELECT
                    instructor_id,
                    profile_id,
                    json_agg(
                        json_build_object(
                            'service_id', service_id,
                            'service_catalog_id', service_catalog_id,
                            'name', service_name,
                            'description', service_description,
                            'price_per_hour', price_per_hour,
                            'subcategory_name', subcategory_name,
                            'category_name', category_name,
                            'relevance_score', relevance_score
                        ) ORDER BY relevance_score DESC
                    ) as matching_services,
                    MAX(relevance_score) as best_score,
                    COUNT(*) as match_count
                FROM matched_services
                GROUP BY instructor_id, profile_id
            ),

            -- Step 3: Get instructor profile data
            instructor_data AS (
                SELECT
                    im.*,
                    u.first_name,
                    COALESCE(LEFT(u.last_name, 1), '') as last_initial,
                    ip.bio,
                    ip.years_experience,
                    u.profile_picture_key,
                    (ip.identity_verified_at IS NOT NULL) as verified,
                    ip.is_founding_instructor
                FROM instructor_matches im
                JOIN instructor_profiles ip ON im.profile_id = ip.id
                JOIN users u ON ip.user_id = u.id
            ),

            -- Step 4: Get aggregated ratings
            ratings AS (
                SELECT
                    r.instructor_id,
                    AVG(r.rating)::float as avg_rating,
                    COUNT(*)::int as review_count
                FROM reviews r
                WHERE r.instructor_id IN (SELECT instructor_id FROM instructor_matches)
                  AND r.status = 'published'
                GROUP BY r.instructor_id
            ),

            -- Step 5: Get coverage areas
            coverage AS (
                SELECT
                    isa.instructor_id,
                    array_agg(DISTINCT rb.region_name ORDER BY rb.region_name) as areas
                FROM instructor_service_areas isa
                JOIN region_boundaries rb ON isa.neighborhood_id = rb.id
                WHERE isa.instructor_id IN (SELECT instructor_id FROM instructor_matches)
                GROUP BY isa.instructor_id
            )

            -- Final: Join everything together
            SELECT
                id.instructor_id,
                id.first_name,
                id.last_initial,
                LEFT(id.bio, 150) as bio_snippet,
                id.years_experience,
                id.profile_picture_key,
                id.verified,
                id.is_founding_instructor,
                id.matching_services,
                id.best_score,
                id.match_count,
                COALESCE(r.avg_rating, null) as avg_rating,
                COALESCE(r.review_count, 0) as review_count,
                COALESCE(c.areas, ARRAY[]::text[]) as coverage_areas
            FROM instructor_data id
            LEFT JOIN ratings r ON id.instructor_id = r.instructor_id
            LEFT JOIN coverage c ON c.instructor_id = id.instructor_id
            ORDER BY id.best_score DESC
            LIMIT :limit
        """
        )

        result = self.db.execute(
            query,
            {
                "embedding": embedding_str,
                "search_limit": limit * 5,  # Fetch more services initially, then group
                "limit": limit,
                "max_price": max_price,
            },
        )

        return [
            {
                "instructor_id": row.instructor_id,
                "first_name": row.first_name,
                "last_initial": row.last_initial,
                "bio_snippet": row.bio_snippet,
                "years_experience": row.years_experience,
                "profile_picture_key": row.profile_picture_key,
                "verified": row.verified,
                "is_founding_instructor": bool(row.is_founding_instructor),
                "matching_services": row.matching_services,
                "best_score": float(row.best_score),
                "match_count": int(row.match_count),
                "avg_rating": float(row.avg_rating) if row.avg_rating else None,
                "review_count": int(row.review_count),
                "coverage_areas": list(row.coverage_areas) if row.coverage_areas else [],
            }
            for row in result
        ]

    def search_text_only(
        self,
        corrected_query: str,
        original_query: str,
        limit: int = 20,
        max_price: int | None = None,
    ) -> List[Dict[str, Any]]:
        """
        Text-only fallback search using pg_trgm trigram matching.

        Used when the embedding service is unavailable (OpenAI outage, circuit open, etc).

        Returns instructor-grouped results with embedded data, matching the shape of
        search_with_instructor_data().

        Args:
            corrected_query: Typo-corrected query text (typically parsed service_query)
            original_query: Original query text for robustness
            limit: Maximum instructors to return
            max_price: Optional hard max hourly rate filter (applied at service level)

        Returns:
            List of instructor data dicts with embedded profile, ratings, services
        """
        query = text(
            """
            WITH matched_services AS (
                SELECT
                    ins.id as service_id,
                    sc.id as service_catalog_id,
                    sc.name as service_name,
                    sc.description as service_description,
                    ins.hourly_rate as price_per_hour,
                    ip.user_id as instructor_id,
                    ip.id as profile_id,
                    ss.name as subcategory_name,
                    scat.name as category_name,
                    GREATEST(
                        similarity(sc.name, :corrected_query),
                        similarity(sc.name, :original_query),
                        similarity(COALESCE(sc.description, ''), :corrected_query) * 0.8
                    ) as relevance_score
                FROM instructor_services ins
                JOIN service_catalog sc ON sc.id = ins.service_catalog_id
                JOIN service_subcategories ss ON ss.id = sc.subcategory_id
                JOIN service_categories scat ON scat.id = ss.category_id
                JOIN instructor_profiles ip ON ip.id = ins.instructor_profile_id
                WHERE sc.is_active = true
                  AND ins.is_active = true
                  AND ip.is_live = true
                  AND ip.bgc_status = 'passed'
                  AND (:max_price IS NULL OR ins.hourly_rate <= :max_price)
                  AND (
                        sc.name % :corrected_query
                        OR sc.name % :original_query
                        OR COALESCE(sc.description, '') % :corrected_query
                  )
                ORDER BY relevance_score DESC
                LIMIT :search_limit
            ),

            instructor_matches AS (
                SELECT
                    instructor_id,
                    profile_id,
                    json_agg(
                        json_build_object(
                            'service_id', service_id,
                            'service_catalog_id', service_catalog_id,
                            'name', service_name,
                            'description', service_description,
                            'price_per_hour', price_per_hour,
                            'subcategory_name', subcategory_name,
                            'category_name', category_name,
                            'relevance_score', relevance_score
                        ) ORDER BY relevance_score DESC
                    ) as matching_services,
                    MAX(relevance_score) as best_score,
                    COUNT(*) as match_count
                FROM matched_services
                GROUP BY instructor_id, profile_id
            ),

            instructor_data AS (
                SELECT
                    im.*,
                    u.first_name,
                    COALESCE(LEFT(u.last_name, 1), '') as last_initial,
                    ip.bio,
                    ip.years_experience,
                    u.profile_picture_key,
                    (ip.identity_verified_at IS NOT NULL) as verified
                FROM instructor_matches im
                JOIN instructor_profiles ip ON im.profile_id = ip.id
                JOIN users u ON ip.user_id = u.id
            ),

            ratings AS (
                SELECT
                    r.instructor_id,
                    AVG(r.rating)::float as avg_rating,
                    COUNT(*)::int as review_count
                FROM reviews r
                WHERE r.instructor_id IN (SELECT instructor_id FROM instructor_matches)
                  AND r.status = 'published'
                GROUP BY r.instructor_id
            ),

            coverage AS (
                SELECT
                    isa.instructor_id,
                    array_agg(DISTINCT rb.region_name ORDER BY rb.region_name) as areas
                FROM instructor_service_areas isa
                JOIN region_boundaries rb ON isa.neighborhood_id = rb.id
                WHERE isa.instructor_id IN (SELECT instructor_id FROM instructor_matches)
                GROUP BY isa.instructor_id
            )

            SELECT
                id.instructor_id,
                id.first_name,
                id.last_initial,
                LEFT(id.bio, 150) as bio_snippet,
                id.years_experience,
                id.profile_picture_key,
                id.verified,
                id.matching_services,
                id.best_score,
                id.match_count,
                COALESCE(r.avg_rating, null) as avg_rating,
                COALESCE(r.review_count, 0) as review_count,
                COALESCE(c.areas, ARRAY[]::text[]) as coverage_areas
            FROM instructor_data id
            LEFT JOIN ratings r ON id.instructor_id = r.instructor_id
            LEFT JOIN coverage c ON c.instructor_id = id.instructor_id
            ORDER BY id.best_score DESC
            LIMIT :limit
        """
        )

        result = self.db.execute(
            query,
            {
                "corrected_query": corrected_query,
                "original_query": original_query,
                "search_limit": limit * 5,
                "limit": limit,
                "max_price": max_price,
            },
        )

        return [
            {
                "instructor_id": row.instructor_id,
                "first_name": row.first_name,
                "last_initial": row.last_initial,
                "bio_snippet": row.bio_snippet,
                "years_experience": row.years_experience,
                "profile_picture_key": row.profile_picture_key,
                "verified": row.verified,
                "matching_services": row.matching_services,
                "best_score": float(row.best_score),
                "match_count": int(row.match_count),
                "avg_rating": float(row.avg_rating) if row.avg_rating else None,
                "review_count": int(row.review_count),
                "coverage_areas": list(row.coverage_areas) if row.coverage_areas else [],
            }
            for row in result
        ]
