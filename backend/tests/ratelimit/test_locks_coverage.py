from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.ratelimit import locks as rl_locks


@pytest.mark.asyncio
async def test_acquire_lock_and_release_lock_success(monkeypatch):
    calls: list[tuple[str, str]] = []

    class DummyRedis:
        async def set(self, key, value, nx=True, ex=30):
            calls.append(("set", key))
            return True

        async def delete(self, key):
            calls.append(("delete", key))
            return 1

    async def _get_redis():
        return DummyRedis()

    monkeypatch.setattr(rl_locks, "settings", SimpleNamespace(namespace="test"))
    monkeypatch.setattr(rl_locks, "get_redis", _get_redis)

    acquired = await rl_locks.acquire_lock("abc", ttl_s=10)
    await rl_locks.release_lock("abc")

    assert acquired is True
    assert calls[0] == ("set", "test:lock:abc")
    assert calls[1] == ("delete", "test:lock:abc")


@pytest.mark.asyncio
async def test_release_lock_fails_open_when_redis_unavailable(monkeypatch):
    async def _boom():
        raise RuntimeError("redis down")

    monkeypatch.setattr(rl_locks, "get_redis", _boom)

    await rl_locks.release_lock("abc")
