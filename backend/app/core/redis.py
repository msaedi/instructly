# backend/app/core/redis.py
"""
Async Redis client for Pub/Sub operations.

This module provides an async Redis client for messaging features
that require non-blocking I/O (e.g., Pub/Sub publishing).

The sync Redis client in cache_service.py remains unchanged for
caching operations.
"""

import logging
from typing import Optional

from redis.asyncio import Redis as AsyncRedis

from app.core.config import settings

logger = logging.getLogger(__name__)

_async_redis_client: Optional[AsyncRedis] = None


async def get_async_redis_client() -> AsyncRedis:
    """
    Get or create async Redis client for Pub/Sub operations.

    Returns:
        AsyncRedis: Async Redis client instance

    Note:
        This client is separate from the sync client used in CacheService.
        It's optimized for async Pub/Sub operations.
    """
    global _async_redis_client

    if _async_redis_client is None:
        redis_url = settings.redis_url or "redis://localhost:6379"
        _async_redis_client = AsyncRedis.from_url(
            redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
        logger.info("[REDIS-PUBSUB] Async Redis client initialized")

    return _async_redis_client


async def close_async_redis_client() -> None:
    """Close async Redis client gracefully."""
    global _async_redis_client

    if _async_redis_client is not None:
        await _async_redis_client.aclose()
        _async_redis_client = None
        logger.info("[REDIS-PUBSUB] Async Redis client closed")
