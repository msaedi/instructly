import pytest

from app.services.mcp_idempotency_service import MCPIdempotencyService


class DummyRedis:
    def __init__(self) -> None:
        self.store = {}
        self.ttl = {}

    async def get(self, key):
        return self.store.get(key)

    async def set(self, key, value, ex=None, nx=False):
        if nx and key in self.store:
            return False
        self.store[key] = value
        if ex is not None:
            self.ttl[key] = ex
        return True

    async def setex(self, key, ttl, value):
        self.store[key] = value
        self.ttl[key] = ttl


@pytest.mark.asyncio
async def test_check_and_store_and_cache(db):
    redis = DummyRedis()
    service = MCPIdempotencyService(db, redis_client=redis)

    already, cached = await service.check_and_store("idem-1", operation="mcp.invites.send")
    assert already is False
    assert cached is None

    await service.store_result("idem-1", {"sent_count": 1})

    already, cached = await service.check_and_store("idem-1", operation="mcp.invites.send")
    assert already is True
    assert cached == {"sent_count": 1}


@pytest.mark.asyncio
async def test_idempotency_separates_operations(db):
    redis = DummyRedis()
    service = MCPIdempotencyService(db, redis_client=redis)

    already, _ = await service.check_and_store("idem-1", operation="op-a")
    assert already is False
    await service.store_result("idem-1", {"ok": True})

    already, cached = await service.check_and_store("idem-1", operation="op-b")
    assert already is False
    assert cached is None


@pytest.mark.asyncio
async def test_store_result_sets_ttl(db):
    redis = DummyRedis()
    service = MCPIdempotencyService(db, redis_client=redis)

    await service.check_and_store("idem-ttl", operation="op-ttl")
    await service.store_result("idem-ttl", {"ok": True})

    keys = list(redis.ttl.keys())
    assert keys
    assert redis.ttl[keys[0]] == service.TTL_SECONDS
