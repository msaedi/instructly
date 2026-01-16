from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any
import weakref

from redis.asyncio import Redis as AsyncRedis

logger = logging.getLogger(__name__)

_clients_by_loop: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, AsyncRedis]" = (
    weakref.WeakKeyDictionary()
)
_locks_by_loop: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Lock]" = (
    weakref.WeakKeyDictionary()
)


async def get_redis(**_kwargs: Any) -> AsyncRedis:
    """
    Return the async Redis client for rate limiting/idempotency.

    Decision: rate limiting uses `RATE_LIMIT_REDIS_URL` so it can be isolated from the
    general cache Redis in production when desired (while still defaulting to localhost).
    """
    from . import config as rl_config

    loop = asyncio.get_running_loop()

    existing = _clients_by_loop.get(loop)
    if existing is not None:
        return existing

    lock = _locks_by_loop.get(loop)
    if lock is None:
        lock = asyncio.Lock()
        _locks_by_loop[loop] = lock

    async with lock:
        existing = _clients_by_loop.get(loop)
        if existing is not None:
            return existing

        redis_url = rl_config.settings.redis_url
        client = AsyncRedis.from_url(
            redis_url,
            encoding="utf-8",
            decode_responses=True,
        )

        try:
            await client.ping()
        except Exception as exc:
            logger.error("[REDIS-RATELIMIT] Async Redis client FAILED to connect: %s", exc)
            try:
                await client.aclose()
            except Exception:
                pass
            raise RuntimeError("Redis unavailable") from exc

        _clients_by_loop[loop] = client
        return client


async def close_async_rate_limit_redis_client() -> None:
    """Close the async rate limiting Redis client (separate from cache + pubsub)."""
    loop = asyncio.get_running_loop()

    client = _clients_by_loop.pop(loop, None)
    if client is None:
        return

    try:
        await client.aclose()
        with contextlib.suppress(BaseException):
            await client.connection_pool.disconnect()
    finally:
        logger.info("[REDIS-RATELIMIT] Async Redis client closed")


# Lua script implementing GCRA logic using TAT (Theoretical Arrival Time)
# KEYS[1] = storage key
# ARGV[1] = now_ms
# ARGV[2] = interval_ms (60_000 / rate_per_min)
# ARGV[3] = burst
# Returns: {allowed, retry_after_ms, remaining, limit, reset_epoch_s, new_tat_ms}
GCRA_LUA = r"""
local key = KEYS[1]
local now_ms = tonumber(ARGV[1])
local interval_ms = tonumber(ARGV[2])
local burst = tonumber(ARGV[3])

local tat_ms = redis.call('GET', key)
if tat_ms then tat_ms = tonumber(tat_ms) end

-- If no TAT, initialize to allow immediate burst requests
if not tat_ms then
  tat_ms = now_ms - (burst * interval_ms)
end

local allow = now_ms >= (tat_ms - (burst * interval_ms))
local new_tat_ms
local retry_after_ms = 0
local remaining = 0
local limit = burst + 1
local reset_epoch_s = math.floor((now_ms + (burst * interval_ms)) / 1000)

if allow then
  if tat_ms > now_ms then
    new_tat_ms = tat_ms + interval_ms
  else
    new_tat_ms = now_ms + interval_ms
  end
  remaining = math.max(0, burst - math.floor(((new_tat_ms - now_ms) / interval_ms) - 1))
  redis.call('SET', key, new_tat_ms)
  return {1, 0, remaining, limit, reset_epoch_s, new_tat_ms}
else
  local allow_at_ms = tat_ms - (burst * interval_ms)
  retry_after_ms = math.max(0, allow_at_ms - now_ms)
  -- keep tat_ms unchanged when blocked
  return {0, retry_after_ms, 0, limit, reset_epoch_s, tat_ms}
end
"""

__all__ = ["get_redis", "close_async_rate_limit_redis_client", "GCRA_LUA"]
