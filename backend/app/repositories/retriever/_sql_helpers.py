"""Shared SQL helpers for retriever repository mixins."""

from typing import Any, Dict, List

_SERVICE_PRICE_SUMMARY_CTE = """
    service_price_summary AS (
        SELECT sfp.service_id,
               MIN(sfp.hourly_rate) AS min_hourly_rate,
               MAX(CASE WHEN sfp.format = 'student_location' THEN 1 ELSE 0 END) AS has_student_location,
               MAX(CASE WHEN sfp.format = 'instructor_location' THEN 1 ELSE 0 END) AS has_instructor_location,
               MAX(CASE WHEN sfp.format = 'online' THEN 1 ELSE 0 END) AS has_online
        FROM service_format_pricing sfp
        GROUP BY sfp.service_id
    )"""

_SERVICE_PRICE_MIN_CTE = """
    service_price_summary AS (
        SELECT sfp.service_id,
               MIN(sfp.hourly_rate) AS min_hourly_rate
        FROM service_format_pricing sfp
        GROUP BY sfp.service_id
    )"""


def _price_cte_query(sql: str, *, full: bool = False) -> str:
    """Prepend the shared pricing CTE to a SQL query."""
    cte = _SERVICE_PRICE_SUMMARY_CTE if full else _SERVICE_PRICE_MIN_CTE
    return "WITH " + cte + " " + sql


def _serialize_embedding(embedding: List[float]) -> str:
    """Serialize a pgvector embedding into the SQL text format."""
    return "[" + ",".join(str(x) for x in embedding) + "]"


def _build_vector_matched_services_cte() -> str:
    """Build the vector-search CTE used by grouped instructor search."""
    return """
            ,
            matched_services AS (
                -- Step 1: Vector search to find matching services
                SELECT
                    ins.id as service_id,
                    sc.id as service_catalog_id,
                    sc.name as service_name,
                    sc.description as service_description,
                    sps.min_hourly_rate,
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
                JOIN service_price_summary sps ON sps.service_id = ins.id
                JOIN instructor_profiles ip ON ip.id = ins.instructor_profile_id
                WHERE sc.is_active = true
                    AND ins.is_active = true
                    AND sc.embedding_v2 IS NOT NULL
                    AND ip.is_live = true
                    AND ip.bgc_status = 'passed'
                    AND (:max_price IS NULL OR sps.min_hourly_rate <= :max_price)
                ORDER BY sc.embedding_v2 <=> CAST(:embedding AS vector)
                LIMIT :search_limit
            ),
"""


def _build_text_matched_services_cte() -> str:
    """Build the text-search CTE used by grouped instructor search."""
    return """
            ,
            matched_services AS (
                SELECT
                    ins.id as service_id,
                    sc.id as service_catalog_id,
                    sc.name as service_name,
                    sc.description as service_description,
                    sps.min_hourly_rate,
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
                JOIN service_price_summary sps ON sps.service_id = ins.id
                JOIN instructor_profiles ip ON ip.id = ins.instructor_profile_id
                WHERE sc.is_active = true
                  AND ins.is_active = true
                  AND ip.is_live = true
                  AND ip.bgc_status = 'passed'
                  AND (:max_price IS NULL OR sps.min_hourly_rate <= :max_price)
                  AND (
                        sc.name % :corrected_query
                        OR sc.name % :original_query
                        OR COALESCE(sc.description, '') % :corrected_query
                  )
                ORDER BY relevance_score DESC
                LIMIT :search_limit
            ),
"""


def _build_grouped_instructor_search_tail() -> str:
    """Build the shared grouped-search CTE tail and final select."""
    return """
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
                            'min_hourly_rate', min_hourly_rate,
                            'price_per_hour', min_hourly_rate,
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
                    CASE WHEN COALESCE(u.last_name, '') = '' THEN '' ELSE LEFT(u.last_name, 1) || '.' END as last_initial,
                    ip.bio,
                    ip.years_experience,
                    u.profile_picture_key,
                    u.profile_picture_version,
                    (ip.identity_verified_at IS NOT NULL) as verified,
                    ip.is_founding_instructor
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
                    array_agg(
                        DISTINCT COALESCE(rb.display_name, rb.region_name)
                        ORDER BY COALESCE(rb.display_name, rb.region_name)
                    ) as areas
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
                id.profile_picture_version,
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


def _grouped_search_params(
    embedding: List[float],
    limit: int,
    max_price: int | None,
) -> Dict[str, object]:
    """Build params for vector grouped-search queries."""
    return {
        "embedding": _serialize_embedding(embedding),
        "search_limit": limit * 5,
        "limit": limit,
        "max_price": max_price,
    }


def _grouped_text_search_params(
    corrected_query: str,
    original_query: str,
    limit: int,
    max_price: int | None,
) -> Dict[str, object]:
    """Build params for text grouped-search queries."""
    return {
        "corrected_query": corrected_query,
        "original_query": original_query,
        "search_limit": limit * 5,
        "limit": limit,
        "max_price": max_price,
    }


def _map_grouped_instructor_row(row: Any) -> Dict[str, Any]:
    """Map a grouped instructor search row into the public response shape."""
    return {
        "instructor_id": row.instructor_id,
        "first_name": row.first_name,
        "last_initial": row.last_initial,
        "bio_snippet": row.bio_snippet,
        "years_experience": row.years_experience,
        "profile_picture_key": row.profile_picture_key,
        "profile_picture_version": row.profile_picture_version,
        "verified": row.verified,
        "is_founding_instructor": bool(row.is_founding_instructor),
        "matching_services": row.matching_services,
        "best_score": float(row.best_score),
        "match_count": int(row.match_count),
        "avg_rating": float(row.avg_rating) if row.avg_rating else None,
        "review_count": int(row.review_count),
        "coverage_areas": list(row.coverage_areas) if row.coverage_areas else [],
    }


def _build_instructor_cards_sql() -> str:
    """Build the instructor-card hydration query."""
    return """
            SELECT
                ip.user_id as instructor_id,
                u.first_name,
                CASE WHEN COALESCE(u.last_name, '') = '' THEN '' ELSE LEFT(u.last_name, 1) || '.' END as last_initial,
                LEFT(ip.bio, 150) as bio_snippet,
                ip.years_experience,
                u.profile_picture_key,
                u.profile_picture_version,
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
                    array_agg(
                        DISTINCT COALESCE(rb.display_name, rb.region_name)
                        ORDER BY COALESCE(rb.display_name, rb.region_name)
                    ) as coverage_areas
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


def _map_instructor_card_row(row: Any) -> Dict[str, Any]:
    """Map an instructor card row into the public response shape."""
    return {
        "instructor_id": str(row.instructor_id),
        "first_name": row.first_name,
        "last_initial": row.last_initial,
        "bio_snippet": row.bio_snippet,
        "years_experience": int(row.years_experience) if row.years_experience is not None else None,
        "profile_picture_key": row.profile_picture_key,
        "profile_picture_version": int(row.profile_picture_version)
        if row.profile_picture_version is not None
        else None,
        "verified": bool(row.verified),
        "is_founding_instructor": bool(row.is_founding_instructor),
        "avg_rating": float(row.avg_rating) if row.avg_rating is not None else None,
        "review_count": int(row.review_count or 0),
        "coverage_areas": list(row.coverage_areas) if row.coverage_areas else [],
        "teaching_locations": list(row.teaching_locations) if row.teaching_locations else [],
    }
