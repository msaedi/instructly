import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.ratelimit import redis_backend


class _RedisStub:
    def __init__(self, ping_error=None) -> None:
        self._ping_error = ping_error
        self.aclose_called = False
        self.disconnect_called = False

        async def _disconnect():
            self.disconnect_called = True

        self.connection_pool = SimpleNamespace(disconnect=_disconnect)

    async def ping(self):
        if self._ping_error:
            raise self._ping_error
        return True

    async def aclose(self):
        self.aclose_called = True


@pytest.mark.asyncio
async def test_get_redis_caches_per_loop(monkeypatch):
    redis_backend._clients_by_loop.clear()
    redis_backend._locks_by_loop.clear()

    stub = _RedisStub()
    from_url = Mock(return_value=stub)
    monkeypatch.setattr(redis_backend.AsyncRedis, "from_url", from_url)
    import app.ratelimit.config as rl_config

    monkeypatch.setattr(
        rl_config,
        "settings",
        SimpleNamespace(redis_url="redis://example"),
    )

    first = await redis_backend.get_redis()
    second = await redis_backend.get_redis()
    assert first is second
    assert from_url.call_count == 1


@pytest.mark.asyncio
async def test_get_redis_ping_failure(monkeypatch):
    redis_backend._clients_by_loop.clear()
    redis_backend._locks_by_loop.clear()

    stub = _RedisStub(ping_error=RuntimeError("down"))
    monkeypatch.setattr(redis_backend.AsyncRedis, "from_url", Mock(return_value=stub))
    import app.ratelimit.config as rl_config

    monkeypatch.setattr(
        rl_config,
        "settings",
        SimpleNamespace(redis_url="redis://example"),
    )

    with pytest.raises(RuntimeError):
        await redis_backend.get_redis()
    assert stub.aclose_called is True


@pytest.mark.asyncio
async def test_close_async_rate_limit_redis_client(monkeypatch):
    redis_backend._clients_by_loop.clear()
    redis_backend._locks_by_loop.clear()

    stub = _RedisStub()
    loop = asyncio.get_running_loop()
    redis_backend._clients_by_loop[loop] = stub

    await redis_backend.close_async_rate_limit_redis_client()
    assert stub.aclose_called is True
    assert stub.disconnect_called is True
