# backend/app/services/base.py
"""
Base Service Pattern for InstaInstru Platform

Provides common functionality for all service classes including:
- Transaction management
- Logging
- Cache integration
- Error handling
- Performance monitoring
"""

import logging
import time
from contextlib import contextmanager
from functools import wraps
from typing import TYPE_CHECKING, Callable, Optional

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..core.exceptions import ServiceException

# Use TYPE_CHECKING to avoid circular imports
if TYPE_CHECKING:
    from .cache_service import CacheService

logger = logging.getLogger(__name__)


class BaseService:
    """
    Base class for all service layer components.

    Provides common patterns for:
    - Database session management
    - Caching
    - Logging
    - Transaction handling
    - Performance monitoring
    """

    def __init__(self, db: Session, cache: Optional["CacheService"] = None):
        """
        Initialize base service.

        Args:
            db: Database session
            cache: Optional CacheService instance
        """
        self.db = db
        self.cache = cache
        self.logger = logging.getLogger(self.__class__.__name__)
        self._metrics = {}  # Initialize metrics tracking

    @contextmanager
    def transaction(self):
        """
        Context manager for database transactions.

        Usage:
            with self.transaction():
                # Do multiple operations
                self.db.add(entity)
                # Note: commit is handled automatically
        """
        try:
            yield self.db
            self.db.commit()
            self.logger.debug("Transaction committed successfully")
        except SQLAlchemyError as e:
            self.logger.error(f"Transaction failed: {str(e)}")
            self.db.rollback()
            raise ServiceException(f"Database operation failed: {str(e)}")
        except Exception as e:
            self.logger.error(f"Unexpected error in transaction: {str(e)}")
            self.db.rollback()
            raise

    def with_transaction(self, func: Callable) -> Callable:
        """
        Decorator for methods that need transaction management.

        Usage:
            @self.with_transaction
            def create_booking(self, data):
                # Method implementation
        """

        @wraps(func)
        def wrapper(*args, **kwargs):
            with self.transaction():
                return func(*args, **kwargs)

        return wrapper

    def invalidate_cache(self, *keys: str) -> None:
        """
        Invalidate specific cache keys.

        Args:
            *keys: Cache keys to invalidate
        """
        if not self.cache:
            return

        for key in keys:
            try:
                self.cache.delete(key)
                self.logger.debug(f"Invalidated cache key: {key}")
            except Exception as e:
                self.logger.warning(f"Failed to invalidate cache key {key}: {str(e)}")

    def invalidate_pattern(self, pattern: str) -> None:
        """
        Invalidate all cache keys matching a pattern.

        Args:
            pattern: Redis key pattern (e.g., "bookings:*")
        """
        if not self.cache:
            return

        try:
            count = self.cache.delete_pattern(pattern)
            self.logger.debug(f"Invalidated {count} keys matching pattern: {pattern}")
        except Exception as e:
            self.logger.warning(f"Failed to invalidate pattern {pattern}: {str(e)}")

    def log_operation(self, operation: str, **context):
        """
        Log an operation with context.

        Args:
            operation: Operation name
            **context: Additional context to log
        """
        # Also record metric for this operation
        start_time = getattr(self, "_operation_start_time", None)
        if start_time:
            elapsed = time.time() - start_time
            self._record_metric(operation, elapsed, success=True)
            delattr(self, "_operation_start_time")
        else:
            # Start timing if not already started
            self._operation_start_time = time.time()

        self.logger.info(f"Operation: {operation}", extra={"operation": operation, **context})

    def _record_metric(self, operation: str, elapsed: float, success: bool) -> None:
        """Record performance metrics."""
        if operation not in self._metrics:
            self._metrics[operation] = {
                "count": 0,
                "total_time": 0,
                "success_count": 0,
                "failure_count": 0,
            }

        self._metrics[operation]["count"] += 1
        self._metrics[operation]["total_time"] += elapsed
        if success:
            self._metrics[operation]["success_count"] += 1
        else:
            self._metrics[operation]["failure_count"] += 1

        # Log slow operations
        if elapsed > 1.0:  # More than 1 second
            self.logger.warning(f"Slow operation detected: {operation} took {elapsed:.2f}s")

    def get_metrics(self) -> dict:
        """Get performance metrics for this service."""
        return {
            operation: {
                "count": data["count"],
                "avg_time": data["total_time"] / data["count"] if data["count"] > 0 else 0,
                "success_rate": data["success_count"] / data["count"] if data["count"] > 0 else 0,
                "total_time": data["total_time"],
            }
            for operation, data in self._metrics.items()
        }
