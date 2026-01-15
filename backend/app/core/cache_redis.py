# backend/app/core/cache_redis.py
"""
Async Redis client for key-value caching (non Pub/Sub).

This client is used by CacheService and other caching-style components.

Important:
- This is intentionally separate from `app.core.redis`, which is reserved for
  messaging/PubSub and SSE-related infrastructure.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Optional
import weakref

from redis.asyncio import Redis as AsyncRedis

from app.core.config import settings

logger = logging.getLogger(__name__)

_clients_by_loop: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, AsyncRedis]" = (
    weakref.WeakKeyDictionary()
)
_locks_by_loop: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Lock]" = (
    weakref.WeakKeyDictionary()
)


async def get_async_cache_redis_client() -> Optional[AsyncRedis]:
    """
    Get or create async Redis client for caching operations.

    Returns:
        AsyncRedis client instance, or None when Redis is unavailable.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return None

    # In tests, default to in-memory cache unless Redis is explicitly configured.
    # This avoids background tasks attempting to connect to localhost Redis and
    # emitting teardown-time unawaited coroutine warnings when the event loop closes.
    if settings.is_testing and not settings.redis_url:
        existing = _clients_by_loop.pop(loop, None)
        if existing is not None:
            with contextlib.suppress(BaseException):
                await existing.aclose()
        return None

    existing = _clients_by_loop.get(loop)
    if existing is not None:
        return existing

    lock = _locks_by_loop.get(loop)
    if lock is None:
        lock = asyncio.Lock()
        _locks_by_loop[loop] = lock

    try:
        async with lock:
            existing = _clients_by_loop.get(loop)
            if existing is not None:
                return existing

            redis_url = settings.redis_url or "redis://localhost:6379"
            client = AsyncRedis.from_url(
                redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
            try:
                await client.ping()
            except BaseException as exc:
                logger.error("[REDIS-CACHE] Async Redis client FAILED to connect: %s", exc)
                with contextlib.suppress(BaseException):
                    await client.aclose()
                return None

            _clients_by_loop[loop] = client
            logger.info("[REDIS-CACHE] Async Redis client initialized and connected")
            return client
    except RuntimeError as exc:
        if "Event loop is closed" in str(exc):
            return None
        raise
    except BaseException:
        return None


async def close_async_cache_redis_client() -> None:
    """Close the async caching Redis client."""
    loop = asyncio.get_running_loop()

    client = _clients_by_loop.pop(loop, None)
    if client is None:
        return

    try:
        await client.aclose()
        with contextlib.suppress(BaseException):
            await client.connection_pool.disconnect()
    finally:
        logger.info("[REDIS-CACHE] Async Redis client closed")
