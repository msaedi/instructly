from __future__ import annotations

import asyncio
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import pytest
from redis.exceptions import RedisError

from app.services.cache_service import (
    CacheKeyBuilder,
    CacheService,
    CacheServiceSyncAdapter,
    CircuitBreaker,
    CircuitState,
    _run_cache_coroutine,
    clear_cache_event_loop,
    get_cache_service,
    get_healthcheck_redis_client,
    set_cache_event_loop,
)


@pytest.fixture
def memory_cache_service(db):
    service = CacheService(db, redis_client=None)
    service.force_memory_cache = True
    return service


@pytest.fixture
def redis_cache_service(db):
    redis_client = AsyncMock()
    service = CacheService(db, redis_client=redis_client)
    service.force_memory_cache = False
    return service, redis_client


@pytest.mark.asyncio
async def test_circuit_breaker_transitions() -> None:
    breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=1)

    async def _fail() -> str:
        raise RedisError("boom")

    with pytest.raises(RedisError):
        await breaker.call(_fail)

    result = await breaker.call(_fail)
    assert result is None
    assert breaker.state == CircuitState.OPEN

    breaker._last_failure_time = datetime.now(timezone.utc) - timedelta(seconds=2)
    assert breaker.state == CircuitState.HALF_OPEN

    async def _ok() -> str:
        return "ok"

    assert await breaker.call(_ok) == "ok"
    assert breaker.state == CircuitState.CLOSED


def test_cache_key_builder_formats() -> None:
    key = CacheKeyBuilder.build("availability", "week", "123", date(2025, 1, 1))
    assert key.startswith("avail:week:123:")
    assert CacheKeyBuilder.hash_complex_key({"a": 1, "b": 2})


def test_cache_key_builder_time_and_datetime() -> None:
    timestamp = datetime(2025, 1, 1, 9, 0, tzinfo=timezone.utc)
    key = CacheKeyBuilder.build("availability", timestamp, time(9, 30))
    assert "2025-01-01T09:00:00+00:00" in key
    assert "09:30:00" in key


@pytest.mark.asyncio
async def test_redis_backend_get_set_delete(redis_cache_service) -> None:
    service, redis_client = redis_cache_service
    redis_client.setex = AsyncMock()
    redis_client.get = AsyncMock(return_value='{"v": 1}')
    redis_client.delete = AsyncMock(return_value=1)

    assert await service.set("redis:key", {"v": 1}, ttl=30)
    assert await service.get("redis:key") == {"v": 1}
    assert await service.delete("redis:key") is True


@pytest.mark.asyncio
async def test_get_json_miss(redis_cache_service) -> None:
    service, redis_client = redis_cache_service
    redis_client.get = AsyncMock(return_value=None)

    assert await service.get_json("missing") is None


@pytest.mark.asyncio
async def test_get_raw_string_on_invalid_json(redis_cache_service) -> None:
    service, redis_client = redis_cache_service
    redis_client.get = AsyncMock(return_value="not-json")

    assert await service.get("raw") == "not-json"


@pytest.mark.asyncio
async def test_set_json_uses_backend(redis_cache_service) -> None:
    service, redis_client = redis_cache_service
    redis_client.setex = AsyncMock()

    await service.set_json("json:key", {"a": 1}, ttl=60)
    redis_client.setex.assert_called_once()


@pytest.mark.asyncio
async def test_memory_set_get_delete(memory_cache_service: CacheService) -> None:
    assert await memory_cache_service.set("key", {"a": 1}, ttl=60)
    assert await memory_cache_service.get("key") == {"a": 1}
    assert await memory_cache_service.delete("key") is True
    assert await memory_cache_service.get("key") is None


@pytest.mark.asyncio
async def test_memory_expiry_evicts(memory_cache_service: CacheService) -> None:
    memory_cache_service._memory_cache["exp"] = "value"
    memory_cache_service._memory_expiry["exp"] = datetime.now(timezone.utc) - timedelta(
        seconds=1
    )

    assert await memory_cache_service.get("exp") is None
    assert "exp" not in memory_cache_service._memory_cache


@pytest.mark.asyncio
async def test_json_helpers_memory(memory_cache_service: CacheService) -> None:
    await memory_cache_service.set_json("json", {"a": 1}, ttl=60)
    assert await memory_cache_service.get_json("json") == {"a": 1}

    memory_cache_service._memory_cache["bad"] = "not-json"
    memory_cache_service._memory_expiry["bad"] = datetime.now(timezone.utc) + timedelta(
        seconds=60
    )
    assert await memory_cache_service.get_json("bad") == "not-json"


@pytest.mark.asyncio
async def test_delete_pattern_memory(memory_cache_service: CacheService) -> None:
    await memory_cache_service.set("prefix:1", 1, ttl=60)
    await memory_cache_service.set("prefix:2", 2, ttl=60)
    await memory_cache_service.set("other:1", 3, ttl=60)

    deleted = await memory_cache_service.delete_pattern("prefix:*")
    assert deleted == 2
    assert await memory_cache_service.get("prefix:1") is None
    assert await memory_cache_service.get("other:1") == 3


@pytest.mark.asyncio
async def test_clear_prefix_short_circuits(memory_cache_service: CacheService) -> None:
    assert await memory_cache_service.clear_prefix("") == 0


@pytest.mark.asyncio
async def test_lock_acquire_release_memory(memory_cache_service: CacheService) -> None:
    assert await memory_cache_service.acquire_lock("lock:key", ttl=10) is True
    assert await memory_cache_service.acquire_lock("lock:key", ttl=10) is False

    memory_cache_service._memory_expiry["lock:key"] = datetime.now(timezone.utc) - timedelta(
        seconds=1
    )
    assert await memory_cache_service.acquire_lock("lock:key", ttl=10) is True

    assert await memory_cache_service.release_lock("lock:key") is True


@pytest.mark.asyncio
async def test_mset_and_mget_memory(memory_cache_service: CacheService) -> None:
    assert await memory_cache_service.mset({"a": {"v": 1}, "b": {"v": 2}}, ttl=60)
    result = await memory_cache_service.mget(["a", "b", "c"])
    assert result["a"] == {"v": 1}
    assert result["b"] == {"v": 2}
    assert "c" not in result


@pytest.mark.asyncio
async def test_domain_specific_helpers(memory_cache_service: CacheService) -> None:
    week_start = date.today() + timedelta(days=7)
    availability = {"slots": ["09:00"]}

    assert await memory_cache_service.cache_week_availability("inst", week_start, availability)
    assert await memory_cache_service.get_week_availability("inst", week_start) == availability

    start_date = date.today()
    end_date = start_date + timedelta(days=2)
    range_data = [{"day": start_date.isoformat()}]
    assert await memory_cache_service.cache_instructor_availability_date_range(
        "inst", start_date, end_date, range_data
    )
    assert (
        await memory_cache_service.get_instructor_availability_date_range(
            "inst", start_date, end_date
        )
        == range_data
    )

    weekly = {"monday": [{"start": "09:00"}]}
    assert await memory_cache_service.cache_instructor_weekly_availability("inst", weekly)
    assert await memory_cache_service.get_instructor_weekly_availability("inst") == weekly

    entries = [
        {"instructor_id": "inst", "week_start": week_start, "data": availability},
        {"instructor_id": "inst", "start_date": start_date, "end_date": end_date, "data": []},
    ]
    assert await memory_cache_service.batch_cache_availability(entries) == 2

    await memory_cache_service.cache_booking_conflicts(
        "inst",
        start_date,
        time(9, 0),
        time(10, 0),
        [{"conflict": True}],
    )


@pytest.mark.asyncio
async def test_invalidate_instructor_availability_updates_stats(
    memory_cache_service: CacheService,
) -> None:
    await memory_cache_service.set("avail:week:inst:2025-01-01", {"a": 1}, ttl=60)
    await memory_cache_service.set("week:foo:inst:bar", {"a": 1}, ttl=60)
    await memory_cache_service.set("con:foo:inst:bar", {"a": 1}, ttl=60)

    await memory_cache_service.invalidate_instructor_availability("inst", dates=[date(2025, 1, 1)])
    stats = await memory_cache_service.get_stats()
    assert stats["availability_invalidations"] >= 1


@pytest.mark.asyncio
async def test_cached_decorator_uses_cache(memory_cache_service: CacheService) -> None:
    calls: dict[str, int] = {"count": 0}

    @memory_cache_service.cached(key_func=lambda *_args, **_kwargs: "cached:key")
    async def _compute() -> dict[str, int]:
        calls["count"] += 1
        return {"value": 1}

    assert await _compute() == {"value": 1}
    assert await _compute() == {"value": 1}
    assert calls["count"] == 1

    await _compute.invalidate()
    assert await memory_cache_service.get("cached:key") is None


@pytest.mark.asyncio
async def test_get_stats_includes_redis_info(redis_cache_service):
    service, redis_client = redis_cache_service
    redis_client.info = AsyncMock(return_value={
        "used_memory_human": "1mb",
        "connected_clients": 1,
        "total_commands_processed": 10,
        "instantaneous_ops_per_sec": 5,
    })

    stats = await service.get_stats()
    assert "redis" in stats


@pytest.mark.asyncio
async def test_get_redis_client_injected(redis_cache_service):
    service, redis_client = redis_cache_service
    assert await service.get_redis_client() is redis_client


@pytest.mark.asyncio
async def test_get_redis_client_fallback(monkeypatch, memory_cache_service: CacheService):
    memory_cache_service.force_memory_cache = False

    async def _get_client() -> Any:
        return "redis-client"

    with patch("app.core.cache_redis.get_async_cache_redis_client", _get_client):
        assert await memory_cache_service.get_redis_client() == "redis-client"


@pytest.mark.asyncio
async def test_delete_pattern_redis(redis_cache_service):
    service, redis_client = redis_cache_service

    async def _scan_iter(*_args, **_kwargs):
        for key in ["k1", "k2"]:
            yield key

    redis_client.scan_iter = _scan_iter
    redis_client.delete = AsyncMock(return_value=True)

    deleted = await service.delete_pattern("k*")
    assert deleted == 2


@pytest.mark.asyncio
async def test_mget_and_mset_redis(redis_cache_service) -> None:
    service, redis_client = redis_cache_service
    redis_client.mget = AsyncMock(return_value=['{"a": 1}', None])

    pipe = Mock()
    pipe.setex = Mock()
    pipe.execute = AsyncMock()
    redis_client.pipeline = Mock(return_value=pipe)

    assert await service.mset({"a": {"a": 1}}, ttl=60)
    result = await service.mget(["a", "b"])
    assert result["a"] == {"a": 1}


@pytest.mark.asyncio
async def test_lock_operations_with_redis(redis_cache_service) -> None:
    service, redis_client = redis_cache_service
    redis_client.set = AsyncMock(return_value=True)
    redis_client.delete = AsyncMock(return_value=1)

    assert await service.acquire_lock("lock:key", ttl=5) is True
    assert await service.release_lock("lock:key") is True


@pytest.mark.asyncio
async def test_clear_prefix_expands_pattern(memory_cache_service: CacheService) -> None:
    await memory_cache_service.set("pref:1", 1, ttl=60)
    await memory_cache_service.set("pref:2", 2, ttl=60)
    deleted = await memory_cache_service.clear_prefix("pref:")
    assert deleted >= 2


@pytest.mark.asyncio
async def test_batch_cache_availability_empty(memory_cache_service: CacheService) -> None:
    assert await memory_cache_service.batch_cache_availability([]) == 0


@pytest.mark.asyncio
async def test_availability_past_date_branches(memory_cache_service: CacheService) -> None:
    past_week = date.today() - timedelta(days=7)
    past_start = date.today() - timedelta(days=2)
    past_end = past_start + timedelta(days=1)

    await memory_cache_service.cache_week_availability("inst", past_week, {"slots": []})
    await memory_cache_service.cache_instructor_availability_date_range(
        "inst", past_start, past_end, []
    )

    assert await memory_cache_service.get_week_availability("inst", date(1999, 1, 1)) is None
    assert (
        await memory_cache_service.get_instructor_availability_date_range(
            "inst", date(1999, 1, 1), date(1999, 1, 2)
        )
        is None
    )
    assert await memory_cache_service.get_instructor_weekly_availability("inst-missing") is None


@pytest.mark.asyncio
async def test_warm_instructor_cache_counts(memory_cache_service: CacheService) -> None:
    class _AvailabilityStub:
        def __init__(self, _db: Any) -> None:
            pass

        def get_week_availability(self, _instructor_id: str, week_start: date) -> dict[str, Any] | None:
            return {"slots": ["09:00"]} if week_start.day % 2 == 0 else None

    with patch("app.services.availability_service.AvailabilityService", _AvailabilityStub):
        warmed = await memory_cache_service.warm_instructor_cache("inst", weeks_ahead=2)
        assert warmed >= 1


@pytest.mark.asyncio
async def test_get_stats_handles_redis_error(redis_cache_service) -> None:
    service, redis_client = redis_cache_service
    redis_client.info = AsyncMock(side_effect=RedisError("boom"))

    stats = await service.get_stats()
    assert "redis" not in stats


def test_reset_stats_clears(memory_cache_service: CacheService) -> None:
    memory_cache_service._stats["hits"] = 5
    memory_cache_service.reset_stats()
    assert memory_cache_service._stats["hits"] == 0


def test_run_cache_coroutine_closes_client_on_error() -> None:
    async def _noop() -> str:
        return "ok"

    async def _close() -> None:
        raise RuntimeError("close boom")

    clear_cache_event_loop()
    with patch("app.core.cache_redis.close_async_cache_redis_client", _close):
        assert _run_cache_coroutine(_noop()) == "ok"


@pytest.mark.asyncio
async def test_run_cache_coroutine_raises_on_event_loop_thread() -> None:
    set_cache_event_loop(asyncio.get_running_loop())
    with pytest.raises(RuntimeError):
        _run_cache_coroutine(asyncio.sleep(0))
    clear_cache_event_loop()


def test_sync_adapter_runs_coroutine(memory_cache_service: CacheService) -> None:
    clear_cache_event_loop()
    adapter = CacheServiceSyncAdapter(memory_cache_service)
    assert adapter.set("sync:key", {"a": 1}, ttl=60) is True
    assert adapter.get("sync:key") == {"a": 1}

    adapter.set_json("sync:json", {"b": 2})
    assert adapter.get_json("sync:json") == {"b": 2}

    assert adapter.cache_week_availability("inst", date.today(), {"slots": []}) is True
    assert (
        adapter.cache_instructor_availability_date_range(
            "inst", date.today(), date.today(), []
        )
        is True
    )
    assert adapter.get_instructor_availability_date_range(
        "inst", date.today(), date.today()
    ) == []

    adapter.set("sync:prefix:1", 1, ttl=60)
    assert adapter.delete("sync:key") is True
    assert adapter.delete_pattern("sync:prefix:*") >= 1
    assert adapter.clear_prefix("sync:json") >= 1
    assert "hits" in adapter.get_stats()


@pytest.mark.asyncio
async def test_sync_adapter_short_circuits_on_event_loop(memory_cache_service: CacheService) -> None:
    loop = asyncio.get_running_loop()
    set_cache_event_loop(loop)
    adapter = CacheServiceSyncAdapter(memory_cache_service)

    assert adapter.get("loop:key") is None
    assert adapter.set("loop:key", {"a": 1}) is False
    assert adapter.delete("loop:key") is False
    assert adapter.delete_pattern("loop:*") == 0
    assert adapter.clear_prefix("loop:") == 0
    assert adapter.get_stats() == {}
    assert adapter.get_json("loop:key") is None
    adapter.set_json("loop:key", {"a": 1})
    assert adapter.cache_week_availability("inst", date.today(), {"slots": []}) is False
    assert (
        adapter.get_instructor_availability_date_range(
            "inst", date.today(), date.today()
        )
        is None
    )
    assert (
        adapter.cache_instructor_availability_date_range(
            "inst", date.today(), date.today(), []
        )
        is False
    )

    async def _boom(*_args, **_kwargs) -> None:
        raise RuntimeError("boom")

    memory_cache_service.invalidate_instructor_availability = _boom  # type: ignore[assignment]
    adapter.invalidate_instructor_availability("inst")
    await asyncio.sleep(0)

    clear_cache_event_loop()


def test_get_cache_service_factory(db) -> None:
    service = get_cache_service(db)
    assert isinstance(service, CacheService)


@pytest.mark.asyncio
async def test_healthcheck_redis_client_handles_error() -> None:
    async def _boom():
        raise RuntimeError("boom")

    with patch("app.core.cache_redis.get_async_cache_redis_client", _boom):
        assert await get_healthcheck_redis_client() is None
