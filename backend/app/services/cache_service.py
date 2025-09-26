# backend/app/services/cache_service.py
"""
Dedicated Cache Service for InstaInstru Platform

Centralizes all caching logic with proper key management,
invalidation strategies, and performance monitoring.

UPDATED IN v65:
- Removed singleton pattern for proper dependency injection
- Added performance metrics to all 22 public methods
- Refactored long methods to stay under 50 lines
Now monitoring all cache operations to optimize energy usage! ⚡
"""

from datetime import date, datetime, time, timedelta
from enum import Enum
from functools import wraps
import hashlib
import json
import logging
import threading
from typing import Any, Callable, Dict, List, Optional, ParamSpec, TypeVar, Union, cast

from fastapi import Depends
import redis
from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy.orm import Session

from ..core.config import settings
from ..database import get_db
from .base import BaseService

logger = logging.getLogger(__name__)


T = TypeVar("T")
P = ParamSpec("P")


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
        expected_exception: type[BaseException] = RedisError,
    ) -> None:
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

        self._failure_count: int = 0
        self._last_failure_time: Optional[datetime] = None
        self._state: CircuitState = CircuitState.CLOSED
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

    def call(self, func: Callable[..., T], *args: Any, **kwargs: Any) -> Optional[T]:
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
        except self.expected_exception:
            self._on_failure()
            if self.state == CircuitState.CLOSED:
                # Still under threshold, propagate error
                raise
            # Circuit is open, return None
            return None

    def _on_success(self) -> None:
        """Handle successful call."""
        with self._lock:
            self._failure_count = 0
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.CLOSED
                logger.info("Circuit breaker recovered, closing circuit")

    def _on_failure(self) -> None:
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
        if parts:
            first = parts[0]
            if isinstance(first, str) and first in CacheKeyBuilder.PREFIXES:
                formatted_parts[0] = CacheKeyBuilder.PREFIXES[first]

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

    REFACTORED: No more singleton pattern - uses proper dependency injection.
    """

    # TTL Tiers (in seconds)
    TTL_TIERS = {
        "hot": 300,  # 5 minutes - frequently accessed
        "warm": 3600,  # 1 hour - moderate access
        "cold": 86400,  # 24 hours - infrequent access
        "static": 604800,  # 7 days - rarely changes
    }

    def __init__(self, db: Session, redis_client: Optional[Redis] = None):
        """
        Initialize cache service.

        REFACTORED: Split initialization into helper methods to stay under 50 lines.
        """
        super().__init__(db)
        self.logger = logging.getLogger(__name__)

        # Initialize components
        self.circuit_breaker = self._create_circuit_breaker()
        self.key_builder = CacheKeyBuilder()

        # In-memory fallbacks
        self._memory_cache: Dict[str, Any] = {}
        self._memory_expiry: Dict[str, datetime] = {}

        # Initialize Redis connection
        self.redis: Optional[Redis] = redis_client
        self._setup_redis_connection()

        # Initialize statistics
        self._stats: Dict[str, int] = self._initialize_stats()

    def _create_circuit_breaker(self) -> CircuitBreaker:
        """Create and configure circuit breaker for resilience."""
        return CircuitBreaker(
            failure_threshold=5, recovery_timeout=60, expected_exception=RedisError
        )

    def _setup_redis_connection(self) -> None:
        """Setup Redis connection with fallback to in-memory cache."""
        if self.redis is None:
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
                )
                # Test connection
                self.redis.ping()
                logger.info("Connected to Redis/DragonflyDB")
            except (RedisError, ConnectionError) as e:
                logger.warning(f"Redis not available: {e}. Using in-memory fallback.")
                self.redis = None
                self._memory_cache.clear()
                self._memory_expiry.clear()

    def _initialize_stats(self) -> Dict[str, int]:
        """Initialize cache statistics tracking."""
        return {
            "hits": 0,
            "misses": 0,
            "sets": 0,
            "deletes": 0,
            "errors": 0,
            "circuit_opens": 0,
            "availability_hits": 0,
            "availability_misses": 0,
            "availability_invalidations": 0,
        }

    # Core Cache Operations

    @BaseService.measure_operation("cache_get")
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache with circuit breaker protection."""

        redis_client = self.redis

        def _get_from_redis() -> Optional[Any]:
            assert redis_client is not None
            value = redis_client.get(key)
            if value is not None:
                return json.loads(value)
            return None

        try:
            if redis_client and self.circuit_breaker.state != CircuitState.OPEN:
                value = self.circuit_breaker.call(_get_from_redis)
                if value is not None:
                    self._stats["hits"] += 1
                    return value
            elif redis_client is None:
                # In-memory fallback
                if key in self._memory_cache:
                    expires_at = self._memory_expiry.get(key)
                    if expires_at is None or datetime.now() < expires_at:
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

    @BaseService.measure_operation("cache_set")
    def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
        tier: str = "warm",
    ) -> bool:
        """Set value in cache with circuit breaker protection."""

        redis_client = self.redis

        def _set_in_redis() -> bool:
            assert redis_client is not None
            redis_client.setex(key, ttl, serialized)
            return True

        try:
            # Use tier TTL if not specified
            if ttl is None:
                ttl = self.TTL_TIERS.get(tier, self.TTL_TIERS["warm"])

            serialized = json.dumps(value, default=str)

            if redis_client and self.circuit_breaker.state != CircuitState.OPEN:
                result = self.circuit_breaker.call(_set_in_redis)
                if result:
                    self._stats["sets"] += 1
                    return True
            elif redis_client is None:
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

    @BaseService.measure_operation("cache_delete")
    def delete(self, key: str) -> bool:
        """Delete a key from cache with circuit breaker protection."""

        redis_client = self.redis

        def _delete_from_redis() -> bool:
            assert redis_client is not None
            return bool(redis_client.delete(key))

        try:
            if redis_client and self.circuit_breaker.state != CircuitState.OPEN:
                result = self.circuit_breaker.call(_delete_from_redis)
                if result:
                    self._stats["deletes"] += 1
                    return True
            elif redis_client is None:
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

    @BaseService.measure_operation("cache_delete_pattern")
    def delete_pattern(self, pattern: str) -> int:
        """
        Delete all keys matching pattern.

        REFACTORED: Split into helper methods to stay under 50 lines.
        """
        count = 0
        try:
            if self.redis:
                count = self._delete_pattern_redis(pattern)
            else:
                count = self._delete_pattern_memory(pattern)

            self._stats["deletes"] += count
            logger.info(f"Deleted {count} keys matching pattern: {pattern}")
            return count

        except Exception as e:
            logger.error(f"Cache delete pattern error: {e}")
            self._stats["errors"] += 1
            return 0

    def _delete_pattern_redis(self, pattern: str) -> int:
        """Delete pattern from Redis using SCAN."""
        count = 0
        redis_client = self.redis
        if redis_client is None:
            return 0
        for key in redis_client.scan_iter(match=pattern):
            if redis_client.delete(key):
                count += 1
        return count

    def _delete_pattern_memory(self, pattern: str) -> int:
        """Delete pattern from in-memory cache."""
        count = 0
        keys_to_delete = [k for k in self._memory_cache.keys() if self._match_pattern(k, pattern)]
        for key in keys_to_delete:
            self._memory_cache.pop(key, None)
            self._memory_expiry.pop(key, None)
            count += 1
        return count

    # Batch Operations

    @BaseService.measure_operation("cache_mget")
    def mget(self, keys: List[str]) -> Dict[str, Any]:
        """Get multiple keys at once."""
        result: Dict[str, Any] = {}
        redis_client = self.redis

        try:
            if redis_client:
                values = redis_client.mget(keys)
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

    @BaseService.measure_operation("cache_mset")
    def mset(self, data: Dict[str, Any], ttl: Optional[int] = None, tier: str = "warm") -> bool:
        """Set multiple keys at once."""
        try:
            if ttl is None:
                ttl = self.TTL_TIERS.get(tier, self.TTL_TIERS["warm"])

            redis_client = self.redis
            if redis_client:
                # Serialize all values
                serialized_data = {k: json.dumps(v, default=str) for k, v in data.items()}

                # Use pipeline for atomic operation
                pipe = redis_client.pipeline()
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

    @BaseService.measure_operation("cache_week_availability")
    def cache_week_availability(
        self, instructor_id: str, week_start: date, availability_data: Dict[str, Any]
    ) -> bool:
        """Cache week availability with smart TTL."""
        key = self.key_builder.build("availability", "week", instructor_id, week_start)

        # Use shorter TTL for current/future weeks
        if week_start >= date.today():
            tier = "hot"  # 5 minutes
        else:
            tier = "warm"  # 1 hour for past weeks

        return self.set(key, availability_data, tier=tier)

    @BaseService.measure_operation("get_week_availability")
    def get_week_availability(
        self, instructor_id: str, week_start: date
    ) -> Optional[Dict[str, Any]]:
        """Get cached week availability."""
        key = self.key_builder.build("availability", "week", instructor_id, week_start)
        result = self.get(key)

        # Track availability-specific metrics
        if result is not None:
            self._stats["availability_hits"] += 1
        else:
            self._stats["availability_misses"] += 1

        return result

    @BaseService.measure_operation("cache_instructor_availability_date_range")
    def cache_instructor_availability_date_range(
        self,
        instructor_id: str,
        start_date: date,
        end_date: date,
        availability_data: List[Dict[str, Any]],
    ) -> bool:
        """Cache instructor availability for a date range with optimized TTL."""
        key = self.key_builder.build("availability", "range", instructor_id, start_date, end_date)

        # Use hot cache for current/future dates, warm for past
        if start_date >= date.today():
            tier = "hot"  # 5 minutes
        else:
            tier = "warm"  # 1 hour

        return self.set(key, availability_data, tier=tier)

    @BaseService.measure_operation("get_instructor_availability_date_range")
    def get_instructor_availability_date_range(
        self, instructor_id: str, start_date: date, end_date: date
    ) -> Optional[List[Dict[str, Any]]]:
        """Get cached instructor availability for date range."""
        key = self.key_builder.build("availability", "range", instructor_id, start_date, end_date)
        result = self.get(key)

        # Track availability-specific metrics
        if result is not None:
            self._stats["availability_hits"] += 1
        else:
            self._stats["availability_misses"] += 1

        return result

    @BaseService.measure_operation("cache_instructor_weekly_availability")
    def cache_instructor_weekly_availability(
        self, instructor_id: str, weekly_data: Dict[str, List[Dict[str, Any]]]
    ) -> bool:
        """Cache instructor's weekly availability pattern with 5-minute TTL."""
        key = self.key_builder.build("availability", "weekly", instructor_id)
        return self.set(key, weekly_data, tier="hot")  # 5 minutes

    @BaseService.measure_operation("get_instructor_weekly_availability")
    def get_instructor_weekly_availability(
        self, instructor_id: str
    ) -> Optional[Dict[str, List[Dict[str, Any]]]]:
        """Get cached instructor weekly availability pattern."""
        key = self.key_builder.build("availability", "weekly", instructor_id)
        result = self.get(key)

        # Track availability-specific metrics
        if result is not None:
            self._stats["availability_hits"] += 1
        else:
            self._stats["availability_misses"] += 1

        return result

    @BaseService.measure_operation("batch_cache_availability")
    def batch_cache_availability(self, availability_entries: List[Dict[str, Any]]) -> int:
        """Batch cache multiple availability entries for performance."""
        cache_data: Dict[str, Any] = {}

        for entry in availability_entries:
            instructor_id = entry["instructor_id"]
            if "week_start" in entry:
                # Week availability
                key = self.key_builder.build(
                    "availability", "week", instructor_id, entry["week_start"]
                )
                cache_data[key] = entry["data"]
            elif "start_date" in entry and "end_date" in entry:
                # Date range availability
                key = self.key_builder.build(
                    "availability", "range", instructor_id, entry["start_date"], entry["end_date"]
                )
                cache_data[key] = entry["data"]

        if not cache_data:
            return 0

        success = self.mset(cache_data, tier="hot")
        return len(cache_data) if success else 0

    @BaseService.measure_operation("invalidate_instructor_availability")
    def invalidate_instructor_availability(
        self, instructor_id: Union[int, str], dates: Optional[List[date]] = None
    ) -> None:
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
                        # Also invalidate public availability endpoints that include this date
                        f"public_availability:{instructor_id}:{d.isoformat()}:*",
                        f"public_availability:{instructor_id}:*:{d.isoformat()}:*",
                    ]
                )

        total_deleted = 0
        for pattern in patterns:
            total_deleted += self.delete_pattern(pattern)

        # Track availability-specific invalidations
        self._stats["availability_invalidations"] += total_deleted

        logger.info(f"Invalidated {total_deleted} cache entries for instructor {instructor_id}")

    @BaseService.measure_operation("cache_booking_conflicts")
    def cache_booking_conflicts(
        self,
        instructor_id: str,
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

    @BaseService.measure_operation("warm_instructor_cache")
    async def warm_instructor_cache(self, instructor_id: str, weeks_ahead: int = 4) -> int:
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

    @BaseService.measure_operation("cached_decorator")
    def cached(
        self,
        key_func: Callable[P, str],
        ttl: Optional[int] = None,
        tier: str = "warm",
    ) -> Callable[[Callable[P, T]], Callable[P, T]]:
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

        def decorator(func: Callable[P, T]) -> Callable[P, T]:
            @wraps(func)
            def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
                # Generate cache key
                cache_key = key_func(*args, **kwargs)

                # Try cache first
                cached_value = self.get(cache_key)
                if cached_value is not None:
                    logger.debug(f"Cache hit for {func.__name__}: {cache_key}")
                    return cast(T, cached_value)

                # Execute function
                result = func(*args, **kwargs)

                # Cache result
                if result is not None:
                    self.set(cache_key, result, ttl=ttl, tier=tier)

                return result

            # Add cache invalidation helper
            def invalidate(*args: P.args, **kwargs: P.kwargs) -> bool:
                return self.delete(key_func(*args, **kwargs))

            setattr(wrapper, "invalidate", invalidate)

            return cast(Callable[P, T], wrapper)

        return decorator

    # Monitoring

    @BaseService.measure_operation("get_cache_stats")
    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache performance statistics including circuit breaker state.

        REFACTORED: Split into helper methods to stay under 50 lines.
        """
        # Calculate basic stats
        stats = self._calculate_basic_stats()

        # Add circuit breaker info
        stats["circuit_breaker"] = self._get_circuit_breaker_stats()

        # Add Redis info if available
        redis_info = self._get_redis_info()
        if redis_info:
            stats["redis"] = redis_info

        return stats

    def _calculate_basic_stats(self) -> Dict[str, Any]:
        """Calculate basic cache statistics."""
        total_requests = self._stats["hits"] + self._stats["misses"]
        hit_rate = (self._stats["hits"] / total_requests * 100) if total_requests > 0 else 0

        return {
            **self._stats,
            "hit_rate": f"{hit_rate:.2f}%",
            "total_requests": total_requests,
        }

    def _get_circuit_breaker_stats(self) -> Dict[str, Any]:
        """Get circuit breaker statistics."""
        return {
            "state": self.circuit_breaker.state.value,
            "failure_count": self.circuit_breaker._failure_count,
            "threshold": self.circuit_breaker.failure_threshold,
        }

    def _get_redis_info(self) -> Optional[Dict[str, Any]]:
        """Get Redis server information if available."""
        redis_client = self.redis
        if redis_client and self.circuit_breaker.state != CircuitState.OPEN:
            try:
                info = redis_client.info()
                return {
                    "used_memory_human": info.get("used_memory_human"),
                    "connected_clients": info.get("connected_clients"),
                    "total_commands_processed": info.get("total_commands_processed"),
                    "instantaneous_ops_per_sec": info.get("instantaneous_ops_per_sec"),
                }
            except RedisError:
                return None
        return None

    @BaseService.measure_operation("reset_cache_stats")
    def reset_stats(self) -> None:
        """Reset performance statistics."""
        self._stats = self._initialize_stats()

    # Helper methods

    def _match_pattern(self, key: str, pattern: str) -> bool:
        """Simple pattern matching for in-memory cache."""
        import fnmatch

        return fnmatch.fnmatch(key, pattern)


# Dependency injection - NO MORE SINGLETON!
def get_cache_service(db: Session = Depends(get_db)) -> CacheService:
    """
    Get cache service instance for dependency injection.

    REFACTORED: No more singleton pattern! Creates a new instance each time
    with proper Redis connection handling. Uses FastAPI's dependency injection
    to manage instance lifecycle.

    Args:
        db: Database session from FastAPI dependency

    Returns:
        CacheService: Fresh cache service instance
    """
    try:
        redis_client = redis.from_url(
            settings.redis_url or "redis://localhost:6379", decode_responses=True
        )
        redis_client.ping()
    except:
        redis_client = None
        logger.warning("Redis not available, using in-memory cache fallback")

    return CacheService(db, redis_client)
