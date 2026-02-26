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

import asyncio
from datetime import date, datetime, time, timedelta, timezone
from enum import Enum
from functools import wraps
import hashlib
import json
import logging
import os
import threading
from typing import (
    Any,
    Awaitable,
    Callable,
    Coroutine,
    Dict,
    List,
    Optional,
    ParamSpec,
    TypeVar,
    Union,
    cast,
)

from fastapi import Depends
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy.orm import Session

from app.middleware.perf_counters import (
    note_cache_hit,
    note_cache_miss,
    record_cache_key,
)

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
                    time_since_failure = (
                        datetime.now(timezone.utc) - self._last_failure_time
                    ).total_seconds()
                    if time_since_failure >= self.recovery_timeout:
                        self._state = CircuitState.HALF_OPEN
            return self._state

    async def call(
        self, func: Callable[..., Awaitable[T]], *args: Any, **kwargs: Any
    ) -> Optional[T]:
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
            result = await func(*args, **kwargs)
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
            self._last_failure_time = datetime.now(timezone.utc)

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
        return hashlib.md5(sorted_data.encode(), usedforsecurity=False).hexdigest()[:12]


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

    def __init__(self, db: Optional[Session] = None, redis_client: Optional[Redis] = None):
        """
        Initialize cache service.

        REFACTORED: Split initialization into helper methods to stay under 50 lines.

        Args:
            db: Optional database session. Not used by CacheService but required
                by BaseService for consistency with other services.
            redis_client: Optional Redis client. If not provided, will attempt
                to connect using REDIS_URL from settings.
        """
        super().__init__(db)
        self.logger = logging.getLogger(__name__)
        self.force_memory_cache = os.getenv("AVAILABILITY_TEST_MEMORY_CACHE") == "1"

        # Initialize components
        self.circuit_breaker = self._create_circuit_breaker()
        self.key_builder = CacheKeyBuilder()

        # In-memory fallbacks
        self._memory_cache: Dict[str, Any] = {}
        self._memory_expiry: Dict[str, datetime] = {}

        # Redis connection (async, shared pool via app.core.cache_redis)
        self.redis: Optional[Redis] = redis_client

        # Initialize statistics
        self._stats: Dict[str, int] = self._initialize_stats()

    def _create_circuit_breaker(self) -> CircuitBreaker:
        """Create and configure circuit breaker for resilience."""
        return CircuitBreaker(
            failure_threshold=5, recovery_timeout=60, expected_exception=RedisError
        )

    async def _get_redis_client(self) -> Optional[Redis]:
        """Return a shared async Redis client, or None when unavailable."""
        if self.force_memory_cache:
            return None

        # Allow explicit injection (tests/mocking) to override the shared pool.
        if self.redis is not None:
            return self.redis

        # Lazy init from the shared cache Redis pool (separate from messaging Pub/Sub Redis)
        try:
            from app.core.cache_redis import get_async_cache_redis_client

            # Do not cache the client on the CacheService instance: this service can be reused
            # across multiple event loops in tests, while the underlying async Redis client is
            # event-loop bound (cache_redis handles per-loop pooling).
            return await get_async_cache_redis_client()
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Redis client unavailable, using in-memory fallback: %s", exc)
            return None

    @BaseService.measure_operation("get_redis_client")
    async def get_redis_client(self) -> Optional[Redis]:
        """Public accessor for the underlying async Redis client (if available)."""
        return await self._get_redis_client()

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

    # Internal helpers -------------------------------------------------

    async def _backend_get(self, key: str) -> Optional[Any]:
        """Fetch raw value from the active backend without instrumentation."""
        redis_client = await self._get_redis_client()

        try:
            if redis_client and self.circuit_breaker.state != CircuitState.OPEN:

                async def _get_from_redis() -> Optional[Any]:
                    return await redis_client.get(key)

                return await self.circuit_breaker.call(_get_from_redis)

            if redis_client is None:
                cached = self._memory_cache.get(key)
                if cached is None:
                    return None

                expires_at = self._memory_expiry.get(key)
                if expires_at is None or datetime.now(timezone.utc) < expires_at:
                    return cached

                # Key expired in memory cache; clean up and treat as miss
                self._memory_cache.pop(key, None)
                self._memory_expiry.pop(key, None)
                return None

            return None

        except Exception as exc:  # pragma: no cover - defensive
            logger.error(f"Cache backend get error for key {key}: {exc}")
            self._stats["errors"] += 1
            return None

    async def _backend_set(self, key: str, value: Any, ttl: Optional[int]) -> bool:
        """Persist value to the active backend without serialization concerns."""
        redis_client = await self._get_redis_client()

        try:
            expiration = ttl if ttl is not None else self.TTL_TIERS.get("warm", 3600)
            if expiration is None:
                raise RuntimeError("Cache TTL missing for backend set")

            if redis_client and self.circuit_breaker.state != CircuitState.OPEN:

                async def _set_in_redis() -> bool:
                    await redis_client.setex(key, expiration, value)
                    return True

                result = await self.circuit_breaker.call(_set_in_redis)
                if result:
                    self._stats["sets"] += 1
                    return True
            elif redis_client is None:
                self._memory_cache[key] = value
                self._memory_expiry[key] = datetime.now(timezone.utc) + timedelta(
                    seconds=expiration
                )
                self._stats["sets"] += 1
                return True

            return False

        except Exception as exc:  # pragma: no cover - defensive
            logger.error(f"Cache backend set error for key {key}: {exc}")
            self._stats["errors"] += 1
            return False

    @BaseService.measure_operation("cache_get_json")
    async def get_json(self, key: str) -> Optional[Any]:
        """Fetch a JSON payload while routing through perf instrumentation."""
        record_cache_key(key)
        raw_value = await self._backend_get(key)
        if raw_value is None:
            self._stats["misses"] += 1
            note_cache_miss(key)
            return None

        self._stats["hits"] += 1
        note_cache_hit(key)

        if isinstance(raw_value, (bytes, str)):
            try:
                return json.loads(raw_value)
            except Exception:
                return raw_value

        return raw_value

    @BaseService.measure_operation("cache_set_json")
    async def set_json(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Persist a JSON-serializable payload uniformly for all backends."""
        payload = json.dumps(value, default=str)
        await self._backend_set(key, payload, ttl)

    # Core Cache Operations

    @BaseService.measure_operation("cache_get")
    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache with circuit breaker protection."""
        try:
            record_cache_key(key)
            raw_value = await self._backend_get(key)
            if raw_value is None:
                self._stats["misses"] += 1
                note_cache_miss(key)
                return None

            self._stats["hits"] += 1
            note_cache_hit(key)

            if isinstance(raw_value, (bytes, str)):
                try:
                    return json.loads(raw_value)
                except Exception:
                    return raw_value

            return raw_value

        except Exception as e:
            logger.error(f"Cache get error for key {key}: {e}")
            self._stats["errors"] += 1
            return None

    @BaseService.measure_operation("cache_set")
    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
        tier: str = "warm",
    ) -> bool:
        """Set value in cache with circuit breaker protection."""

        try:
            redis_client = await self._get_redis_client()

            # Use tier TTL if not specified
            if ttl is None:
                ttl = self.TTL_TIERS.get(tier, self.TTL_TIERS["warm"])

            if ttl is None:
                raise RuntimeError("Cache TTL missing for set")
            expiration = ttl
            serialized = json.dumps(value, default=str)

            if redis_client and self.circuit_breaker.state != CircuitState.OPEN:
                redis = redis_client

                async def _set_in_redis() -> bool:
                    await redis.setex(key, expiration, serialized)
                    return True

                result = await self.circuit_breaker.call(_set_in_redis)
                if result:
                    self._stats["sets"] += 1
                    return True
            elif redis_client is None:
                # In-memory fallback
                self._memory_cache[key] = value
                self._memory_expiry[key] = datetime.now(timezone.utc) + timedelta(
                    seconds=expiration
                )
                self._stats["sets"] += 1
                return True

            return False

        except Exception as e:
            logger.error(f"Cache set error for key {key}: {e}")
            self._stats["errors"] += 1
            return False

    @BaseService.measure_operation("cache_delete")
    async def delete(self, key: str) -> bool:
        """Delete a key from cache with circuit breaker protection."""

        redis_client = await self._get_redis_client()

        try:
            if redis_client and self.circuit_breaker.state != CircuitState.OPEN:

                async def _delete_from_redis() -> bool:
                    return bool(await redis_client.delete(key))

                result = await self.circuit_breaker.call(_delete_from_redis)
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
    async def delete_pattern(self, pattern: str) -> int:
        """
        Delete all keys matching pattern.

        REFACTORED: Split into helper methods to stay under 50 lines.
        """
        count = 0
        try:
            redis_client = await self._get_redis_client()
            if redis_client:
                count = await self._delete_pattern_redis(pattern)
            else:
                count = self._delete_pattern_memory(pattern)

            self._stats["deletes"] += count
            logger.info(f"Deleted {count} keys matching pattern: {pattern}")
            return count

        except Exception as e:
            logger.error(f"Cache delete pattern error: {e}")
            self._stats["errors"] += 1
            return 0

    @BaseService.measure_operation("cache_clear_prefix")
    async def clear_prefix(self, prefix: str) -> int:
        """
        Delete all keys that begin with the supplied prefix.

        Args:
            prefix: Cache key prefix (e.g., "catalog:services:")

        Returns:
            Number of keys removed.
        """
        if not prefix:
            return 0

        pattern = prefix if prefix.endswith("*") else f"{prefix}*"
        return await self.delete_pattern(pattern)

    async def _delete_pattern_redis(self, pattern: str) -> int:
        """Delete pattern from Redis using SCAN."""
        count = 0
        redis_client = await self._get_redis_client()
        if redis_client is None:
            return 0
        async for key in redis_client.scan_iter(match=pattern):
            if await redis_client.delete(key):
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

    # Lock Operations (for stampede protection)

    @BaseService.measure_operation("cache_acquire_lock")
    async def acquire_lock(self, key: str, ttl: int = 10) -> bool:
        """
        Acquire a distributed lock using Redis SETNX.

        Used for cache stampede protection - ensures only one request
        computes an expensive operation while others wait.

        Args:
            key: Lock key (typically "lock:{cache_key}")
            ttl: Lock expiry in seconds (default 10s safety)

        Returns:
            True if lock acquired, False if already held
        """
        redis_client = await self._get_redis_client()

        try:
            if redis_client and self.circuit_breaker.state != CircuitState.OPEN:
                # SET key value NX EX ttl - atomic set-if-not-exists with expiry
                result = await redis_client.set(key, "1", nx=True, ex=ttl)
                return bool(result)
            else:
                # In-memory fallback: use simple dict check with expiry
                now = datetime.now(timezone.utc)
                expires_at = self._memory_expiry.get(key)
                if expires_at is None or now >= expires_at:
                    # Lock is free or expired - acquire it
                    self._memory_cache[key] = "1"
                    self._memory_expiry[key] = now + timedelta(seconds=ttl)
                    return True
                return False

        except Exception as e:
            logger.error(f"Lock acquire error for key {key}: {e}")
            self._stats["errors"] += 1
            # On error, allow the request to proceed (fail-open)
            return True

    @BaseService.measure_operation("cache_release_lock")
    async def release_lock(self, key: str) -> bool:
        """
        Release a distributed lock.

        Args:
            key: Lock key to release

        Returns:
            True if lock was released, False otherwise
        """
        redis_client = await self._get_redis_client()

        try:
            if redis_client and self.circuit_breaker.state != CircuitState.OPEN:
                return bool(await redis_client.delete(key))
            else:
                # In-memory fallback
                self._memory_cache.pop(key, None)
                self._memory_expiry.pop(key, None)
                return True

        except Exception as e:
            logger.error(f"Lock release error for key {key}: {e}")
            self._stats["errors"] += 1
            return False

    # Batch Operations

    @BaseService.measure_operation("cache_mget")
    async def mget(self, keys: List[str]) -> Dict[str, Any]:
        """Get multiple keys at once."""
        result: Dict[str, Any] = {}
        redis_client = await self._get_redis_client()

        try:
            if redis_client:
                values = await redis_client.mget(keys)
                for key, value in zip(keys, values):
                    record_cache_key(key)
                    if value is not None:
                        try:
                            result[key] = json.loads(value)
                        except Exception:
                            result[key] = value
                        self._stats["hits"] += 1
                        note_cache_hit(key)
                    else:
                        self._stats["misses"] += 1
                        note_cache_miss(key)
            else:
                # In-memory
                for key in keys:
                    value = await self.get(key)  # Reuse get logic
                    if value is not None:
                        result[key] = value

        except Exception as e:
            logger.error(f"Cache mget error: {e}")
            self._stats["errors"] += 1

        return result

    @BaseService.measure_operation("cache_mset")
    async def mset(
        self, data: Dict[str, Any], ttl: Optional[int] = None, tier: str = "warm"
    ) -> bool:
        """Set multiple keys at once."""
        try:
            if ttl is None:
                ttl = self.TTL_TIERS.get(tier, self.TTL_TIERS["warm"])
            if ttl is None:
                raise RuntimeError("Cache TTL missing for mset")

            redis_client = await self._get_redis_client()
            if redis_client:
                # Serialize all values
                serialized_data = {k: json.dumps(v, default=str) for k, v in data.items()}

                # Use pipeline for atomic operation
                pipe = redis_client.pipeline()
                for key, value in serialized_data.items():
                    pipe.setex(key, ttl, value)
                await pipe.execute()
            else:
                # In-memory
                for key, value in data.items():
                    await self.set(key, value, ttl, tier)

            self._stats["sets"] += len(data)
            return True

        except Exception as e:
            logger.error(f"Cache mset error: {e}")
            self._stats["errors"] += 1
            return False

    # Domain-Specific Methods

    @BaseService.measure_operation("cache_week_availability")
    async def cache_week_availability(
        self, instructor_id: str, week_start: date, availability_data: Dict[str, Any]
    ) -> bool:
        """Cache week availability with smart TTL."""
        key = self.key_builder.build("availability", "week", instructor_id, week_start)

        # Use shorter TTL for current/future weeks
        if week_start >= datetime.now(timezone.utc).date():
            tier = "hot"  # 5 minutes
        else:
            tier = "warm"  # 1 hour for past weeks

        return await self.set(key, availability_data, tier=tier)

    @BaseService.measure_operation("get_week_availability")
    async def get_week_availability(
        self, instructor_id: str, week_start: date
    ) -> Optional[Dict[str, Any]]:
        """Get cached week availability."""
        key = self.key_builder.build("availability", "week", instructor_id, week_start)
        record_cache_key(key)
        result = cast(Optional[Dict[str, Any]], await self.get(key))

        # Track availability-specific metrics
        if result is not None:
            self._stats["availability_hits"] += 1
        else:
            self._stats["availability_misses"] += 1

        return result

    @BaseService.measure_operation("cache_instructor_availability_date_range")
    async def cache_instructor_availability_date_range(
        self,
        instructor_id: str,
        start_date: date,
        end_date: date,
        availability_data: List[Dict[str, Any]],
    ) -> bool:
        """Cache instructor availability for a date range with optimized TTL."""
        key = self.key_builder.build("availability", "range", instructor_id, start_date, end_date)

        # Use hot cache for current/future dates, warm for past
        if start_date >= datetime.now(timezone.utc).date():
            tier = "hot"  # 5 minutes
        else:
            tier = "warm"  # 1 hour

        return await self.set(key, availability_data, tier=tier)

    @BaseService.measure_operation("get_instructor_availability_date_range")
    async def get_instructor_availability_date_range(
        self, instructor_id: str, start_date: date, end_date: date
    ) -> Optional[List[Dict[str, Any]]]:
        """Get cached instructor availability for date range."""
        key = self.key_builder.build("availability", "range", instructor_id, start_date, end_date)
        result = cast(Optional[List[Dict[str, Any]]], await self.get(key))

        # Track availability-specific metrics
        if result is not None:
            self._stats["availability_hits"] += 1
        else:
            self._stats["availability_misses"] += 1

        return result

    @BaseService.measure_operation("cache_instructor_weekly_availability")
    async def cache_instructor_weekly_availability(
        self, instructor_id: str, weekly_data: Dict[str, List[Dict[str, Any]]]
    ) -> bool:
        """Cache instructor's weekly availability pattern with 5-minute TTL."""
        key = self.key_builder.build("availability", "weekly", instructor_id)
        return await self.set(key, weekly_data, tier="hot")  # 5 minutes

    @BaseService.measure_operation("get_instructor_weekly_availability")
    async def get_instructor_weekly_availability(
        self, instructor_id: str
    ) -> Optional[Dict[str, List[Dict[str, Any]]]]:
        """Get cached instructor weekly availability pattern."""
        key = self.key_builder.build("availability", "weekly", instructor_id)
        result = cast(Optional[Dict[str, List[Dict[str, Any]]]], await self.get(key))

        # Track availability-specific metrics
        if result is not None:
            self._stats["availability_hits"] += 1
        else:
            self._stats["availability_misses"] += 1

        return result

    @BaseService.measure_operation("batch_cache_availability")
    async def batch_cache_availability(self, availability_entries: List[Dict[str, Any]]) -> int:
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

        success = await self.mset(cache_data, tier="hot")
        return len(cache_data) if success else 0

    @BaseService.measure_operation("invalidate_instructor_availability")
    async def invalidate_instructor_availability(
        self, instructor_id: Union[int, str], dates: Optional[List[date]] = None
    ) -> None:
        """Invalidate all availability caches for an instructor."""
        patterns = [
            f"avail:*:{instructor_id}:*",
            f"week:*:{instructor_id}:*",
            f"con:*:{instructor_id}:*",  # Bug fix: was "conf:" but prefix is "con"
            # Always invalidate public availability for this instructor (any date range)
            f"public_availability:{instructor_id}:*",
        ]

        if dates:
            # Also invalidate specific date patterns
            for d in dates:
                patterns.extend(
                    [
                        f"*:{instructor_id}:{d.isoformat()}",
                        f"*:{instructor_id}:*:{d.isoformat()}",
                    ]
                )

        total_deleted = 0
        for pattern in patterns:
            total_deleted += await self.delete_pattern(pattern)

        # Track availability-specific invalidations
        self._stats["availability_invalidations"] += total_deleted

        logger.info(f"Invalidated {total_deleted} cache entries for instructor {instructor_id}")

    @BaseService.measure_operation("cache_booking_conflicts")
    async def cache_booking_conflicts(
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

        return await self.set(key, conflicts, tier="hot")

    # Cache Warming

    @BaseService.measure_operation("warm_instructor_cache")
    async def warm_instructor_cache(self, instructor_id: str, weeks_ahead: int = 4) -> int:
        """Pre-populate cache for an instructor's upcoming weeks."""
        from ..services.availability_service import AvailabilityService

        availability_service = AvailabilityService(self.db)
        today = datetime.now(timezone.utc).date()
        monday = today - timedelta(days=today.weekday())

        warmed = 0
        for week_offset in range(weeks_ahead):
            week_start = monday + timedelta(weeks=week_offset)

            # Get and cache availability
            availability = availability_service.get_week_availability(instructor_id, week_start)
            if availability:
                await self.cache_week_availability(instructor_id, week_start, availability)
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
    ) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
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

        def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
            @wraps(func)
            async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
                # Generate cache key
                cache_key = key_func(*args, **kwargs)

                # Try cache first
                cached_value = await self.get(cache_key)
                if cached_value is not None:
                    logger.debug(f"Cache hit for {func.__name__}: {cache_key}")
                    return cast(T, cached_value)

                # Execute function
                result = await func(*args, **kwargs)

                # Cache result
                if result is not None:
                    await self.set(cache_key, result, ttl=ttl, tier=tier)

                return result

            # Add cache invalidation helper
            async def invalidate(*args: P.args, **kwargs: P.kwargs) -> bool:
                return await self.delete(key_func(*args, **kwargs))

            setattr(wrapper, "invalidate", invalidate)

            return cast(Callable[P, Awaitable[T]], wrapper)

        return decorator

    # Monitoring

    @BaseService.measure_operation("get_cache_stats")
    async def get_stats(self) -> Dict[str, Any]:
        """
        Get cache performance statistics including circuit breaker state.

        REFACTORED: Split into helper methods to stay under 50 lines.
        """
        # Calculate basic stats
        stats = self._calculate_basic_stats()

        # Add circuit breaker info
        stats["circuit_breaker"] = self._get_circuit_breaker_stats()

        # Add Redis info if available
        redis_info = await self._get_redis_info()
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

    async def _get_redis_info(self) -> Optional[Dict[str, Any]]:
        """Get Redis server information if available."""
        redis_client = await self._get_redis_client()
        if redis_client and self.circuit_breaker.state != CircuitState.OPEN:
            try:
                info = await redis_client.info()
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


_cache_event_loop: asyncio.AbstractEventLoop | None = None
_cache_event_loop_thread_id: int | None = None


def set_cache_event_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Register the main event loop for sync-to-async cache bridging."""
    global _cache_event_loop, _cache_event_loop_thread_id
    _cache_event_loop = loop
    _cache_event_loop_thread_id = threading.get_ident()


_CT = TypeVar("_CT")


def _run_cache_coroutine(coro: Coroutine[Any, Any, _CT]) -> _CT:
    """
    Run a cache coroutine from sync code without blocking the main event loop.

    This is used only by CacheServiceSyncAdapter for sync call sites.
    """

    async def _runner() -> _CT:
        try:
            return await coro
        finally:
            try:
                from app.core.cache_redis import close_async_cache_redis_client

                await close_async_cache_redis_client()
            except Exception:
                logger.debug("Non-fatal error ignored", exc_info=True)

    loop = _cache_event_loop
    if loop is None or loop.is_closed():
        return asyncio.run(_runner())

    # Never block the event loop thread waiting on itself.
    if threading.get_ident() == _cache_event_loop_thread_id:
        coro.close()
        raise RuntimeError(
            "Sync cache operation called on the event loop thread; use `await CacheService.*` instead."
        )

    try:
        future = asyncio.run_coroutine_threadsafe(coro, loop)
    except Exception:
        # If scheduling failed (often because the loop is closing/closed), make sure we
        # don't leak an un-awaited coroutine.
        try:
            return asyncio.run(_runner())
        except Exception:
            coro.close()
            raise
    return future.result()


def clear_cache_event_loop() -> None:
    """Clear the registered event loop for sync-to-async cache bridging (tests/shutdown)."""
    global _cache_event_loop, _cache_event_loop_thread_id
    _cache_event_loop = None
    _cache_event_loop_thread_id = None


class CacheServiceSyncAdapter:
    """
    Synchronous adapter over CacheService for sync call sites.

    Redis operations remain async (redis.asyncio) and execute on the main event loop,
    while sync callers block only their worker thread.
    """

    TTL_TIERS = CacheService.TTL_TIERS

    def __init__(self, cache_service: CacheService):
        self._cache_service = cache_service
        self.key_builder = cache_service.key_builder

    @staticmethod
    def _is_event_loop_thread() -> bool:
        try:
            asyncio.get_running_loop()
            return True
        except RuntimeError:
            pass

        loop = _cache_event_loop
        return loop is not None and threading.get_ident() == _cache_event_loop_thread_id

    def get(self, key: str) -> Optional[Any]:
        if self._is_event_loop_thread():
            return None
        return _run_cache_coroutine(self._cache_service.get(key))

    def set(self, key: str, value: Any, ttl: Optional[int] = None, tier: str = "warm") -> bool:
        if self._is_event_loop_thread():
            return False
        return _run_cache_coroutine(self._cache_service.set(key, value, ttl=ttl, tier=tier))

    def delete(self, key: str) -> bool:
        if self._is_event_loop_thread():
            return False
        return _run_cache_coroutine(self._cache_service.delete(key))

    def delete_pattern(self, pattern: str) -> int:
        if self._is_event_loop_thread():
            return 0
        return _run_cache_coroutine(self._cache_service.delete_pattern(pattern))

    def clear_prefix(self, prefix: str) -> int:
        if self._is_event_loop_thread():
            return 0
        return _run_cache_coroutine(self._cache_service.clear_prefix(prefix))

    def get_stats(self) -> Dict[str, Any]:
        if self._is_event_loop_thread():
            return {}
        return _run_cache_coroutine(self._cache_service.get_stats())

    def get_json(self, key: str) -> Optional[Any]:
        if self._is_event_loop_thread():
            return None
        return _run_cache_coroutine(self._cache_service.get_json(key))

    def set_json(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        if self._is_event_loop_thread():
            return
        _run_cache_coroutine(self._cache_service.set_json(key, value, ttl=ttl))

    def cache_week_availability(
        self, instructor_id: str, week_start: date, availability_data: Dict[str, Any]
    ) -> bool:
        if self._is_event_loop_thread():
            return False
        return _run_cache_coroutine(
            self._cache_service.cache_week_availability(
                instructor_id, week_start, availability_data
            )
        )

    def get_instructor_availability_date_range(
        self, instructor_id: str, start_date: date, end_date: date
    ) -> Optional[List[Dict[str, Any]]]:
        if self._is_event_loop_thread():
            return None
        return _run_cache_coroutine(
            self._cache_service.get_instructor_availability_date_range(
                instructor_id, start_date, end_date
            )
        )

    def cache_instructor_availability_date_range(
        self,
        instructor_id: str,
        start_date: date,
        end_date: date,
        availability_data: List[Dict[str, Any]],
    ) -> bool:
        if self._is_event_loop_thread():
            return False
        return _run_cache_coroutine(
            self._cache_service.cache_instructor_availability_date_range(
                instructor_id, start_date, end_date, availability_data
            )
        )

    def invalidate_instructor_availability(
        self, instructor_id: str, dates: Optional[List[date]] = None
    ) -> None:
        if self._is_event_loop_thread():
            # Bug fix: Instead of silently skipping, schedule as fire-and-forget task
            try:
                loop = asyncio.get_running_loop()
                coro = self._cache_service.invalidate_instructor_availability(instructor_id, dates)
                task: asyncio.Task[None] = loop.create_task(coro)

                def _log_error(t: asyncio.Task[None]) -> None:
                    if t.cancelled():
                        return
                    exc = t.exception()
                    if exc:
                        logger.warning(
                            f"Async cache invalidation failed for {instructor_id}: {exc}"
                        )

                task.add_done_callback(_log_error)
            except RuntimeError:
                # No running loop available - skip gracefully
                logger.debug(f"No event loop for cache invalidation: instructor {instructor_id}")
            return
        _run_cache_coroutine(
            self._cache_service.invalidate_instructor_availability(instructor_id, dates)
        )


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
    return CacheService(db)


async def get_healthcheck_redis_client() -> Optional[Redis]:
    """Return the shared async Redis client for readiness checks."""
    try:
        from app.core.cache_redis import get_async_cache_redis_client

        return await get_async_cache_redis_client()
    except Exception:
        return None
