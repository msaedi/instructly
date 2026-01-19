from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core import cache_redis
from app.core.config import settings


@pytest.mark.asyncio
async def test_get_async_cache_redis_client_no_loop(monkeypatch) -> None:
    monkeypatch.setattr(cache_redis.asyncio, "get_running_loop", lambda: (_ for _ in ()).throw(RuntimeError()))

    result = await cache_redis.get_async_cache_redis_client()

    assert result is None


@pytest.mark.asyncio
async def test_get_async_cache_redis_client_testing_closes_existing(monkeypatch) -> None:
    loop = asyncio.get_running_loop()
    dummy = AsyncMock()
    cache_redis._clients_by_loop[loop] = dummy

    monkeypatch.setattr(settings, "is_testing", True, raising=False)
    monkeypatch.setattr(settings, "redis_url", None, raising=False)

    result = await cache_redis.get_async_cache_redis_client()

    assert result is None
    dummy.aclose.assert_awaited()
    assert loop not in cache_redis._clients_by_loop


@pytest.mark.asyncio
async def test_get_async_cache_redis_client_reuses_existing(monkeypatch) -> None:
    loop = asyncio.get_running_loop()
    dummy = AsyncMock()
    cache_redis._clients_by_loop[loop] = dummy

    monkeypatch.setattr(settings, "is_testing", False, raising=False)
    monkeypatch.setattr(settings, "redis_url", "redis://example", raising=False)

    result = await cache_redis.get_async_cache_redis_client()

    assert result is dummy


@pytest.mark.asyncio
async def test_get_async_cache_redis_client_ping_failure(monkeypatch) -> None:
    dummy = AsyncMock()
    dummy.ping.side_effect = RuntimeError("nope")

    monkeypatch.setattr(cache_redis.AsyncRedis, "from_url", lambda *_args, **_kwargs: dummy)
    monkeypatch.setattr(settings, "is_testing", False, raising=False)
    monkeypatch.setattr(settings, "redis_url", "redis://example", raising=False)

    result = await cache_redis.get_async_cache_redis_client()

    assert result is None
    dummy.aclose.assert_awaited()


@pytest.mark.asyncio
async def test_close_async_cache_redis_client_disconnects(monkeypatch) -> None:
    loop = asyncio.get_running_loop()
    dummy = AsyncMock()
    dummy.connection_pool = SimpleNamespace(disconnect=AsyncMock())
    cache_redis._clients_by_loop[loop] = dummy

    await cache_redis.close_async_cache_redis_client()

    dummy.aclose.assert_awaited()
    dummy.connection_pool.disconnect.assert_awaited()
