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
                ins.instructor_profile_id as instructor_id,
                -- Normalize cosine distance to similarity score (0-1)
                -- pgvector <=> returns distance [0, 2], convert to similarity
                GREATEST(0, 1 - ((sc.embedding_v2 <=> :embedding::vector) / 2)) as vector_score
            FROM service_catalog sc
            JOIN instructor_services ins ON ins.service_catalog_id = sc.id
            WHERE sc.is_active = true
                AND ins.is_active = true
                AND sc.embedding_v2 IS NOT NULL
            ORDER BY sc.embedding_v2 <=> :embedding::vector
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
                ins.instructor_profile_id as instructor_id,
                GREATEST(
                    similarity(sc.name, :corrected_query),
                    similarity(sc.name, :original_query),
                    similarity(COALESCE(sc.description, ''), :corrected_query) * 0.8
                ) as text_score
            FROM service_catalog sc
            JOIN instructor_services ins ON ins.service_catalog_id = sc.id
            WHERE sc.is_active = true
                AND ins.is_active = true
                AND (
                    sc.name % :corrected_query
                    OR sc.name % :original_query
                    OR COALESCE(sc.description, '') % :corrected_query
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
                ins.instructor_profile_id as instructor_id,
                ins.duration_options,
                ins.levels_taught,
                ins.age_groups
            FROM instructor_services ins
            JOIN service_catalog sc ON sc.id = ins.service_catalog_id
            WHERE ins.id = ANY(:ids)
                AND ins.is_active = true
                AND sc.is_active = true
        """
        )

        result = self.db.execute(query, {"ids": service_ids})

        return [
            {
                "id": row.instructor_service_id,
                "catalog_id": row.catalog_id,
                "name": row.name,
                "description": row.description,
                "price_per_hour": int(row.price_per_hour),
                "instructor_id": row.instructor_id,
                "duration_options": row.duration_options,
                "levels_taught": row.levels_taught,
                "age_groups": row.age_groups,
            }
            for row in result
        ]
