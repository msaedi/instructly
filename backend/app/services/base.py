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
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional

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

    # Class-level metrics storage
    _class_metrics = {}

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

    @staticmethod
    def measure_operation(operation_name: str) -> Callable:
        """
        Decorator to measure operation performance.

        Usage:
            @BaseService.measure_operation("create_booking")
            def create_booking(self, data):
                # Method implementation

        Args:
            operation_name: Name of the operation for metrics

        Returns:
            Decorator function
        """

        def decorator(func: Callable) -> Callable:
            # Store the operation name on the function for later use
            func._operation_name = operation_name
            func._is_measured = True

            @wraps(func)
            def wrapper(self, *args, **kwargs):
                # Now we have access to self!
                if not hasattr(self, "_metrics"):
                    # Initialize metrics if this is called on a non-BaseService instance
                    self._metrics = {}

                start_time = time.time()
                success = False

                try:
                    result = func(self, *args, **kwargs)
                    success = True
                    return result
                except Exception:
                    success = False
                    raise
                finally:
                    elapsed = time.time() - start_time
                    if hasattr(self, "_record_metric"):
                        self._record_metric(operation_name, elapsed, success)

                    # Log slow operations
                    if elapsed > 1.0 and hasattr(self, "logger"):
                        self.logger.warning(f"Slow operation detected: {operation_name} took {elapsed:.2f}s")

                    # Record Prometheus metrics
                    try:
                        from ..monitoring.prometheus_metrics import prometheus_metrics

                        service_name = self.__class__.__name__ if hasattr(self, "__class__") else "Unknown"
                        status = "success" if success else "error"
                        error_type = None

                        # Try to get error type if there was an exception
                        if not success and hasattr(wrapper, "_last_exception"):
                            error_type = type(wrapper._last_exception).__name__

                        prometheus_metrics.record_service_operation(
                            service=service_name,
                            operation=operation_name,
                            duration=elapsed,
                            status=status,
                            error_type=error_type,
                        )
                    except ImportError:
                        # Prometheus metrics not available, skip
                        pass
                    except Exception:
                        # Don't let metrics collection break the operation
                        pass

            return wrapper

        return decorator

    @contextmanager
    def measure_operation_context(self, operation_name: str):
        """
        Context manager to measure operation performance.

        Usage:
            with self.measure_operation_context("complex_operation"):
                # Do work here
                pass

        Args:
            operation_name: Name of the operation for metrics
        """
        start_time = time.time()
        success = False

        try:
            yield
            success = True
        except Exception:
            success = False
            raise
        finally:
            elapsed = time.time() - start_time
            self._record_metric(operation_name, elapsed, success)

            # Log slow operations
            if elapsed > 1.0:
                self.logger.warning(f"Slow operation detected: {operation_name} took {elapsed:.2f}s")

            # Record Prometheus metrics
            try:
                from ..monitoring.prometheus_metrics import prometheus_metrics

                service_name = self.__class__.__name__
                status = "success" if success else "error"

                prometheus_metrics.record_service_operation(
                    service=service_name, operation=operation_name, duration=elapsed, status=status
                )
            except ImportError:
                # Prometheus metrics not available, skip
                pass
            except Exception:
                # Don't let metrics collection break the operation
                pass

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

        Note: This method now only logs, it doesn't handle metrics.
        Use @measure_operation decorator or measure_operation_context for timing.

        Args:
            operation: Operation name
            **context: Additional context to log
        """
        self.logger.info(f"Operation: {operation}", extra={"operation": operation, **context})

    def _record_metric(self, operation: str, elapsed: float, success: bool) -> None:
        """
        Record performance metrics.

        Args:
            operation: Operation name
            elapsed: Time taken in seconds
            success: Whether operation succeeded
        """
        class_name = self.__class__.__name__
        if class_name not in BaseService._class_metrics:
            BaseService._class_metrics[class_name] = {}

        metrics = BaseService._class_metrics[class_name]

        if operation not in metrics:
            metrics[operation] = {
                "count": 0,
                "total_time": 0.0,
                "success_count": 0,
                "failure_count": 0,
                "min_time": float("inf"),
                "max_time": 0.0,
            }

        metric_data = metrics[operation]
        metric_data["count"] += 1
        metric_data["total_time"] += elapsed
        metric_data["min_time"] = min(metric_data["min_time"], elapsed)
        metric_data["max_time"] = max(metric_data["max_time"], elapsed)

        if success:
            metric_data["success_count"] += 1
        else:
            metric_data["failure_count"] += 1

    def get_metrics(self) -> Dict[str, Any]:
        """
        Get performance metrics for this service.

        Returns:
            Dictionary with metrics for each measured operation
        """
        class_name = self.__class__.__name__
        if class_name not in BaseService._class_metrics:
            return {}

        result = {}
        metrics = BaseService._class_metrics[class_name]

        for operation, data in metrics.items():
            count = data["count"]
            if count == 0:
                continue

            result[operation] = {
                "count": count,
                "avg_time": data["total_time"] / count,
                "min_time": data["min_time"],
                "max_time": data["max_time"],
                "total_time": data["total_time"],
                "success_rate": data["success_count"] / count,
                "success_count": data["success_count"],
                "failure_count": data["failure_count"],
            }

        return result

    def reset_metrics(self) -> None:
        """Reset all metrics for this service."""
        class_name = self.__class__.__name__
        if class_name in BaseService._class_metrics:
            BaseService._class_metrics[class_name].clear()
        self.logger.info(f"Metrics reset for {class_name}")
