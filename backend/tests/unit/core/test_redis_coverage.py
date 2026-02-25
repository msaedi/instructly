"""Unit coverage for app.core.redis – uncovered L44,47."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest


class _AsyncRedisStub:
    """Stub for AsyncRedis."""

    def __init__(self, ping_error=None) -> None:
        self._ping_error = ping_error
        self.aclose_called = False

        async def _disconnect():
            pass

        self.connection_pool = SimpleNamespace(disconnect=_disconnect)

    async def ping(self):
        if self._ping_error:
            raise self._ping_error
        return True

    async def aclose(self):
        self.aclose_called = True


@pytest.mark.asyncio
async def test_get_async_redis_client_success(monkeypatch):
    """L44,47: Double-check locking – client created on first call."""
    import app.core.redis as redis_mod

    original = redis_mod._async_redis_client
    try:
        redis_mod._async_redis_client = None
        redis_mod._redis_lock = asyncio.Lock()

        stub = _AsyncRedisStub()
        monkeypatch.setattr(redis_mod, "secret_or_plain", lambda x: "redis://localhost:6379")
        monkeypatch.setattr(redis_mod, "settings", SimpleNamespace(redis_url="redis://localhost:6379"))

        from redis.asyncio import Redis as AsyncRedis

        monkeypatch.setattr(AsyncRedis, "from_url", staticmethod(lambda *a, **kw: stub))

        client = await redis_mod.get_async_redis_client()
        assert client is stub

        # Second call should return cached client
        client2 = await redis_mod.get_async_redis_client()
        assert client2 is stub
    finally:
        redis_mod._async_redis_client = original


@pytest.mark.asyncio
async def test_get_async_redis_client_ping_failure(monkeypatch):
    """L44,47: When ping fails, client stays None."""
    import app.core.redis as redis_mod

    original = redis_mod._async_redis_client
    try:
        redis_mod._async_redis_client = None
        redis_mod._redis_lock = asyncio.Lock()

        stub = _AsyncRedisStub(ping_error=ConnectionError("refused"))
        monkeypatch.setattr(redis_mod, "secret_or_plain", lambda x: "redis://localhost:6379")
        monkeypatch.setattr(redis_mod, "settings", SimpleNamespace(redis_url="redis://localhost:6379"))

        from redis.asyncio import Redis as AsyncRedis

        monkeypatch.setattr(AsyncRedis, "from_url", staticmethod(lambda *a, **kw: stub))

        client = await redis_mod.get_async_redis_client()
        assert client is None
    finally:
        redis_mod._async_redis_client = original


@pytest.mark.asyncio
async def test_close_async_redis_client(monkeypatch):
    """Close with existing client."""
    import app.core.redis as redis_mod

    original = redis_mod._async_redis_client
    try:
        stub = _AsyncRedisStub()
        redis_mod._async_redis_client = stub

        await redis_mod.close_async_redis_client()
        assert stub.aclose_called is True
        assert redis_mod._async_redis_client is None
    finally:
        redis_mod._async_redis_client = original


@pytest.mark.asyncio
async def test_close_async_redis_client_none():
    """Close when no client exists."""
    import app.core.redis as redis_mod

    original = redis_mod._async_redis_client
    try:
        redis_mod._async_redis_client = None
        await redis_mod.close_async_redis_client()
        assert redis_mod._async_redis_client is None
    finally:
        redis_mod._async_redis_client = original
