# backend/app/repositories/cached_repository_mixin.py
"""
Cached Repository Mixin for InstaInstru Platform

Provides caching capabilities for repository classes with:
- Automatic cache key generation
- Cache invalidation on updates
- Configurable TTL per method
- Performance monitoring

This mixin can be added to any repository to enable caching
without modifying the core repository logic.
"""

import hashlib
import json
import logging
from functools import wraps
from typing import Any, Callable, Dict, Optional, Union

from ..services.cache_service import CacheService, get_cache_service

logger = logging.getLogger(__name__)


class CachedRepositoryMixin:
    """
    Mixin to add caching capabilities to repositories.

    Usage:
        class BookingRepository(BaseRepository[Booking], CachedRepositoryMixin):
            def __init__(self, db: Session):
                super().__init__(db, Booking)
                self.init_cache()
    """

    def init_cache(self, cache_service: Optional[CacheService] = None):
        """
        Initialize cache service for the repository.

        Args:
            cache_service: Optional cache service instance
        """
        self._cache_service = cache_service
        self._cache_prefix = self.__class__.__name__.lower().replace("repository", "")
        self._cache_enabled = True

    @property
    def cache_service(self) -> Optional[CacheService]:
        """Get cache service, creating if needed."""
        if not hasattr(self, "_cache_service") or self._cache_service is None:
            try:
                self._cache_service = get_cache_service(self.db)
            except Exception as e:
                logger.warning(f"Failed to initialize cache service: {e}")
                self._cache_service = None
        return self._cache_service

    def _generate_cache_key(self, method_name: str, *args, **kwargs) -> str:
        """
        Generate a cache key for a repository method call.

        Args:
            method_name: Name of the repository method
            *args: Method arguments
            **kwargs: Method keyword arguments

        Returns:
            Cache key string
        """
        # Build key components
        key_parts = [self._cache_prefix, method_name]

        # Add arguments to key
        for arg in args:
            if hasattr(arg, "id"):
                key_parts.append(f"id_{arg.id}")
            elif isinstance(arg, (str, int, float, bool)):
                key_parts.append(str(arg))
            elif hasattr(arg, "isoformat"):  # Handle date/datetime objects
                key_parts.append(arg.isoformat())
            else:
                # Hash complex objects
                arg_hash = hashlib.md5(str(arg).encode()).hexdigest()[:8]
                key_parts.append(arg_hash)

        # Add keyword arguments
        if kwargs:
            sorted_kwargs = sorted(kwargs.items())
            kwargs_str = json.dumps(sorted_kwargs, default=str)
            kwargs_hash = hashlib.md5(kwargs_str.encode()).hexdigest()[:8]
            key_parts.append(f"kw_{kwargs_hash}")

        return ":".join(key_parts)

    def _serialize_for_cache(self, data: Any, _visited: set = None, _depth: int = 0) -> Any:
        """
        Serialize data for caching with cycle detection and depth limit.

        Args:
            data: The data to serialize
            _visited: Set of object IDs already being processed (for cycle detection)
            _depth: Current recursion depth (to prevent deep nesting)
        """
        MAX_DEPTH = 2  # Only serialize 2 levels deep

        if _visited is None:
            _visited = set()

        # Handle None
        if data is None:
            return None

        # Handle basic types
        if isinstance(data, (str, int, float, bool)):
            return data

        # Handle datetime objects
        if hasattr(data, "isoformat"):
            return data.isoformat()

        # Handle lists
        if isinstance(data, list):
            if _depth >= MAX_DEPTH:
                return []  # Stop at max depth
            return [self._serialize_for_cache(item, _visited, _depth) for item in data]

        # Handle SQLAlchemy objects
        if hasattr(data, "__table__"):
            obj_id = id(data)

            # Cycle detection
            if obj_id in _visited:
                # Return minimal representation for circular reference
                return {"id": getattr(data, "id", None), "__type__": data.__class__.__name__, "_circular_ref": True}

            _visited.add(obj_id)

            try:
                # Start with basic columns
                result = (
                    data.to_dict()
                    if hasattr(data, "to_dict")
                    else {c.name: getattr(data, c.name) for c in data.__table__.columns}
                )

                # Add marker for cached data
                result["_from_cache"] = True

                # Handle relationships only if not at max depth
                if _depth < MAX_DEPTH:
                    for relationship in data.__mapper__.relationships:
                        if relationship.key in data.__dict__:  # Only if loaded
                            related = getattr(data, relationship.key)
                            if related is not None:
                                # For critical relationships, include all required fields
                                if relationship.key in ["student", "instructor"]:
                                    if hasattr(related, "id"):
                                        # Include all fields needed by StudentInfo/InstructorInfo
                                        result[relationship.key] = {
                                            "id": related.id,
                                            "first_name": getattr(related, "first_name", ""),
                                            "last_name": getattr(related, "last_name", ""),
                                            "email": getattr(related, "email", ""),
                                            "__type__": related.__class__.__name__,
                                        }
                                elif relationship.key == "instructor_service":
                                    if hasattr(related, "id"):
                                        # Include all fields needed by ServiceInfo
                                        result[relationship.key] = {
                                            "id": related.id,
                                            "name": getattr(related, "name", ""),
                                            "description": getattr(related, "description", None),
                                            "__type__": related.__class__.__name__,
                                        }
                                # Skip non-critical relationships at depth 1+
                                elif _depth == 0:
                                    result[relationship.key] = self._serialize_for_cache(related, _visited, _depth + 1)

                return result

            finally:
                _visited.remove(obj_id)

        elif isinstance(data, dict):
            return {k: self._serialize_for_cache(v, _visited, _depth) for k, v in data.items()}
        else:
            # Default: return as-is
            return data

    def _invalidate_method_cache(self, method_name: str, *args, **kwargs):
        """
        Invalidate cache for a specific method call.

        Args:
            method_name: Name of the method
            *args: Method arguments
            **kwargs: Method keyword arguments
        """
        if not self.cache_service:
            return

        cache_key = self._generate_cache_key(method_name, *args, **kwargs)
        try:
            self.cache_service.delete(cache_key)
            logger.debug(f"Invalidated cache for {method_name}: {cache_key}")
        except Exception as e:
            logger.error(f"Failed to invalidate cache for {method_name}: {e}")

    def invalidate_entity_cache(self, entity_id: Union[int, str]):
        """
        Invalidate all cache entries related to an entity.

        Args:
            entity_id: ID of the entity to invalidate
        """
        if not self.cache_service:
            return

        pattern = f"{self._cache_prefix}:*:{entity_id}:*"
        try:
            count = self.cache_service.delete_pattern(pattern)
            logger.info(f"Invalidated {count} cache entries for {self._cache_prefix} entity {entity_id}")
        except Exception as e:
            logger.error(f"Failed to invalidate entity cache: {e}")

    def invalidate_all_cache(self):
        """Invalidate all cache entries for this repository."""
        if not self.cache_service:
            return

        pattern = f"{self._cache_prefix}:*"
        try:
            count = self.cache_service.delete_pattern(pattern)
            logger.info(f"Invalidated {count} cache entries for {self._cache_prefix}")
        except Exception as e:
            logger.error(f"Failed to invalidate all cache: {e}")

    def with_cache_disabled(self):
        """
        Context manager to temporarily disable caching.

        Usage:
            with repository.with_cache_disabled():
                result = repository.get_something()  # Won't use cache
        """

        class CacheDisabler:
            def __init__(self, repo):
                self.repo = repo
                self.original_state = None

            def __enter__(self):
                self.original_state = self.repo._cache_enabled
                self.repo._cache_enabled = False
                return self

            def __exit__(self, exc_type, exc_val, exc_tb):
                self.repo._cache_enabled = self.original_state

        return CacheDisabler(self)

    def get_cache_stats(self) -> Optional[Dict[str, Any]]:
        """
        Get cache statistics for this repository.

        Returns:
            Cache statistics dictionary or None if cache not available
        """
        if not self.cache_service:
            return None

        stats = self.cache_service.get_stats()
        # Add repository-specific prefix
        stats["repository"] = self._cache_prefix
        return stats


def cached_method(ttl: Optional[int] = None, tier: str = "warm"):
    """
    Decorator to cache repository method results with proper SQLAlchemy serialization.

    Args:
        ttl: Time-to-live in seconds
        tier: Cache tier (hot/warm/cold/static)

    Usage:
        @cached_method(tier="hot")
        def get_instructor_bookings(self, instructor_id: int):
            return self.db.query(Booking)...
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            # Skip caching if disabled or no cache service
            if not getattr(self, "_cache_enabled", True) or not getattr(self, "cache_service", None):
                return func(self, *args, **kwargs)

            # Generate cache key
            cache_key = self._generate_cache_key(func.__name__, *args, **kwargs)

            # Try to get from cache
            try:
                cached_value = self.cache_service.get(cache_key)
                if cached_value is not None:
                    logger.debug(f"Cache hit for {func.__name__}: {cache_key}")
                    return cached_value
            except Exception as e:
                logger.error(f"Cache get error in {func.__name__}: {e}")

            # Execute function
            result = func(self, *args, **kwargs)

            # Cache the result (convert SQLAlchemy objects to dicts)
            if result is not None:
                try:
                    cache_data = self._serialize_for_cache(result)
                    self.cache_service.set(cache_key, cache_data, ttl=ttl, tier=tier)
                    logger.debug(f"Cached result for {func.__name__}: {cache_key}")
                except RecursionError as e:
                    logger.error(f"Recursion error during cache serialization in {func.__name__}: {e}")
                except Exception as e:
                    logger.error(f"Cache set error in {func.__name__}: {e}")

            return result

        return wrapper

    return decorator
