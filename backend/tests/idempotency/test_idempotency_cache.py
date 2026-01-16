from types import SimpleNamespace

import pytest

from app.idempotency import cache as idem_cache


class DummyRedis:
    def __init__(self):
        self.store = {}

    async def get(self, key):
        return self.store.get(key)

    async def setex(self, key, _ttl, value):
        self.store[key] = value


@pytest.mark.asyncio
async def test_idempotency_cache_set_and_get(monkeypatch):
    redis = DummyRedis()

    async def _get_redis():
        return redis

    monkeypatch.setattr(idem_cache, "get_redis", _get_redis)
    raw = "POST:/api/payments/checkout:user:123:bodyhash"
    payload = {"status": "ok", "id": "abc123"}

    await idem_cache.set_cached(raw, payload, ttl_s=2)
    got = await idem_cache.get_cached(raw)
    assert got == payload


def test_idem_key_uses_namespace(monkeypatch) -> None:
    monkeypatch.setattr(idem_cache, "settings", SimpleNamespace(namespace="ns"))
    key = idem_cache.idem_key("raw")
    assert key.startswith("ns:idem:")


@pytest.mark.asyncio
async def test_get_cached_handles_exception(monkeypatch):
    async def _get_redis():
        raise RuntimeError("boom")

    monkeypatch.setattr(idem_cache, "get_redis", _get_redis)
    assert await idem_cache.get_cached("raw") is None


@pytest.mark.asyncio
async def test_set_cached_handles_exception(monkeypatch):
    async def _get_redis():
        raise RuntimeError("boom")

    monkeypatch.setattr(idem_cache, "get_redis", _get_redis)
    await idem_cache.set_cached("raw", {"ok": True})
