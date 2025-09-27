# backend/app/middleware/db_query_counter.py
"""
Database query counting for request performance monitoring.

This module provides SQLAlchemy event listeners to count queries per request.
"""

import logging
from typing import Any, Optional

from fastapi import Request
from sqlalchemy import event
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


class QueryCounter:
    """Tracks database queries per request."""

    @staticmethod
    def setup_query_counting(engine: Engine) -> None:
        """
        Set up SQLAlchemy event listeners for query counting.

        Args:
            engine: SQLAlchemy engine to monitor
        """

        def increment_query_count(
            conn: Any,
            cursor: Any,
            statement: str,
            parameters: Any,
            context: Any,
            executemany: Any,
        ) -> None:
            """Increment query count for current request."""
            # Try to get the current request from context
            request = QueryCounter.get_current_request()
            if request and hasattr(request.state, "query_count"):
                request.state.query_count += 1

                # Log query in debug mode
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(
                        f"Query #{request.state.query_count} for request {getattr(request.state, 'request_id', 'unknown')}: "
                        f"{statement[:100]}..."
                    )

        event.listens_for(engine, "before_cursor_execute")(increment_query_count)

    @staticmethod
    def get_current_request() -> Optional[Request]:
        """
        Get the current request from context.

        This is a placeholder - in production, you'd use contextvars
        or another mechanism to track the current request.
        """
        # TODO: Implement proper request context tracking
        # For now, this would need to be integrated with your app's
        # request context management
        return None


def track_cache_operations(request: Request, operation: str, hit: bool = True) -> None:
    """
    Track cache operations for the current request.

    Args:
        request: Current FastAPI request
        operation: Type of cache operation (get, set, etc.)
        hit: Whether it was a cache hit (for get operations)
    """
    if hasattr(request.state, "cache_hits") and hasattr(request.state, "cache_misses"):
        if operation == "get":
            if hit:
                request.state.cache_hits += 1
            else:
                request.state.cache_misses += 1
