"""Service layer for MCP search analytics endpoints."""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.repositories.search_analytics_repository import SearchAnalyticsRepository
from app.services.base import BaseService


class MCPSearchAnalyticsService(BaseService):
    """Business logic for MCP search analytics endpoints."""

    def __init__(self, db: Session):
        super().__init__(db)
        self.repository = SearchAnalyticsRepository(db)

    @BaseService.measure_operation("mcp_search.top_queries")
    def get_top_queries(
        self,
        *,
        start_date: date,
        end_date: date,
        limit: int,
        min_count: int,
    ) -> dict[str, Any]:
        queries = self.repository.nl_get_top_queries_by_date_range(
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            min_count=min_count,
        )
        total_searches = self.repository.nl_count_searches_by_date_range(start_date, end_date)

        return {
            "time_window": {"start": start_date, "end": end_date},
            "queries": queries,
            "total_searches": total_searches,
        }

    @BaseService.measure_operation("mcp_search.zero_results")
    def get_zero_result_queries(
        self,
        *,
        start_date: date,
        end_date: date,
        limit: int,
    ) -> dict[str, Any]:
        queries = self.repository.nl_get_zero_result_queries_by_date_range(
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        )
        total_searches = self.repository.nl_count_searches_by_date_range(start_date, end_date)
        total_zero = self.repository.nl_count_zero_result_searches_by_date_range(
            start_date, end_date
        )
        zero_result_rate = round((total_zero / total_searches), 4) if total_searches else 0.0

        return {
            "time_window": {"start": start_date, "end": end_date},
            "queries": queries,
            "total_zero_result_searches": total_zero,
            "zero_result_rate": zero_result_rate,
        }
