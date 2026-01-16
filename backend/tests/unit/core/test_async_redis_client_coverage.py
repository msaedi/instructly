from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core import redis as core_redis


class _DummyRedis:
    def __init__(self) -> None:
        self.ping_called = False
        self.closed = False
        self.connection_pool = SimpleNamespace(disconnect=AsyncMock())

    async def ping(self) -> None:
        self.ping_called = True

    async def aclose(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_get_async_redis_client_initializes(monkeypatch) -> None:
    dummy = _DummyRedis()
    monkeypatch.setattr(core_redis, "_async_redis_client", None)
    monkeypatch.setattr(core_redis.settings, "redis_url", "redis://example", raising=False)
    monkeypatch.setattr(core_redis.AsyncRedis, "from_url", lambda *args, **kwargs: dummy)

    client = await core_redis.get_async_redis_client()
    assert client is dummy
    assert dummy.ping_called is True


@pytest.mark.asyncio
async def test_get_async_redis_client_handles_failure(monkeypatch) -> None:
    class _FailRedis(_DummyRedis):
        async def ping(self) -> None:
            raise RuntimeError("boom")

    dummy = _FailRedis()
    monkeypatch.setattr(core_redis, "_async_redis_client", None)
    monkeypatch.setattr(core_redis.AsyncRedis, "from_url", lambda *args, **kwargs: dummy)

    client = await core_redis.get_async_redis_client()
    assert client is None


@pytest.mark.asyncio
async def test_close_async_redis_client(monkeypatch) -> None:
    dummy = _DummyRedis()
    monkeypatch.setattr(core_redis, "_async_redis_client", dummy)

    await core_redis.close_async_redis_client()

    assert dummy.closed is True
    dummy.connection_pool.disconnect.assert_awaited()
    assert core_redis._async_redis_client is None
