"""Candidate retrieval queries for the retriever repository."""

from typing import Any, Dict, List

from sqlalchemy import text

from ._sql_helpers import _price_cte_query, _serialize_embedding
from .mixin_base import RetrieverRepositoryMixinBase


class CandidateSearchMixin(RetrieverRepositoryMixinBase):
    """Vector and trigram candidate search helpers."""

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
        query = text(
            _price_cte_query(
                """
            SELECT
                ins.id as instructor_service_id,
                sc.id as catalog_id,
                sc.name,
                sc.description,
                sps.min_hourly_rate,
                ip.user_id as instructor_id,
                ss.id as subcategory_id,
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
            JOIN service_price_summary sps ON sps.service_id = ins.id
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
        )

        result = self.db.execute(
            query,
            {
                "embedding": _serialize_embedding(embedding),
                "limit": limit,
            },
        )

        return [
            {
                "id": row.instructor_service_id,
                "catalog_id": row.catalog_id,
                "name": row.name,
                "description": row.description,
                "min_hourly_rate": float(row.min_hourly_rate),
                "price_per_hour": float(row.min_hourly_rate),
                "instructor_id": row.instructor_id,
                "subcategory_id": row.subcategory_id,
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
            _price_cte_query(
                """
            SELECT
                ins.id as instructor_service_id,
                sc.id as catalog_id,
                sc.name,
                sc.description,
                sps.min_hourly_rate,
                ip.user_id as instructor_id,
                ss.id as subcategory_id,
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
            JOIN service_price_summary sps ON sps.service_id = ins.id
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
                "min_hourly_rate": float(row.min_hourly_rate),
                "price_per_hour": float(row.min_hourly_rate),
                "instructor_id": row.instructor_id,
                "subcategory_id": row.subcategory_id,
                "subcategory_name": row.subcategory_name,
                "category_name": row.category_name,
                "text_score": float(row.text_score),
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
