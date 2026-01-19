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

import asyncio
from contextlib import asynccontextmanager, contextmanager
from functools import update_wrapper
import logging
import time
from typing import (
    TYPE_CHECKING,
    Any,
    AsyncIterator,
    Awaitable,
    Callable,
    ClassVar,
    Concatenate,
    Dict,
    Iterator,
    Optional,
    ParamSpec,
    Protocol,
    TypedDict,
    TypeVar,
    cast,
)

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..core.exceptions import ServiceException

# Import prometheus_metrics at module level to avoid repeated imports
try:
    from ..monitoring.prometheus_metrics import prometheus_metrics

    PROMETHEUS_AVAILABLE = True
except ImportError:
    prometheus_metrics = None
    PROMETHEUS_AVAILABLE = False

# Use TYPE_CHECKING to avoid circular imports
if TYPE_CHECKING:
    pass


P = ParamSpec("P")
R = TypeVar("R")
FuncType = TypeVar("FuncType", bound=Callable[..., Any])


class _MetricBucket(TypedDict):
    count: int
    total_time: float
    success_count: int
    failure_count: int
    min_time: float
    max_time: float


class _AggregatedMetric(TypedDict):
    count: int
    avg_time: float
    min_time: float
    max_time: float
    total_time: float
    success_rate: float
    success_count: int
    failure_count: int


class CacheInvalidationProtocol(Protocol):
    def get(self, key: str) -> Optional[Any]:
        """Retrieve an item from the cache."""

    def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = ...,
        tier: str = ...,
    ) -> bool:
        """Store an item in the cache with an optional TTL."""

    def delete(self, key: str) -> bool:
        """Remove an item from the cache."""

    def delete_pattern(self, pattern: str) -> int:
        """Remove all cache items matching a pattern."""


logger = logging.getLogger(__name__)


class BaseService:
    """Base class for all service layer components.

    Provides common patterns for:
    - Database session management
    - Caching
    - Logging
    - Transaction handling
    - Performance monitoring
    """

    _class_metrics: ClassVar[Dict[str, Dict[str, _MetricBucket]]] = {}

    def __init__(
        self,
        db: Session,
        cache: Optional[CacheInvalidationProtocol] = None,
    ) -> None:
        """
        Initialize base service.

        Args:
            db: Database session
            cache: Optional CacheService instance
        """
        self.db: Session = db
        self.cache: Optional[CacheInvalidationProtocol] = cache
        self.logger: logging.Logger = logging.getLogger(self.__class__.__name__)

    @contextmanager
    def transaction(self) -> Iterator[Session]:
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

    def with_transaction(
        self, func: Callable[Concatenate["BaseService", P], R]
    ) -> Callable[Concatenate["BaseService", P], R]:
        """
        Decorator for methods that need transaction management.

        Usage:
            @self.with_transaction
            def create_booking(self, data):
                # Method implementation
        """

        def wrapper(self_arg: "BaseService", /, *args: P.args, **kwargs: P.kwargs) -> R:
            with self_arg.transaction():
                return func(self_arg, *args, **kwargs)

        update_wrapper(wrapper, func)
        return wrapper

    @staticmethod
    def measure_operation(
        operation_name: str,
    ) -> Callable[[FuncType], FuncType]:
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

        def decorator(func: FuncType) -> FuncType:
            setattr(func, "_operation_name", operation_name)
            setattr(func, "_is_measured", True)

            if not asyncio.iscoroutinefunction(func):

                def wrapper(*args: Any, **kwargs: Any) -> Any:
                    if not args:
                        return func(*args, **kwargs)

                    service = cast(BaseService, args[0])
                    start_time = time.time()
                    success = False
                    error_type: Optional[str] = None

                    try:
                        result = func(*args, **kwargs)
                        success = True
                        return result
                    except Exception as exc:  # pragma: no cover - logging path
                        success = False
                        error_type = type(exc).__name__
                        raise
                    finally:
                        elapsed = time.time() - start_time
                        service._record_metric(operation_name, elapsed, success)

                        if elapsed > 1.0 and hasattr(service, "logger"):
                            func_name = getattr(func, "__name__", operation_name)
                            service.logger.warning(
                                f"Slow operation detected: {func_name} took {elapsed:.2f}s"
                            )

                        if PROMETHEUS_AVAILABLE and prometheus_metrics:
                            try:
                                prometheus_metrics.record_service_operation(
                                    service=service.__class__.__name__,
                                    operation=operation_name,
                                    duration=elapsed,
                                    status="success" if success else "error",
                                    error_type=error_type,
                                )
                            except Exception:  # pragma: no cover - metrics failure
                                logger.debug(
                                    "Failed to record Prometheus service metrics",
                                    exc_info=True,
                                )

                update_wrapper(wrapper, func)
                return cast(FuncType, wrapper)

            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                if not args:
                    result_obj = func(*args, **kwargs)
                    return await cast(Awaitable[Any], result_obj)

                service = cast(BaseService, args[0])
                start_time = time.time()
                success = False
                error_type: Optional[str] = None

                try:
                    result_obj = func(*args, **kwargs)
                    result = await cast(Awaitable[Any], result_obj)
                    success = True
                    return result
                except Exception as exc:  # pragma: no cover - logging path
                    success = False
                    error_type = type(exc).__name__
                    raise
                finally:
                    elapsed = time.time() - start_time
                    service._record_metric(operation_name, elapsed, success)

                    if elapsed > 1.0 and hasattr(service, "logger"):
                        func_name = getattr(func, "__name__", operation_name)
                        service.logger.warning(
                            f"Slow operation detected: {func_name} took {elapsed:.2f}s"
                        )

                    if PROMETHEUS_AVAILABLE and prometheus_metrics:
                        try:
                            prometheus_metrics.record_service_operation(
                                service=service.__class__.__name__,
                                operation=operation_name,
                                duration=elapsed,
                                status="success" if success else "error",
                                error_type=error_type,
                            )
                        except Exception:  # pragma: no cover - metrics failure
                            logger.debug(
                                "Failed to record Prometheus service metrics",
                                exc_info=True,
                            )

            update_wrapper(async_wrapper, func)
            return cast(FuncType, async_wrapper)

        return decorator

    @contextmanager
    def measure_operation_context(self, operation_name: str) -> Iterator[None]:
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
                self.logger.warning(
                    f"Slow operation detected: {operation_name} took {elapsed:.2f}s"
                )

            # Record Prometheus metrics
            if PROMETHEUS_AVAILABLE and prometheus_metrics:
                try:
                    service_name = self.__class__.__name__
                    status = "success" if success else "error"

                    prometheus_metrics.record_service_operation(
                        service=service_name,
                        operation=operation_name,
                        duration=elapsed,
                        status=status,
                    )
                except Exception:
                    # Don't let metrics collection break the operation
                    logger.debug("Non-fatal error ignored", exc_info=True)

    @asynccontextmanager
    async def async_measure_operation_context(self, operation_name: str) -> AsyncIterator[None]:
        """
        Async context manager to measure operation performance.
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

            if elapsed > 1.0:
                self.logger.warning(
                    f"Slow operation detected: {operation_name} took {elapsed:.2f}s"
                )

            if PROMETHEUS_AVAILABLE and prometheus_metrics:
                try:
                    service_name = self.__class__.__name__
                    status = "success" if success else "error"
                    prometheus_metrics.record_service_operation(
                        service=service_name,
                        operation=operation_name,
                        duration=elapsed,
                        status=status,
                    )
                except Exception:
                    logger.debug("Non-fatal error ignored", exc_info=True)

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

    def log_operation(self, operation: str, **context: Any) -> None:
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
        metrics = BaseService._class_metrics.setdefault(class_name, {})
        metric_data = metrics.setdefault(
            operation,
            {
                "count": 0,
                "total_time": 0.0,
                "success_count": 0,
                "failure_count": 0,
                "min_time": float("inf"),
                "max_time": 0.0,
            },
        )
        elapsed_value = float(elapsed)
        metric_data["count"] += 1
        metric_data["total_time"] += elapsed_value
        metric_data["min_time"] = min(metric_data["min_time"], elapsed_value)
        metric_data["max_time"] = max(metric_data["max_time"], elapsed_value)

        success_flag = bool(success)
        if success_flag:
            metric_data["success_count"] += 1
        else:
            metric_data["failure_count"] += 1

    def get_metrics(self) -> Dict[str, _AggregatedMetric]:
        """
        Get performance metrics for this service.

        Returns:
            Dictionary with metrics for each measured operation
        """
        class_name = self.__class__.__name__
        if class_name not in BaseService._class_metrics:
            return {}

        result: Dict[str, _AggregatedMetric] = {}
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
