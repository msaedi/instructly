import json

import pytest
from redis.exceptions import RedisError

from app.core.exceptions import ServiceException
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


class PendingRaceRedis(DummyRedis):
    def __init__(self) -> None:
        super().__init__()
        self._get_calls = 0

    async def get(self, key):
        self._get_calls += 1
        if self._get_calls == 1:
            return None
        return json.dumps({"status": "pending"})

    async def set(self, key, value, ex=None, nx=False):
        return False


class ErrorRedis:
    async def get(self, key):
        raise RedisError("boom")

    async def set(self, key, value, ex=None, nx=False):
        raise RedisError("boom")

    async def setex(self, key, ttl, value):
        raise RedisError("boom")


class ErrorSetexRedis(DummyRedis):
    async def setex(self, key, ttl, value):
        raise RedisError("boom")


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


@pytest.mark.asyncio
async def test_check_and_store_pending_record(db):
    redis = DummyRedis()
    storage_key = "mcp:idempotency:op-pending:idem"
    redis.store[storage_key] = json.dumps({"status": "pending"})

    service = MCPIdempotencyService(db, redis_client=redis)
    already, cached = await service.check_and_store("idem", operation="op-pending")
    assert already is True
    assert cached is None


@pytest.mark.asyncio
async def test_check_and_store_handles_race_pending(db):
    redis = PendingRaceRedis()
    service = MCPIdempotencyService(db, redis_client=redis)

    already, cached = await service.check_and_store("idem-race", operation="op-race")
    assert already is True
    assert cached is None


@pytest.mark.asyncio
async def test_check_and_store_redis_error(db):
    service = MCPIdempotencyService(db, redis_client=ErrorRedis())
    with pytest.raises(ServiceException) as exc:
        await service.check_and_store("idem-error", operation="op-error")
    assert exc.value.code == "idempotency_unavailable"


@pytest.mark.asyncio
async def test_store_result_missing_context(db):
    service = MCPIdempotencyService(db, redis_client=DummyRedis())
    with pytest.raises(ServiceException) as exc:
        await service.store_result("idem-missing", {"ok": True})
    assert exc.value.code == "mcp_idem_operation_missing"


@pytest.mark.asyncio
async def test_store_result_redis_error_is_non_fatal(db):
    service = MCPIdempotencyService(db, redis_client=ErrorSetexRedis())
    service._operation_context = "op-error"  # test-only setup

    await service.store_result("idem-error", {"ok": True})
