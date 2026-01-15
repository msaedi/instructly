# backend/app/core/redis.py
"""
Async Redis client for Pub/Sub operations.

This module provides an async Redis client for messaging features
that require non-blocking I/O (e.g., Pub/Sub publishing).

The sync Redis client in cache_service.py remains unchanged for
caching operations.
"""

import asyncio
import contextlib
import logging
from typing import Optional

from redis.asyncio import Redis as AsyncRedis

from app.core.config import settings

logger = logging.getLogger(__name__)

_async_redis_client: Optional[AsyncRedis] = None
_redis_lock: asyncio.Lock = asyncio.Lock()


async def get_async_redis_client() -> Optional[AsyncRedis]:
    """
    Get or create async Redis client for Pub/Sub operations.

    Uses double-check locking pattern to prevent race conditions
    when multiple coroutines attempt to initialize the client concurrently.

    Returns:
        AsyncRedis: Async Redis client instance

    Note:
        This client is separate from the sync client used in CacheService.
        It's optimized for async Pub/Sub operations.
    """
    global _async_redis_client

    # Fast path: client already initialized
    if _async_redis_client is None:
        async with _redis_lock:
            # Double-check after acquiring lock
            if _async_redis_client is None:
                redis_url = settings.redis_url or "redis://localhost:6379"
                client = AsyncRedis.from_url(
                    redis_url,
                    encoding="utf-8",
                    decode_responses=True,
                )
                try:
                    await client.ping()
                    _async_redis_client = client
                    logger.info("[REDIS-PUBSUB] Async Redis client initialized and connected")
                except Exception as exc:
                    logger.error("[REDIS-PUBSUB] Async Redis client FAILED to connect: %s", exc)
                    _async_redis_client = None

    return _async_redis_client


async def close_async_redis_client() -> None:
    """Close async Redis client gracefully."""
    global _async_redis_client

    if _async_redis_client is not None:
        await _async_redis_client.aclose()
        with contextlib.suppress(BaseException):
            await _async_redis_client.connection_pool.disconnect()
        _async_redis_client = None
        logger.info("[REDIS-PUBSUB] Async Redis client closed")
