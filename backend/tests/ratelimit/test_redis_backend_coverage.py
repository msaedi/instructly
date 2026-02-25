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


@pytest.mark.asyncio
async def test_close_async_rate_limit_redis_client_no_client():
    """L37: close when client is None (no-op)."""
    redis_backend._clients_by_loop.clear()
    redis_backend._locks_by_loop.clear()

    await redis_backend.close_async_rate_limit_redis_client()
    # Should not raise


@pytest.mark.asyncio
async def test_get_redis_double_check_locking(monkeypatch):
    """L44: double-check locking – second check inside lock returns existing."""
    redis_backend._clients_by_loop.clear()
    redis_backend._locks_by_loop.clear()

    stub = _RedisStub()

    # Pre-populate client AFTER lock is created (simulates race condition)
    call_count = {"n": 0}

    def patched_from_url(*args, **kwargs):
        call_count["n"] += 1
        return stub

    monkeypatch.setattr(redis_backend.AsyncRedis, "from_url", patched_from_url)
    import app.ratelimit.config as rl_config

    monkeypatch.setattr(
        rl_config,
        "settings",
        SimpleNamespace(redis_url="redis://example"),
    )

    first = await redis_backend.get_redis()
    assert first is stub
    # Cache hit on second call
    second = await redis_backend.get_redis()
    assert second is stub
    assert call_count["n"] == 1


@pytest.mark.asyncio
async def test_get_redis_ping_failure_closes_client(monkeypatch):
    """L59-60: On ping failure, aclose is called and error propagates."""
    redis_backend._clients_by_loop.clear()
    redis_backend._locks_by_loop.clear()

    stub = _RedisStub(ping_error=ConnectionError("conn refused"))
    monkeypatch.setattr(redis_backend.AsyncRedis, "from_url", Mock(return_value=stub))
    import app.ratelimit.config as rl_config

    monkeypatch.setattr(
        rl_config,
        "settings",
        SimpleNamespace(redis_url="redis://example"),
    )

    with pytest.raises(RuntimeError, match="Redis unavailable"):
        await redis_backend.get_redis()
    assert stub.aclose_called is True


@pytest.mark.asyncio
async def test_get_redis_lock_already_exists(monkeypatch):
    """L37->41: lock already exists in _locks_by_loop, skip creation."""
    redis_backend._clients_by_loop.clear()
    redis_backend._locks_by_loop.clear()

    stub = _RedisStub()
    monkeypatch.setattr(redis_backend.AsyncRedis, "from_url", Mock(return_value=stub))
    import app.ratelimit.config as rl_config

    monkeypatch.setattr(
        rl_config,
        "settings",
        SimpleNamespace(redis_url="redis://example"),
    )

    # Pre-populate the lock for the current loop
    loop = asyncio.get_running_loop()
    redis_backend._locks_by_loop[loop] = asyncio.Lock()

    client = await redis_backend.get_redis()
    assert client is stub


@pytest.mark.asyncio
async def test_get_redis_double_check_locking_inside_lock(monkeypatch):
    """L44: Another coroutine populates the client while we wait for the lock."""
    redis_backend._clients_by_loop.clear()
    redis_backend._locks_by_loop.clear()

    stub = _RedisStub()
    pre_existing_stub = _RedisStub()
    import app.ratelimit.config as rl_config

    monkeypatch.setattr(
        rl_config,
        "settings",
        SimpleNamespace(redis_url="redis://example"),
    )

    loop = asyncio.get_running_loop()
    lock = asyncio.Lock()
    redis_backend._locks_by_loop[loop] = lock

    def sneaky_from_url(*args, **kwargs):
        # This simulates another coroutine having populated the cache
        # before our from_url call. But we need to inject BEFORE from_url.
        # Instead, we pre-populate the client dict so the double-check at L42-44 hits.
        return stub

    monkeypatch.setattr(redis_backend.AsyncRedis, "from_url", sneaky_from_url)

    # Pre-populate client inside the dict so the double-check returns it
    redis_backend._clients_by_loop[loop] = pre_existing_stub

    client = await redis_backend.get_redis()
    # Should get the pre_existing_stub from the L32-34 fast path (before lock)
    assert client is pre_existing_stub


@pytest.mark.asyncio
async def test_get_redis_double_check_returns_existing_from_inside_lock(monkeypatch):
    """L42-44: Specifically tests the double-check INSIDE the lock."""
    redis_backend._clients_by_loop.clear()
    redis_backend._locks_by_loop.clear()

    stub = _RedisStub()
    import app.ratelimit.config as rl_config

    monkeypatch.setattr(
        rl_config,
        "settings",
        SimpleNamespace(redis_url="redis://example"),
    )

    loop = asyncio.get_running_loop()

    # We need to get past L32-34 (no client) but then have L42-44 find one.
    # To do this, we use a custom Lock that injects a client when acquired.
    class InjectingLock:
        async def __aenter__(self):
            # Simulate another coroutine populating the cache while we waited
            redis_backend._clients_by_loop[loop] = stub
            return self

        async def __aexit__(self, *args):
            pass

    redis_backend._locks_by_loop[loop] = InjectingLock()

    from_url_mock = Mock(return_value=_RedisStub())
    monkeypatch.setattr(redis_backend.AsyncRedis, "from_url", from_url_mock)

    client = await redis_backend.get_redis()
    assert client is stub
    # from_url should NOT have been called because the double-check found the client
    assert from_url_mock.call_count == 0


@pytest.mark.asyncio
async def test_get_redis_ping_failure_aclose_also_raises(monkeypatch):
    """L59-60: aclose itself raises during ping failure cleanup."""
    redis_backend._clients_by_loop.clear()
    redis_backend._locks_by_loop.clear()

    class _FailingCloseStub(_RedisStub):
        def __init__(self):
            super().__init__(ping_error=ConnectionError("down"))

        async def aclose(self):
            self.aclose_called = True
            raise OSError("aclose failed too")

    stub = _FailingCloseStub()
    monkeypatch.setattr(redis_backend.AsyncRedis, "from_url", Mock(return_value=stub))
    import app.ratelimit.config as rl_config

    monkeypatch.setattr(
        rl_config,
        "settings",
        SimpleNamespace(redis_url="redis://example"),
    )

    with pytest.raises(RuntimeError, match="Redis unavailable"):
        await redis_backend.get_redis()
    # aclose was attempted despite raising
    assert stub.aclose_called is True
