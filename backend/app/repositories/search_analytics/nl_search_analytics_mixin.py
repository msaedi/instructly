"""Read-side NL search analytics queries."""

from datetime import date
from typing import Any, Dict, List

from sqlalchemy import and_, desc, func

from ...models.nl_search import SearchClick, SearchQuery
from .mixin_base import SearchAnalyticsRepositoryMixinBase


class NLSearchAnalyticsMixin(SearchAnalyticsRepositoryMixinBase):
    """Read-side analytics for NL search queries and clicks."""

    def nl_get_popular_queries(self, days: int = 7, limit: int = 50) -> List[Dict[str, Any]]:
        """Get most popular NL search queries in the last N days."""
        from sqlalchemy import text as sql_text

        query = sql_text(
            """
            SELECT
                original_query,
                COUNT(*) as query_count,
                AVG(result_count) as avg_results,
                AVG(total_latency_ms) as avg_latency_ms
            FROM search_queries
            WHERE created_at > NOW() - INTERVAL :days_interval
            GROUP BY original_query
            ORDER BY query_count DESC
            LIMIT :limit
        """
        )

        result = self.db.execute(query, {"days_interval": f"{days} days", "limit": limit})

        return [
            {
                "query": row.original_query,
                "count": row.query_count,
                "avg_results": float(row.avg_results) if row.avg_results else 0.0,
                "avg_latency_ms": float(row.avg_latency_ms) if row.avg_latency_ms else 0.0,
            }
            for row in result
        ]

    def nl_get_top_queries_by_date_range(
        self,
        start_date: date,
        end_date: date,
        limit: int = 50,
        min_count: int = 2,
    ) -> List[Dict[str, Any]]:
        """Get top NL search queries with booking conversion rates."""
        base_rows = (
            self.db.query(
                SearchQuery.original_query.label("query"),
                func.count(SearchQuery.id).label("query_count"),
                func.avg(SearchQuery.result_count).label("avg_results"),
            )
            .filter(
                and_(
                    func.date(SearchQuery.created_at) >= start_date,
                    func.date(SearchQuery.created_at) <= end_date,
                    SearchQuery.original_query.isnot(None),
                    SearchQuery.original_query != "",
                )
            )
            .group_by(SearchQuery.original_query)
            .having(func.count(SearchQuery.id) >= min_count)
            .order_by(desc("query_count"))
            .limit(limit)
            .all()
        )

        if not base_rows:
            return []

        queries = [row.query for row in base_rows]
        conversion_rows = (
            self.db.query(
                SearchQuery.original_query.label("query"),
                func.count(func.distinct(SearchQuery.id)).label("book_count"),
            )
            .join(SearchClick, SearchClick.search_query_id == SearchQuery.id)
            .filter(
                and_(
                    SearchClick.action == "book",
                    SearchQuery.original_query.in_(queries),
                    func.date(SearchQuery.created_at) >= start_date,
                    func.date(SearchQuery.created_at) <= end_date,
                )
            )
            .group_by(SearchQuery.original_query)
            .all()
        )
        conversion_map = {row.query: int(row.book_count or 0) for row in conversion_rows}

        results: List[Dict[str, Any]] = []
        for row in base_rows:
            count = int(row.query_count or 0)
            book_count = conversion_map.get(row.query, 0)
            conversion_rate = round((book_count / count), 4) if count else 0.0
            results.append(
                {
                    "query": row.query,
                    "count": count,
                    "avg_results": float(row.avg_results or 0.0),
                    "conversion_rate": conversion_rate,
                }
            )

        return results

    def nl_get_zero_result_queries_by_date_range(
        self, start_date: date, end_date: date, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get NL search queries that returned zero results within date range."""
        rows = (
            self.db.query(
                SearchQuery.original_query.label("query"),
                func.count(SearchQuery.id).label("query_count"),
            )
            .filter(
                and_(
                    func.date(SearchQuery.created_at) >= start_date,
                    func.date(SearchQuery.created_at) <= end_date,
                    SearchQuery.result_count == 0,
                    SearchQuery.original_query.isnot(None),
                    SearchQuery.original_query != "",
                )
            )
            .group_by(SearchQuery.original_query)
            .order_by(desc("query_count"))
            .limit(limit)
            .all()
        )

        return [{"query": row.query, "count": int(row.query_count or 0)} for row in rows]

    def nl_count_searches_by_date_range(self, start_date: date, end_date: date) -> int:
        """Count total NL searches within date range."""
        return int(
            self.db.query(func.count(SearchQuery.id))
            .filter(
                and_(
                    func.date(SearchQuery.created_at) >= start_date,
                    func.date(SearchQuery.created_at) <= end_date,
                    SearchQuery.original_query.isnot(None),
                    SearchQuery.original_query != "",
                )
            )
            .scalar()
            or 0
        )

    def nl_count_zero_result_searches_by_date_range(self, start_date: date, end_date: date) -> int:
        """Count NL searches with zero results within date range."""
        return int(
            self.db.query(func.count(SearchQuery.id))
            .filter(
                and_(
                    func.date(SearchQuery.created_at) >= start_date,
                    func.date(SearchQuery.created_at) <= end_date,
                    SearchQuery.result_count == 0,
                    SearchQuery.original_query.isnot(None),
                    SearchQuery.original_query != "",
                )
            )
            .scalar()
            or 0
        )

    def nl_get_zero_result_queries(self, days: int = 7, limit: int = 100) -> List[Dict[str, Any]]:
        """Get NL search queries that returned zero results."""
        from sqlalchemy import text as sql_text

        query = sql_text(
            """
            SELECT
                original_query,
                COUNT(*) as query_count,
                MAX(created_at) as last_searched
            FROM search_queries
            WHERE created_at > NOW() - INTERVAL :days_interval
              AND result_count = 0
            GROUP BY original_query
            ORDER BY query_count DESC
            LIMIT :limit
        """
        )

        result = self.db.execute(query, {"days_interval": f"{days} days", "limit": limit})

        return [
            {
                "query": row.original_query,
                "count": row.query_count,
                "last_searched": row.last_searched.isoformat() if row.last_searched else None,
            }
            for row in result
        ]

    def nl_get_search_metrics(self, days: int = 1) -> Dict[str, Any]:
        """Get aggregate NL search metrics."""
        from sqlalchemy import text as sql_text

        query = sql_text(
            """
            SELECT
                COUNT(*) as total_searches,
                AVG(total_latency_ms) as avg_latency_ms,
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY total_latency_ms) as p50_latency_ms,
                PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY total_latency_ms) as p95_latency_ms,
                AVG(result_count) as avg_results,
                SUM(CASE WHEN result_count = 0 THEN 1 ELSE 0 END)::float / NULLIF(COUNT(*), 0)
                    as zero_result_rate,
                SUM(CASE WHEN cache_hit THEN 1 ELSE 0 END)::float / NULLIF(COUNT(*), 0)
                    as cache_hit_rate,
                SUM(CASE WHEN degraded THEN 1 ELSE 0 END)::float / NULLIF(COUNT(*), 0)
                    as degradation_rate
            FROM search_queries
            WHERE created_at > NOW() - INTERVAL :days_interval
        """
        )

        result = self.db.execute(query, {"days_interval": f"{days} days"}).first()

        if not result or result.total_searches == 0:
            return {
                "total_searches": 0,
                "avg_latency_ms": 0.0,
                "p50_latency_ms": 0.0,
                "p95_latency_ms": 0.0,
                "avg_results": 0.0,
                "zero_result_rate": 0.0,
                "cache_hit_rate": 0.0,
                "degradation_rate": 0.0,
            }

        return {
            "total_searches": result.total_searches,
            "avg_latency_ms": float(result.avg_latency_ms) if result.avg_latency_ms else 0.0,
            "p50_latency_ms": float(result.p50_latency_ms) if result.p50_latency_ms else 0.0,
            "p95_latency_ms": float(result.p95_latency_ms) if result.p95_latency_ms else 0.0,
            "avg_results": float(result.avg_results) if result.avg_results else 0.0,
            "zero_result_rate": float(result.zero_result_rate) if result.zero_result_rate else 0.0,
            "cache_hit_rate": float(result.cache_hit_rate) if result.cache_hit_rate else 0.0,
            "degradation_rate": (
                float(result.degradation_rate) if result.degradation_rate else 0.0
            ),
        }
