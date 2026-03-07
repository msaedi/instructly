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
from typing import Any, Optional
import weakref

from redis.asyncio import Redis as AsyncRedis

from app.core.config import secret_or_plain, settings

logger = logging.getLogger(__name__)

_clients_by_loop: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, AsyncRedis]" = (
    weakref.WeakKeyDictionary()
)
_locks_by_loop: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Lock]" = (
    weakref.WeakKeyDictionary()
)


async def _disconnect_pool_connections(connection_pool: Any) -> None:
    """
    Disconnect Redis pool connections without relying on redis-py's gather-based helper.

    The cache client is sometimes closed immediately after a failed connection attempt.
    In that state, redis-py's internal `connection_pool.disconnect()` can create
    `connection.disconnect()` coroutines and then abort before awaiting them, which
    surfaces as `RuntimeWarning: coroutine ... was never awaited` during test teardown.
    Disconnecting sequentially avoids leaving orphaned coroutines behind.
    """
    available = getattr(connection_pool, "_available_connections", None)
    in_use = getattr(connection_pool, "_in_use_connections", None)

    if available is None and in_use is None:
        disconnect = getattr(connection_pool, "disconnect", None)
        if callable(disconnect):
            await disconnect()
        return

    first_error: BaseException | None = None
    seen: set[int] = set()
    for connection in [*(available or ()), *(in_use or ())]:
        marker = id(connection)
        if marker in seen:
            continue
        seen.add(marker)
        try:
            await connection.disconnect()
        except BaseException as exc:  # pragma: no cover - behavior preserved, covered via caller
            if first_error is None:
                first_error = exc
    if first_error is not None:
        raise first_error


async def _close_cache_client(
    client: AsyncRedis, *, suppress_disconnect_errors: bool = False
) -> None:
    """Close a cache Redis client without triggering redis-py's gather disconnect path."""
    await client.aclose(close_connection_pool=False)
    if suppress_disconnect_errors:
        with contextlib.suppress(Exception):
            await _disconnect_pool_connections(client.connection_pool)
        return
    await _disconnect_pool_connections(client.connection_pool)


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
    redis_url = secret_or_plain(settings.redis_url).strip()
    if settings.is_testing and not redis_url:
        existing = _clients_by_loop.pop(loop, None)
        if existing is not None:
            with contextlib.suppress(Exception):
                await _close_cache_client(existing)
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

            redis_url = redis_url or "redis://localhost:6379"
            client = AsyncRedis.from_url(
                redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
            try:
                await client.ping()
            except Exception as exc:
                logger.warning("[REDIS-CACHE] Async Redis client FAILED to connect: %s", exc)
                with contextlib.suppress(Exception):
                    await _close_cache_client(client)
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
        await _close_cache_client(client, suppress_disconnect_errors=True)
    finally:
        logger.info("[REDIS-CACHE] Async Redis client closed")
