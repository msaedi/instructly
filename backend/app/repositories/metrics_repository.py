# backend/app/repositories/metrics_repository.py
"""
Metrics Repository for InstaInstru Platform.

Handles data access for system metrics and monitoring.
"""

from typing import Any, Dict, List

from sqlalchemy import text
from sqlalchemy.orm import Session


class MetricsRepository:
    """Repository for system metrics data access."""

    def __init__(self, db: Session):
        """Initialize with database session."""
        self.db = db

    def get_active_connections_count(self) -> int:
        """
        Get the count of active database connections.

        Returns:
            Number of active connections from pg_stat_activity
        """
        result = self.db.execute(text("SELECT count(*) FROM pg_stat_activity")).scalar()
        return int(result or 0)

    def get_slow_queries(
        self, min_mean_exec_time_ms: float = 100, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Get slow queries from pg_stat_statements.

        Args:
            min_mean_exec_time_ms: Minimum mean execution time in milliseconds
            limit: Maximum number of queries to return

        Returns:
            List of slow query data dictionaries
        """
        try:
            result = self.db.execute(
                text(
                    """
                    SELECT
                        query,
                        mean_exec_time,
                        calls,
                        total_exec_time
                    FROM pg_stat_statements
                    WHERE mean_exec_time > :min_time
                    ORDER BY mean_exec_time DESC
                    LIMIT :limit
                    """
                ),
                {"min_time": min_mean_exec_time_ms, "limit": limit},
            )

            slow_queries = []
            for row in result:
                slow_queries.append(
                    {
                        "query": row.query,
                        "mean_exec_time": row.mean_exec_time,
                        "calls": row.calls,
                        "total_exec_time": row.total_exec_time,
                    }
                )
            return slow_queries
        except Exception:
            # pg_stat_statements may not be installed
            return []
