from __future__ import annotations

from contextlib import asynccontextmanager, contextmanager
import logging
import threading
import time
from typing import AsyncIterator, Iterator, Optional

from redis import Redis

from app.ratelimit.config import settings as rl_settings
from app.ratelimit.locks import (
    acquire_lock as _acquire_async_lock,
    release_lock as _release_async_lock,
)

logger = logging.getLogger(__name__)

_SYNC_REDIS: Optional[Redis] = None
_SYNC_REDIS_LOCK = threading.Lock()


def _lock_key(booking_id: str) -> str:
    return f"booking:{booking_id}:mutex"


def _namespaced_key(key: str) -> str:
    return f"{rl_settings.namespace}:lock:{key}"


def _get_sync_redis() -> Optional[Redis]:
    global _SYNC_REDIS
    if _SYNC_REDIS is not None:
        return _SYNC_REDIS
    with _SYNC_REDIS_LOCK:
        if _SYNC_REDIS is not None:
            return _SYNC_REDIS
        try:
            client = Redis.from_url(
                rl_settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
            client.ping()
        except Exception as exc:
            logger.warning("booking_lock_sync_redis_unavailable: %s", exc)
            return None
        _SYNC_REDIS = client
        return _SYNC_REDIS


async def acquire_booking_lock(booking_id: str, ttl_s: int = 90) -> bool:
    return await _acquire_async_lock(_lock_key(booking_id), ttl_s=ttl_s)


async def release_booking_lock(booking_id: str) -> None:
    await _release_async_lock(_lock_key(booking_id))


def acquire_booking_lock_sync(booking_id: str, ttl_s: int = 90) -> bool:
    client = _get_sync_redis()
    if client is None:
        return True
    try:
        return bool(
            client.set(_namespaced_key(_lock_key(booking_id)), str(time.time()), nx=True, ex=ttl_s)
        )
    except Exception as exc:
        logger.warning("booking_lock_sync_failed: %s", exc)
        return True


def release_booking_lock_sync(booking_id: str) -> None:
    client = _get_sync_redis()
    if client is None:
        return
    try:
        client.delete(_namespaced_key(_lock_key(booking_id)))
    except Exception as exc:
        logger.warning("booking_lock_sync_release_failed: %s", exc)


@asynccontextmanager
async def booking_lock(booking_id: str, ttl_s: int = 90) -> AsyncIterator[bool]:
    acquired = await acquire_booking_lock(booking_id, ttl_s=ttl_s)
    try:
        yield acquired
    finally:
        if acquired:
            await release_booking_lock(booking_id)


@contextmanager
def booking_lock_sync(booking_id: str, ttl_s: int = 90) -> Iterator[bool]:
    acquired = acquire_booking_lock_sync(booking_id, ttl_s=ttl_s)
    try:
        yield acquired
    finally:
        if acquired:
            release_booking_lock_sync(booking_id)
