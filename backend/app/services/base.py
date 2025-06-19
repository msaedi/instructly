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
from typing import TYPE_CHECKING, Any, Callable, Generic, Optional, TypeVar

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..core.exceptions import ServiceException, ValidationException

try:
    from ..infrastructure.cache.redis_cache import RedisCache, get_cache
except ImportError:
    # Cache not yet implemented, use None
    def get_cache():
        return None

    RedisCache = None

# Use TYPE_CHECKING to avoid circular imports
if TYPE_CHECKING:
    from .cache_service import CacheService

T = TypeVar("T")
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
        self._metrics = {}

    @contextmanager
    def transaction(self):
        """
        Context manager for database transactions.

        Usage:
            with self.transaction():
                # Do multiple operations
                self.db.add(entity)
                self.db.commit()
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
            @with_transaction
            def create_booking(self, data):
                # Method implementation
        """

        @wraps(func)
        def wrapper(*args, **kwargs):
            with self.transaction():
                return func(*args, **kwargs)

        return wrapper

    def with_cache(
        self, key_prefix: str, ttl: int = 300, key_generator: Optional[Callable] = None
    ) -> Callable:
        """
        Decorator for caching method results.

        Args:
            key_prefix: Cache key prefix
            ttl: Time to live in seconds
            key_generator: Optional function to generate cache key

        Usage:
            @with_cache("bookings", ttl=600)
            def get_bookings(self, user_id: int):
                # Method implementation
        """

        def decorator(func: Callable) -> Callable:
            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                # Generate cache key
                if key_generator:
                    cache_key = key_generator(*args, **kwargs)
                else:
                    # Simple key generation from args
                    key_parts = [key_prefix]
                    key_parts.extend(str(arg) for arg in args[1:])  # Skip self
                    cache_key = ":".join(key_parts)

                # Try to get from cache
                if self.cache:
                    cached = await self.cache.get(cache_key)
                    if cached is not None:
                        self.logger.debug(f"Cache hit for key: {cache_key}")
                        return cached

                # Execute function
                result = await func(*args, **kwargs)

                # Store in cache
                if self.cache and result is not None:
                    await self.cache.set(cache_key, result, ttl=ttl)
                    self.logger.debug(f"Cached result for key: {cache_key}")

                return result

            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                # For sync methods, we'll implement a sync cache wrapper
                # This is simplified for now
                return func(*args, **kwargs)

            # Return appropriate wrapper based on function type
            import asyncio

            if asyncio.iscoroutinefunction(func):
                return async_wrapper
            return sync_wrapper

        return decorator

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

    def measure_performance(self, operation: str) -> Callable:
        """
        Decorator to measure method performance.

        Args:
            operation: Name of the operation being measured

        Usage:
            # Can't be used as @self.measure_performance
            # Instead, wrap manually or use without decorator
        """

        def decorator(func: Callable) -> Callable:
            @wraps(func)
            def wrapper(*args, **kwargs):
                start_time = time.time()
                try:
                    result = func(*args, **kwargs)
                    elapsed = time.time() - start_time
                    self._record_metric(operation, elapsed, success=True)
                    return result
                except Exception:
                    elapsed = time.time() - start_time
                    self._record_metric(operation, elapsed, success=False)
                    raise

            return wrapper

        return decorator

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
            self.logger.warning(
                f"Slow operation detected: {operation} took {elapsed:.2f}s"
            )

    def get_metrics(self) -> dict:
        """Get performance metrics for this service."""
        return {
            operation: {
                "count": data["count"],
                "avg_time": data["total_time"] / data["count"]
                if data["count"] > 0
                else 0,
                "success_rate": data["success_count"] / data["count"]
                if data["count"] > 0
                else 0,
                "total_time": data["total_time"],
            }
            for operation, data in self._metrics.items()
        }

    def validate_input(self, data: Any, validator_class: type) -> Any:
        """
        Validate input data using a Pydantic model.

        Args:
            data: Input data to validate
            validator_class: Pydantic model class

        Returns:
            Validated data

        Raises:
            ValidationException: If validation fails
        """
        try:
            return validator_class(**data)
        except Exception as e:
            self.logger.error(f"Validation failed: {str(e)}")
            raise ValidationException(str(e))

    def log_operation(self, operation: str, **context):
        """
        Log an operation with context.

        Args:
            operation: Operation name
            **context: Additional context to log
        """
        self.logger.info(
            f"Operation: {operation}", extra={"operation": operation, **context}
        )


class BaseRepositoryService(BaseService, Generic[T]):
    """
    Base service with repository pattern support.

    Provides additional methods for services that work with
    a specific repository.
    """

    def __init__(
        self, db: Session, repository: Any, cache: Optional[RedisCache] = None
    ):
        """
        Initialize repository-based service.

        Args:
            db: Database session
            repository: Repository instance
            cache: Optional Redis cache
        """
        super().__init__(db, cache)
        self.repository = repository

    async def get_by_id(self, id: int, use_cache: bool = True) -> Optional[T]:
        """Get entity by ID with optional caching."""
        if use_cache and self.cache:
            cache_key = f"{self.repository.model.__name__}:{id}"
            cached = await self.cache.get(cache_key)
            if cached:
                return cached

        result = self.repository.get_by_id(id)

        if result and use_cache and self.cache:
            cache_key = f"{self.repository.model.__name__}:{id}"
            await self.cache.set(cache_key, result, ttl=300)

        return result

    def create(self, data: dict) -> T:
        """Create new entity."""
        with self.transaction():
            entity = self.repository.create(data)
            self.invalidate_related_caches(entity)
            return entity

    def update(self, id: int, data: dict) -> Optional[T]:
        """Update existing entity."""
        with self.transaction():
            entity = self.repository.update(id, data)
            if entity:
                self.invalidate_related_caches(entity)
            return entity

    def delete(self, id: int) -> bool:
        """Delete entity."""
        with self.transaction():
            entity = self.repository.get_by_id(id)
            if entity:
                result = self.repository.delete(id)
                self.invalidate_related_caches(entity)
                return result
            return False

    def invalidate_related_caches(self, entity: T) -> None:
        """
        Invalidate caches related to an entity.

        Override this method in subclasses to define
        which caches should be invalidated.
        """
        # Invalidate entity cache
        cache_key = f"{entity.__class__.__name__}:{entity.id}"
        self.invalidate_cache(cache_key)
