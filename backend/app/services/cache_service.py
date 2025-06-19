# backend/app/services/cache_service.py
"""
Dedicated Cache Service for InstaInstru Platform

Centralizes all caching logic with proper key management,
invalidation strategies, and performance monitoring.
"""

import hashlib
import json
import logging
import threading
from datetime import date, datetime, time, timedelta
from enum import Enum
from functools import wraps
from typing import Any, Callable, Dict, List, Optional, Union

import redis
from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy.orm import Session

from ..core.config import settings
from .base import BaseService

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject calls
    HALF_OPEN = "half_open"  # Testing if service recovered


class CircuitBreaker:
    """
    Circuit breaker pattern implementation for cache resilience.

    Prevents cascading failures when cache is unavailable.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        expected_exception: type = RedisError,
    ):
        """
        Initialize circuit breaker.

        Args:
            failure_threshold: Number of failures before opening circuit
            recovery_timeout: Seconds before attempting recovery
            expected_exception: Exception type to catch
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception

        self._failure_count = 0
        self._last_failure_time = None
        self._state = CircuitState.CLOSED
        self._lock = threading.Lock()

    @property
    def state(self) -> CircuitState:
        """Get current circuit state."""
        with self._lock:
            if self._state == CircuitState.OPEN:
                # Check if we should try half-open
                if self._last_failure_time:
                    time_since_failure = (datetime.now() - self._last_failure_time).total_seconds()
                    if time_since_failure >= self.recovery_timeout:
                        self._state = CircuitState.HALF_OPEN
            return self._state

    def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute function with circuit breaker protection.

        Args:
            func: Function to execute
            *args: Function arguments
            **kwargs: Function keyword arguments

        Returns:
            Function result or None if circuit is open

        Raises:
            Exception if function fails and circuit allows
        """
        if self.state == CircuitState.OPEN:
            logger.warning(f"Circuit breaker is OPEN, skipping {func.__name__}")
            return None

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except self.expected_exception as e:
            self._on_failure()
            if self.state == CircuitState.CLOSED:
                # Still under threshold, propagate error
                raise
            # Circuit is open, return None
            return None

    def _on_success(self):
        """Handle successful call."""
        with self._lock:
            self._failure_count = 0
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.CLOSED
                logger.info("Circuit breaker recovered, closing circuit")

    def _on_failure(self):
        """Handle failed call."""
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = datetime.now()

            if self._failure_count >= self.failure_threshold:
                self._state = CircuitState.OPEN
                logger.warning(f"Circuit breaker opened after {self._failure_count} failures")


class CacheKeyBuilder:
    """Standardized cache key generation."""

    # Key prefixes for different domains
    PREFIXES = {
        "availability": "avail",
        "booking": "book",
        "instructor": "inst",
        "service": "svc",
        "slot": "slot",
        "conflict": "con",
        "week": "week",
        "stats": "stats",
    }

    @staticmethod
    def build(*parts: Union[str, int, date]) -> str:
        """
        Build a cache key from parts.

        Examples:
            build('availability', 'week', 123, '2025-06-18') -> 'avail:week:123:2025-06-18'
        """
        formatted_parts = []

        for part in parts:
            if isinstance(part, date):
                formatted_parts.append(part.isoformat())
            elif isinstance(part, datetime):
                formatted_parts.append(part.isoformat())
            elif isinstance(part, time):
                formatted_parts.append(part.isoformat())
            else:
                formatted_parts.append(str(part))

        # Use prefix if first part is a known domain
        if parts and parts[0] in CacheKeyBuilder.PREFIXES:
            formatted_parts[0] = CacheKeyBuilder.PREFIXES[parts[0]]

        return ":".join(formatted_parts)

    @staticmethod
    def hash_complex_key(data: Dict[str, Any]) -> str:
        """Generate a hash for complex cache keys."""
        # Sort keys for consistency
        sorted_data = json.dumps(data, sort_keys=True, default=str)
        return hashlib.md5(sorted_data.encode()).hexdigest()[:12]


class CacheService(BaseService):
    """
    Centralized caching service with advanced features.

    Features:
    - Automatic serialization/deserialization
    - TTL management with different tiers
    - Batch operations
    - Cache warming
    - Invalidation patterns
    - Performance monitoring
    """

    # TTL Tiers (in seconds)
    TTL_TIERS = {
        "hot": 300,  # 5 minutes - frequently accessed
        "warm": 3600,  # 1 hour - moderate access
        "cold": 86400,  # 24 hours - infrequent access
        "static": 604800,  # 7 days - rarely changes
    }

    def __init__(self, db: Session, redis_client: Optional[Redis] = None):
        """Initialize cache service."""
        self.db = db
        self.logger = logging.getLogger(__name__)

        # Initialize circuit breaker
        self.circuit_breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=60)

        if redis_client:
            self.redis = redis_client
        else:
            try:
                self.redis = redis.from_url(
                    settings.redis_url or "redis://localhost:6379",
                    decode_responses=True,
                    socket_keepalive=True,
                    socket_connect_timeout=5,
                    retry_on_timeout=True,
                    health_check_interval=30,
                    # Connection pooling
                    max_connections=50,
                    connection_pool_class=redis.BlockingConnectionPool,
                )
                # Test connection
                self.redis.ping()
                logger.info("Connected to Redis/DragonflyDB")
            except (RedisError, ConnectionError) as e:
                logger.warning(f"Redis not available: {e}. Using in-memory fallback.")
                self.redis = None
                self._memory_cache = {}
                self._memory_expiry = {}

        self.key_builder = CacheKeyBuilder()
        self._stats = {
            "hits": 0,
            "misses": 0,
            "sets": 0,
            "deletes": 0,
            "errors": 0,
            "circuit_opens": 0,
        }

    # Core Cache Operations

    def get(self, key: str) -> Optional[Any]:
        """Get value from cache with circuit breaker protection."""

        def _get_from_redis():
            value = self.redis.get(key)
            if value is not None:
                return json.loads(value)
            return None

        try:
            if self.redis and self.circuit_breaker.state != CircuitState.OPEN:
                value = self.circuit_breaker.call(_get_from_redis)
                if value is not None:
                    self._stats["hits"] += 1
                    return value
            elif not self.redis:
                # In-memory fallback
                if key in self._memory_cache:
                    if key not in self._memory_expiry or datetime.now() < self._memory_expiry[key]:
                        self._stats["hits"] += 1
                        return self._memory_cache[key]
                    else:
                        # Expired
                        del self._memory_cache[key]
                        del self._memory_expiry[key]

            self._stats["misses"] += 1
            return None

        except Exception as e:
            logger.error(f"Cache get error for key {key}: {e}")
            self._stats["errors"] += 1
            return None

    def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
        tier: Optional[str] = "warm",
    ) -> bool:
        """Set value in cache with circuit breaker protection."""

        def _set_in_redis():
            self.redis.setex(key, ttl, serialized)
            return True

        try:
            # Use tier TTL if not specified
            if ttl is None:
                ttl = self.TTL_TIERS.get(tier, self.TTL_TIERS["warm"])

            serialized = json.dumps(value, default=str)

            if self.redis and self.circuit_breaker.state != CircuitState.OPEN:
                result = self.circuit_breaker.call(_set_in_redis)
                if result:
                    self._stats["sets"] += 1
                    return True
            elif not self.redis:
                # In-memory fallback
                self._memory_cache[key] = value
                self._memory_expiry[key] = datetime.now() + timedelta(seconds=ttl)
                self._stats["sets"] += 1
                return True

            return False

        except Exception as e:
            logger.error(f"Cache set error for key {key}: {e}")
            self._stats["errors"] += 1
            return False

    def delete(self, key: str) -> bool:
        """Delete a key from cache with circuit breaker protection."""

        def _delete_from_redis():
            return self.redis.delete(key) > 0

        try:
            if self.redis and self.circuit_breaker.state != CircuitState.OPEN:
                result = self.circuit_breaker.call(_delete_from_redis)
                if result:
                    self._stats["deletes"] += 1
                    return True
            elif not self.redis:
                result = key in self._memory_cache
                self._memory_cache.pop(key, None)
                self._memory_expiry.pop(key, None)
                if result:
                    self._stats["deletes"] += 1
                return result

            return False

        except Exception as e:
            logger.error(f"Cache delete error for key {key}: {e}")
            self._stats["errors"] += 1
            return False

    def delete_pattern(self, pattern: str) -> int:
        """Delete all keys matching pattern."""
        count = 0
        try:
            if self.redis:
                # Use SCAN for better performance
                for key in self.redis.scan_iter(match=pattern):
                    if self.redis.delete(key):
                        count += 1
            else:
                # In-memory pattern matching
                keys_to_delete = [k for k in self._memory_cache.keys() if self._match_pattern(k, pattern)]
                for key in keys_to_delete:
                    self._memory_cache.pop(key, None)
                    self._memory_expiry.pop(key, None)
                    count += 1

            self._stats["deletes"] += count
            logger.info(f"Deleted {count} keys matching pattern: {pattern}")
            return count

        except Exception as e:
            logger.error(f"Cache delete pattern error: {e}")
            self._stats["errors"] += 1
            return 0

    # Batch Operations

    def mget(self, keys: List[str]) -> Dict[str, Any]:
        """Get multiple keys at once."""
        result = {}

        try:
            if self.redis:
                values = self.redis.mget(keys)
                for key, value in zip(keys, values):
                    if value is not None:
                        result[key] = json.loads(value)
                        self._stats["hits"] += 1
                    else:
                        self._stats["misses"] += 1
            else:
                # In-memory
                for key in keys:
                    value = self.get(key)  # Reuse get logic
                    if value is not None:
                        result[key] = value

        except Exception as e:
            logger.error(f"Cache mget error: {e}")
            self._stats["errors"] += 1

        return result

    def mset(self, data: Dict[str, Any], ttl: int = None, tier: str = "warm") -> bool:
        """Set multiple keys at once."""
        try:
            if ttl is None:
                ttl = self.TTL_TIERS.get(tier, self.TTL_TIERS["warm"])

            if self.redis:
                # Serialize all values
                serialized_data = {k: json.dumps(v, default=str) for k, v in data.items()}

                # Use pipeline for atomic operation
                pipe = self.redis.pipeline()
                for key, value in serialized_data.items():
                    pipe.setex(key, ttl, value)
                pipe.execute()
            else:
                # In-memory
                for key, value in data.items():
                    self.set(key, value, ttl, tier)

            self._stats["sets"] += len(data)
            return True

        except Exception as e:
            logger.error(f"Cache mset error: {e}")
            self._stats["errors"] += 1
            return False

    # Domain-Specific Methods

    def cache_week_availability(self, instructor_id: int, week_start: date, availability_data: Dict[str, Any]) -> bool:
        """Cache week availability with smart TTL."""
        key = self.key_builder.build("availability", "week", instructor_id, week_start)

        # Use shorter TTL for current/future weeks
        if week_start >= date.today():
            tier = "hot"  # 5 minutes
        else:
            tier = "warm"  # 1 hour for past weeks

        return self.set(key, availability_data, tier=tier)

    def get_week_availability(self, instructor_id: int, week_start: date) -> Optional[Dict[str, Any]]:
        """Get cached week availability."""
        key = self.key_builder.build("availability", "week", instructor_id, week_start)
        return self.get(key)

    def invalidate_instructor_availability(self, instructor_id: int, dates: List[date] = None):
        """Invalidate all availability caches for an instructor."""
        patterns = [
            f"avail:*:{instructor_id}:*",
            f"week:*:{instructor_id}:*",
            f"conf:*:{instructor_id}:*",
        ]

        if dates:
            # Also invalidate specific dates
            for d in dates:
                patterns.extend(
                    [
                        f"*:{instructor_id}:{d.isoformat()}",
                        f"*:{instructor_id}:*:{d.isoformat()}",
                    ]
                )

        total_deleted = 0
        for pattern in patterns:
            total_deleted += self.delete_pattern(pattern)

        logger.info(f"Invalidated {total_deleted} cache entries for instructor {instructor_id}")

    def cache_booking_conflicts(
        self,
        instructor_id: int,
        check_date: date,
        start_time: time,
        end_time: time,
        conflicts: List[Dict[str, Any]],
    ) -> bool:
        """Cache booking conflict check results."""
        # Create complex key from parameters
        key_data = {
            "instructor_id": instructor_id,
            "date": check_date.isoformat(),
            "start": start_time.isoformat(),
            "end": end_time.isoformat(),
        }
        key_hash = self.key_builder.hash_complex_key(key_data)
        key = self.key_builder.build("conflict", instructor_id, check_date, key_hash)

        return self.set(key, conflicts, tier="hot")

    # Cache Warming

    async def warm_instructor_cache(self, instructor_id: int, weeks_ahead: int = 4):
        """Pre-populate cache for an instructor's upcoming weeks."""
        from ..services.availability_service import AvailabilityService

        availability_service = AvailabilityService(self.db)
        today = date.today()
        monday = today - timedelta(days=today.weekday())

        warmed = 0
        for week_offset in range(weeks_ahead):
            week_start = monday + timedelta(weeks=week_offset)

            # Get and cache availability
            availability = availability_service.get_week_availability(instructor_id, week_start)
            if availability:
                self.cache_week_availability(instructor_id, week_start, availability)
                warmed += 1

        logger.info(f"Warmed {warmed} weeks of cache for instructor {instructor_id}")
        return warmed

    # Decorators

    def cached(self, key_func: Callable[..., str], ttl: int = None, tier: str = "warm"):
        """
        Decorator for caching function results.

        Usage:
            @cache_service.cached(
                key_func=lambda self, user_id: f"user:profile:{user_id}",
                tier='warm'
            )
            def get_user_profile(self, user_id: int):
                return expensive_operation()
        """

        def decorator(func: Callable) -> Callable:
            @wraps(func)
            def wrapper(*args, **kwargs):
                # Generate cache key
                cache_key = key_func(*args, **kwargs)

                # Try cache first
                cached_value = self.get(cache_key)
                if cached_value is not None:
                    logger.debug(f"Cache hit for {func.__name__}: {cache_key}")
                    return cached_value

                # Execute function
                result = func(*args, **kwargs)

                # Cache result
                if result is not None:
                    self.set(cache_key, result, ttl=ttl, tier=tier)

                return result

            # Add cache invalidation helper
            wrapper.invalidate = lambda *args, **kwargs: self.delete(key_func(*args, **kwargs))

            return wrapper

        return decorator

    # Monitoring

    def get_stats(self) -> Dict[str, Any]:
        """Get cache performance statistics including circuit breaker state."""
        total_requests = self._stats["hits"] + self._stats["misses"]
        hit_rate = (self._stats["hits"] / total_requests * 100) if total_requests > 0 else 0

        stats = {
            **self._stats,
            "hit_rate": f"{hit_rate:.2f}%",
            "total_requests": total_requests,
            "circuit_breaker": {
                "state": self.circuit_breaker.state.value,
                "failure_count": self.circuit_breaker._failure_count,
                "threshold": self.circuit_breaker.failure_threshold,
            },
        }

        # Add Redis info if available and circuit is not open
        if self.redis and self.circuit_breaker.state != CircuitState.OPEN:
            try:
                info = self.redis.info()
                stats["redis"] = {
                    "used_memory_human": info.get("used_memory_human"),
                    "connected_clients": info.get("connected_clients"),
                    "total_commands_processed": info.get("total_commands_processed"),
                    "instantaneous_ops_per_sec": info.get("instantaneous_ops_per_sec"),
                }
            except:
                pass

        return stats

    def reset_stats(self):
        """Reset performance statistics."""
        self._stats = {"hits": 0, "misses": 0, "sets": 0, "deletes": 0, "errors": 0}

    # Helper methods

    def _match_pattern(self, key: str, pattern: str) -> bool:
        """Simple pattern matching for in-memory cache."""
        import fnmatch

        return fnmatch.fnmatch(key, pattern)


# Dependency injection
def get_cache_service(db: Session = None) -> CacheService:
    """
    Get cache service instance for dependency injection.

    Creates a singleton instance of CacheService with Redis/DragonflyDB
    connection if available, otherwise falls back to in-memory cache.

    Args:
        db: Optional database session

    Returns:
        CacheService: Singleton cache service instance
    """
    if not hasattr(get_cache_service, "_instance"):
        # Create singleton instance
        try:
            redis_client = redis.from_url(settings.redis_url or "redis://localhost:6379", decode_responses=True)
            redis_client.ping()
        except:
            redis_client = None

        get_cache_service._instance = CacheService(db or Session(), redis_client)

    return get_cache_service._instance
