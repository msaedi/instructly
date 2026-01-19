"""Additional unit coverage for CacheService and helpers."""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.cache_service import (
    CacheKeyBuilder,
    CacheService,
    CacheServiceSyncAdapter,
    CircuitBreaker,
    CircuitState,
    _run_cache_coroutine,
    clear_cache_event_loop,
    set_cache_event_loop,
)


def test_circuit_breaker_half_open_transition() -> None:
    breaker = CircuitBreaker(recovery_timeout=0)
    breaker._state = CircuitState.OPEN
    breaker._last_failure_time = datetime.now(timezone.utc) - timedelta(seconds=1)

    assert breaker.state == CircuitState.HALF_OPEN


def test_cache_key_builder_uses_datetime_and_prefix() -> None:
    stamp = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
    key = CacheKeyBuilder.build("availability", stamp)

    assert key.startswith("avail:")
    assert stamp.isoformat() in key


@pytest.mark.asyncio
async def test_backend_get_returns_none_when_circuit_open() -> None:
    cache = CacheService(redis_client=AsyncMock())
    cache.circuit_breaker._state = CircuitState.OPEN

    assert await cache._backend_get("key") is None


@pytest.mark.asyncio
async def test_backend_set_returns_false_when_circuit_open() -> None:
    cache = CacheService(redis_client=AsyncMock())
    cache.force_memory_cache = False
    cache.circuit_breaker._state = CircuitState.OPEN

    assert await cache._backend_set("key", "value", 10) is False


@pytest.mark.asyncio
async def test_backend_set_missing_ttl_returns_false(monkeypatch: pytest.MonkeyPatch) -> None:
    cache = CacheService(redis_client=None)
    monkeypatch.setattr(cache, "TTL_TIERS", {"warm": None})

    assert await cache._backend_set("key", "value", None) is False


@pytest.mark.asyncio
async def test_cache_get_handles_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    cache = CacheService(redis_client=None)

    async def _boom(_: str) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(cache, "_backend_get", _boom)

    assert await cache.get("key") is None


@pytest.mark.asyncio
async def test_cache_set_missing_ttl_returns_false(monkeypatch: pytest.MonkeyPatch) -> None:
    cache = CacheService(redis_client=None)
    monkeypatch.setattr(cache, "TTL_TIERS", {"warm": None})

    assert await cache.set("key", {"value": 1}, ttl=None, tier="warm") is False


@pytest.mark.asyncio
async def test_cache_delete_handles_exception() -> None:
    redis_client = AsyncMock()
    redis_client.delete.side_effect = RuntimeError("boom")
    cache = CacheService(redis_client=redis_client)

    assert await cache.delete("key") is False


@pytest.mark.asyncio
async def test_delete_pattern_redis_none_returns_zero() -> None:
    cache = CacheService(redis_client=None)

    assert await cache._delete_pattern_redis("missing:*") == 0


@pytest.mark.asyncio
async def test_delete_pattern_redis_counts_deletes() -> None:
    redis_client = AsyncMock()

    async def _scan_iter(match: str):
        yield "key-1"

    redis_client.scan_iter = _scan_iter
    redis_client.delete = AsyncMock(return_value=1)
    cache = CacheService(redis_client=redis_client)
    cache.force_memory_cache = False

    assert await cache._delete_pattern_redis("key-*") == 1


@pytest.mark.asyncio
async def test_mget_handles_non_json() -> None:
    redis_client = AsyncMock()
    redis_client.mget.return_value = [b'{"a": 1}', b"not-json"]
    cache = CacheService(redis_client=redis_client)
    cache.force_memory_cache = False

    result = await cache.mget(["k1", "k2"])

    assert result["k1"]["a"] == 1
    assert result["k2"] == b"not-json"


@pytest.mark.asyncio
async def test_mget_handles_exception() -> None:
    redis_client = AsyncMock()
    redis_client.mget.side_effect = RuntimeError("boom")
    cache = CacheService(redis_client=redis_client)
    cache.force_memory_cache = False

    result = await cache.mget(["k1"])

    assert result == {}
    assert cache._stats["errors"] >= 1


@pytest.mark.asyncio
async def test_mset_missing_ttl_returns_false(monkeypatch: pytest.MonkeyPatch) -> None:
    cache = CacheService(redis_client=None)
    monkeypatch.setattr(cache, "TTL_TIERS", {"warm": None})

    assert await cache.mset({"k": "v"}) is False


@pytest.mark.asyncio
async def test_batch_cache_availability_date_range_entry() -> None:
    cache = CacheService(redis_client=None)
    cache.mset = AsyncMock(return_value=True)
    entries = [
        {
            "instructor_id": "inst",
            "start_date": date(2024, 1, 1),
            "end_date": date(2024, 1, 2),
            "data": {"slots": []},
        }
    ]

    assert await cache.batch_cache_availability(entries) == 1


@pytest.mark.asyncio
async def test_cached_decorator_sets_value() -> None:
    cache = CacheService(redis_client=None)
    cache.get = AsyncMock(return_value=None)
    cache.set = AsyncMock(return_value=True)

    async def _workload(value: int) -> dict[str, int]:
        return {"value": value}

    wrapped = cache.cached(lambda value: f"key:{value}")(_workload)
    assert await wrapped(5) == {"value": 5}
    cache.set.assert_called_once()


def test_run_cache_coroutine_fallback_when_threadsafe_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    loop = asyncio.new_event_loop()
    set_cache_event_loop(loop)
    try:
        monkeypatch.setattr("app.services.cache_service._cache_event_loop_thread_id", -1)

        def _raise(*_: object) -> None:
            raise RuntimeError("boom")

        monkeypatch.setattr(asyncio, "run_coroutine_threadsafe", _raise)

        async def _sample() -> str:
            return "ok"

        result = _run_cache_coroutine(_sample())

        assert result == "ok"
    finally:
        clear_cache_event_loop()
        loop.close()


def test_sync_adapter_invalidate_handles_cancelled_task(monkeypatch: pytest.MonkeyPatch) -> None:
    cache_service = AsyncMock()
    adapter = CacheServiceSyncAdapter(cache_service)

    class DummyTask:
        def __init__(self) -> None:
            self._callback = None

        def add_done_callback(self, callback) -> None:
            self._callback = callback

        def cancelled(self) -> bool:
            return True

        def exception(self):
            return None

    task = DummyTask()
    def _create_task(coro):
        coro.close()
        return task

    loop = SimpleNamespace(create_task=_create_task)

    monkeypatch.setattr(adapter, "_is_event_loop_thread", lambda: True)
    monkeypatch.setattr(asyncio, "get_running_loop", lambda: loop)

    adapter.invalidate_instructor_availability("inst", dates=None)
    assert task._callback is not None
    task._callback(task)


def test_sync_adapter_invalidate_handles_missing_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    cache_service = AsyncMock()
    adapter = CacheServiceSyncAdapter(cache_service)

    monkeypatch.setattr(adapter, "_is_event_loop_thread", lambda: True)
    monkeypatch.setattr(asyncio, "get_running_loop", lambda: (_ for _ in ()).throw(RuntimeError()))

    adapter.invalidate_instructor_availability("inst", dates=None)
