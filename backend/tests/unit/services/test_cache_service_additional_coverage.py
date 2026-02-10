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


def test_cache_key_builder_datetime_branch() -> None:
    stamp = datetime(2024, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    key = CacheKeyBuilder.build("stats", stamp)
    assert key.startswith("stats:")
    assert "2024-01-02T03:04:05" in key


@pytest.mark.asyncio
async def test_backend_get_returns_none_when_redis_present_but_circuit_open() -> None:
    cache = CacheService(redis_client=AsyncMock())
    cache.circuit_breaker._state = CircuitState.OPEN
    cache.force_memory_cache = False
    assert await cache._backend_get("k") is None


@pytest.mark.asyncio
async def test_backend_set_returns_false_when_circuit_call_returns_false() -> None:
    redis_client = AsyncMock()
    cache = CacheService(redis_client=redis_client)
    cache.force_memory_cache = False
    cache.circuit_breaker.call = AsyncMock(return_value=False)
    assert await cache._backend_set("k", "v", 30) is False


@pytest.mark.asyncio
async def test_get_json_returns_raw_non_string_payload() -> None:
    cache = CacheService(redis_client=None)
    cache._backend_get = AsyncMock(return_value={"a": 1})  # type: ignore[assignment]
    value = await cache.get_json("json:key")
    assert value == {"a": 1}


@pytest.mark.asyncio
async def test_set_returns_false_when_redis_present_but_circuit_open() -> None:
    cache = CacheService(redis_client=AsyncMock())
    cache.circuit_breaker._state = CircuitState.OPEN
    cache.force_memory_cache = False
    assert await cache.set("k", {"v": 1}, ttl=10) is False


@pytest.mark.asyncio
async def test_delete_returns_false_when_redis_present_but_circuit_open() -> None:
    cache = CacheService(redis_client=AsyncMock())
    cache.circuit_breaker._state = CircuitState.OPEN
    cache.force_memory_cache = False
    assert await cache.delete("k") is False


@pytest.mark.asyncio
async def test_delete_pattern_handles_backend_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    cache = CacheService(redis_client=AsyncMock())
    cache.force_memory_cache = False
    monkeypatch.setattr(cache, "_delete_pattern_redis", AsyncMock(side_effect=RuntimeError("boom")))
    deleted = await cache.delete_pattern("x:*")
    assert deleted == 0
    assert cache._stats["errors"] >= 1


@pytest.mark.asyncio
async def test_delete_pattern_redis_skips_non_deleted_entries() -> None:
    redis_client = AsyncMock()

    async def _scan_iter(match: str):
        yield "key-1"
        yield "key-2"

    redis_client.scan_iter = _scan_iter
    redis_client.delete = AsyncMock(side_effect=[1, 0])
    cache = CacheService(redis_client=redis_client)
    cache.force_memory_cache = False
    assert await cache._delete_pattern_redis("key-*") == 1


@pytest.mark.asyncio
async def test_acquire_and_release_lock_error_branches() -> None:
    redis_client = AsyncMock()
    redis_client.set.side_effect = RuntimeError("lock fail")
    redis_client.delete.side_effect = RuntimeError("unlock fail")
    cache = CacheService(redis_client=redis_client)
    cache.force_memory_cache = False

    # acquire_lock fail-open on error
    assert await cache.acquire_lock("lock:key") is True
    # release_lock returns False on error
    assert await cache.release_lock("lock:key") is False


@pytest.mark.asyncio
async def test_batch_cache_availability_ignores_unrecognized_entry_shape() -> None:
    cache = CacheService(redis_client=None)
    cache.mset = AsyncMock(return_value=True)
    count = await cache.batch_cache_availability(
        [
            {"instructor_id": "i1", "data": {"slots": []}},
            {"instructor_id": "i2", "week_start": date(2024, 1, 1), "data": {"slots": []}},
        ]
    )
    assert count == 1


@pytest.mark.asyncio
async def test_cached_decorator_does_not_cache_none_results() -> None:
    cache = CacheService(redis_client=None)
    cache.get = AsyncMock(return_value=None)
    cache.set = AsyncMock(return_value=True)

    async def _workload(_: int) -> None:
        return None

    wrapped = cache.cached(lambda value: f"key:{value}")(_workload)
    assert await wrapped(10) is None
    cache.set.assert_not_called()


def test_run_cache_coroutine_closes_coro_when_fallback_run_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    loop = asyncio.new_event_loop()
    set_cache_event_loop(loop)
    try:
        monkeypatch.setattr("app.services.cache_service._cache_event_loop_thread_id", -1)
        monkeypatch.setattr(
            asyncio,
            "run_coroutine_threadsafe",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("threadsafe failed")),
        )
        def _raise_fallback(coro):
            coro.close()
            raise RuntimeError("fallback failed")
        monkeypatch.setattr(
            asyncio,
            "run",
            _raise_fallback,
        )

        async def _boom() -> str:
            return "never"

        with pytest.raises(RuntimeError, match="fallback failed"):
            _run_cache_coroutine(_boom())
    finally:
        clear_cache_event_loop()
        loop.close()
