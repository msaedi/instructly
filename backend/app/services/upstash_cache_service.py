# backend/app/services/upstash_cache_service.py
"""
Upstash-optimized cache service extension.

This module provides Upstash-specific optimizations including:
- Automatic command pipelining for reduced latency
- Optimized serialization using msgpack
- Request coalescing to minimize API calls
- Cost-aware caching strategies
"""

import asyncio
import logging
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

import msgpack
import redis.asyncio as redis

from ..core.config import settings
from .cache_service import CacheService

logger = logging.getLogger(__name__)


class UpstashOptimizedCache:
    """
    Upstash-specific cache optimizations.

    Features:
    - Automatic request batching/pipelining
    - Msgpack serialization for smaller payloads
    - Cost-aware TTL management
    - Request coalescing
    """

    def __init__(self, redis_url: str, max_pipeline_size: int = 50, pipeline_timeout_ms: int = 10):
        """Initialize Upstash-optimized cache."""
        self.redis_url = redis_url
        self.max_pipeline_size = max_pipeline_size
        self.pipeline_timeout_ms = pipeline_timeout_ms

        # Pending operations for batching
        self._pending_gets: Dict[str, List[asyncio.Future]] = defaultdict(list)
        self._pending_sets: List[Tuple[str, Any, int]] = []
        self._pipeline_lock = asyncio.Lock()
        self._pipeline_timer = None

        # Metrics
        self._metrics = {
            "pipeline_executions": 0,
            "commands_batched": 0,
            "bytes_saved": 0,
            "coalesced_requests": 0,
        }

    async def get_connection(self) -> redis.Redis:
        """Get optimized Redis connection for Upstash."""
        return await redis.from_url(
            self.redis_url,
            encoding="utf-8",
            decode_responses=False,  # We'll handle decoding with msgpack
            socket_keepalive=True,
            socket_keepalive_options={
                1: 1,  # TCP_KEEPIDLE
                2: 1,  # TCP_KEEPINTVL
                3: 3,  # TCP_KEEPCNT
            },
            retry_on_timeout=True,
            retry_on_error=[ConnectionError, TimeoutError],
            max_connections=10,  # Limited for Upstash
        )

    def _serialize(self, value: Any) -> bytes:
        """Serialize using msgpack for smaller payloads."""
        try:
            serialized = msgpack.packb(value, use_bin_type=True)
            # Track compression savings
            json_size = len(str(value).encode())
            msgpack_size = len(serialized)
            self._metrics["bytes_saved"] += max(0, json_size - msgpack_size)
            return serialized
        except Exception:
            # Fallback to JSON
            import json

            return json.dumps(value, default=str).encode()

    def _deserialize(self, data: bytes) -> Any:
        """Deserialize msgpack data."""
        if not data:
            return None
        try:
            return msgpack.unpackb(data, raw=False)
        except Exception:
            # Fallback to JSON
            import json

            return json.loads(data.decode())

    async def get_with_coalescing(self, key: str) -> Optional[Any]:
        """
        Get with request coalescing.

        Multiple simultaneous requests for the same key will be coalesced
        into a single Redis call.
        """
        # Check if there's already a pending request for this key
        async with self._pipeline_lock:
            if key in self._pending_gets:
                # Coalesce with existing request
                future = asyncio.Future()
                self._pending_gets[key].append(future)
                self._metrics["coalesced_requests"] += 1
                return await future

            # First request for this key
            future = asyncio.Future()
            self._pending_gets[key] = [future]

        try:
            # Execute the actual get
            conn = await self.get_connection()
            value = await conn.get(key)
            result = self._deserialize(value) if value else None

            # Resolve all waiting futures
            async with self._pipeline_lock:
                for f in self._pending_gets[key]:
                    if not f.done():
                        f.set_result(result)
                del self._pending_gets[key]

            return result
        except Exception as e:
            # Resolve with error
            async with self._pipeline_lock:
                for f in self._pending_gets.get(key, []):
                    if not f.done():
                        f.set_exception(e)
                self._pending_gets.pop(key, None)
            raise

    async def set_with_batching(self, key: str, value: Any, ttl: int = 300) -> bool:
        """
        Set with automatic batching.

        Operations are collected and executed in batches to reduce
        round trips to Upstash.
        """
        async with self._pipeline_lock:
            self._pending_sets.append((key, value, ttl))

            # Start timer if not already running
            if self._pipeline_timer is None:
                self._pipeline_timer = asyncio.create_task(self._flush_pipeline_timer())

            # Flush immediately if batch is full
            if len(self._pending_sets) >= self.max_pipeline_size:
                await self._flush_pipeline()

        return True

    async def _flush_pipeline_timer(self):
        """Timer to flush pipeline after timeout."""
        await asyncio.sleep(self.pipeline_timeout_ms / 1000.0)
        async with self._pipeline_lock:
            await self._flush_pipeline()

    async def _flush_pipeline(self):
        """Execute all pending operations in a pipeline."""
        if not self._pending_sets:
            return

        try:
            conn = await self.get_connection()
            async with conn.pipeline(transaction=False) as pipe:
                # Add all pending sets
                for key, value, ttl in self._pending_sets:
                    serialized = self._serialize(value)
                    await pipe.setex(key, ttl, serialized)

                # Execute pipeline
                await pipe.execute()

                # Update metrics
                self._metrics["pipeline_executions"] += 1
                self._metrics["commands_batched"] += len(self._pending_sets)

            # Clear pending operations
            self._pending_sets.clear()
            self._pipeline_timer = None

        except Exception as e:
            logger.error(f"Pipeline execution failed: {e}")
            # Clear pending to avoid memory leak
            self._pending_sets.clear()
            self._pipeline_timer = None
            raise

    async def mget_optimized(self, keys: List[str]) -> Dict[str, Any]:
        """Optimized mget with deduplication and result caching."""
        if not keys:
            return {}

        # Deduplicate keys
        unique_keys = list(set(keys))

        conn = await self.get_connection()
        values = await conn.mget(unique_keys)

        result = {}
        for key, value in zip(unique_keys, values):
            if value is not None:
                result[key] = self._deserialize(value)

        return result

    def get_metrics(self) -> Dict[str, Any]:
        """Get Upstash optimization metrics."""
        return {
            **self._metrics,
            "avg_commands_per_pipeline": (
                self._metrics["commands_batched"] / self._metrics["pipeline_executions"]
                if self._metrics["pipeline_executions"] > 0
                else 0
            ),
            "bytes_saved_mb": round(self._metrics["bytes_saved"] / 1024 / 1024, 2),
        }


class UpstashCacheService(CacheService):
    """
    Extended cache service with Upstash-specific optimizations.

    This service extends the base CacheService with features specifically
    optimized for Upstash's serverless Redis architecture.
    """

    def __init__(self, *args, **kwargs):
        """Initialize with Upstash optimizations."""
        super().__init__(*args, **kwargs)

        # Initialize Upstash optimizer if using Upstash
        if self._is_upstash():
            self.upstash = UpstashOptimizedCache(
                redis_url=settings.redis_url or "redis://localhost:6379", max_pipeline_size=50, pipeline_timeout_ms=10
            )
        else:
            self.upstash = None

    def _is_upstash(self) -> bool:
        """Check if we're using Upstash Redis."""
        redis_url = settings.redis_url or ""
        return "upstash" in redis_url.lower()

    async def get_async(self, key: str) -> Optional[Any]:
        """Async get with Upstash optimizations."""
        if self.upstash:
            return await self.upstash.get_with_coalescing(key)
        else:
            # Fallback to sync get
            return self.get(key)

    async def set_async(self, key: str, value: Any, ttl: int = None, tier: str = "warm") -> bool:
        """Async set with Upstash batching."""
        if ttl is None:
            ttl = self.TTL_TIERS.get(tier, self.TTL_TIERS["warm"])

        if self.upstash:
            return await self.upstash.set_with_batching(key, value, ttl)
        else:
            # Fallback to sync set
            return self.set(key, value, ttl, tier)

    async def mget_async(self, keys: List[str]) -> Dict[str, Any]:
        """Async mget with Upstash optimizations."""
        if self.upstash:
            return await self.upstash.mget_optimized(keys)
        else:
            # Fallback to sync mget
            return self.mget(keys)

    def get_extended_stats(self) -> Dict[str, Any]:
        """Get stats including Upstash-specific metrics."""
        base_stats = self.get_stats()

        if self.upstash:
            base_stats["upstash_metrics"] = self.upstash.get_metrics()

        return base_stats


# Cost-aware caching strategies for Upstash
class UpstashCostOptimizer:
    """
    Strategies to minimize Upstash costs.

    Upstash charges per command, so we optimize for:
    - Fewer commands via batching
    - Smaller payloads via compression
    - Smarter TTLs to reduce storage
    """

    @staticmethod
    def calculate_optimal_ttl(data_size: int, access_frequency: float, data_volatility: float) -> int:
        """
        Calculate optimal TTL based on data characteristics.

        Args:
            data_size: Size of data in bytes
            access_frequency: Expected accesses per hour (0-1)
            data_volatility: How often data changes (0-1)

        Returns:
            Optimal TTL in seconds
        """
        # Base TTL inversely proportional to volatility
        base_ttl = 3600 * (1 - data_volatility)  # 0-3600 seconds

        # Adjust for access frequency (cache frequently accessed longer)
        frequency_multiplier = 1 + access_frequency

        # Adjust for size (cache smaller items longer)
        size_penalty = max(0.5, 1 - (data_size / 1024 / 100))  # Penalty for >100KB

        optimal_ttl = int(base_ttl * frequency_multiplier * size_penalty)

        # Enforce min/max bounds
        return max(60, min(86400, optimal_ttl))  # 1 minute to 24 hours
