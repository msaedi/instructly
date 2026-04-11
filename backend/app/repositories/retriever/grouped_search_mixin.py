"""Grouped instructor search queries for the retriever repository."""

from typing import Any, Dict, List

from sqlalchemy import text

from ._sql_helpers import (
    _build_grouped_instructor_search_tail,
    _build_text_matched_services_cte,
    _build_vector_matched_services_cte,
    _grouped_search_params,
    _grouped_text_search_params,
    _map_grouped_instructor_row,
    _price_cte_query,
)
from .mixin_base import RetrieverRepositoryMixinBase


class GroupedSearchMixin(RetrieverRepositoryMixinBase):
    """Instructor-grouped vector and text search queries."""

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
        sql = _build_vector_matched_services_cte() + _build_grouped_instructor_search_tail()
        query = text(_price_cte_query(sql))
        result = self.db.execute(query, _grouped_search_params(embedding, limit, max_price))
        return [_map_grouped_instructor_row(row) for row in result]

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
        sql = _build_text_matched_services_cte() + _build_grouped_instructor_search_tail()
        query = text(_price_cte_query(sql))
        result = self.db.execute(
            query,
            _grouped_text_search_params(corrected_query, original_query, limit, max_price),
        )
        return [_map_grouped_instructor_row(row) for row in result]
