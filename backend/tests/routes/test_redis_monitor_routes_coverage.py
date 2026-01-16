from __future__ import annotations

from types import SimpleNamespace

from fastapi import HTTPException
import pytest

import app.routes.v1.redis_monitor as redis_routes


class _DummyRedis:
    def __init__(self) -> None:
        self._info = {
            "redis_version": "7.0",
            "uptime_in_seconds": 123,
            "uptime_in_days": 1,
            "used_memory_human": "10M",
            "used_memory_peak_human": "12M",
            "used_memory_rss_human": "11M",
            "maxmemory_human": "64M",
            "mem_fragmentation_ratio": 1.2,
            "total_connections_received": 3,
            "total_commands_processed": 5,
            "instantaneous_ops_per_sec": 2,
            "rejected_connections": 0,
            "expired_keys": 1,
            "evicted_keys": 0,
            "connected_clients": 4,
            "blocked_clients": 0,
        }

    async def ping(self) -> bool:
        return True

    async def info(self, section: str | None = None) -> dict:
        if section == "server":
            return {
                "redis_version": self._info["redis_version"],
                "uptime_in_seconds": self._info["uptime_in_seconds"],
            }
        if section == "clients":
            return {"connected_clients": self._info["connected_clients"]}
        return dict(self._info)

    async def llen(self, queue: str) -> int:
        return 2 if queue == "celery" else 0

    async def delete(self, _queue: str) -> int:
        return 1


@pytest.mark.asyncio
async def test_redis_health_ok(monkeypatch) -> None:
    async def _client():
        return _DummyRedis()

    monkeypatch.setattr(redis_routes, "get_redis_client", _client)
    response = await redis_routes.redis_health()
    assert response.status == "healthy"
    assert response.connected is True


@pytest.mark.asyncio
async def test_redis_health_unhealthy(monkeypatch) -> None:
    async def _boom():
        raise RuntimeError("down")

    monkeypatch.setattr(redis_routes, "get_redis_client", _boom)
    response = await redis_routes.redis_health()
    assert response.status == "unhealthy"
    assert response.connected is False


@pytest.mark.asyncio
async def test_redis_test_success(monkeypatch) -> None:
    async def _client():
        return _DummyRedis()

    monkeypatch.setattr(redis_routes, "get_redis_client", _client)
    response = await redis_routes.redis_test()
    assert response.status == "connected"
    assert response.redis_version == "7.0"


@pytest.mark.asyncio
async def test_redis_test_error(monkeypatch) -> None:
    async def _boom():
        raise RuntimeError("down")

    monkeypatch.setattr(redis_routes, "get_redis_client", _boom)
    response = await redis_routes.redis_test()
    assert response.status == "error"
    assert response.ping is False


@pytest.mark.asyncio
async def test_redis_stats_and_celery_queue_status(monkeypatch) -> None:
    async def _client():
        return _DummyRedis()

    async def _queues(_client):
        return {"celery": 2, "email": 0}

    monkeypatch.setattr(redis_routes, "get_redis_client", _client)
    monkeypatch.setattr(redis_routes, "_get_celery_queue_lengths", _queues)

    stats = await redis_routes.redis_stats(current_user=SimpleNamespace())
    assert stats.stats["stats"]["instantaneous_ops_per_sec"] == 2

    queues = await redis_routes.celery_queue_status(current_user=SimpleNamespace())
    assert queues.queues["total_pending"] == 2


@pytest.mark.asyncio
async def test_get_celery_queue_lengths_handles_failure() -> None:
    class _FailingRedis(_DummyRedis):
        async def llen(self, queue: str) -> int:
            if queue == "email":
                raise RuntimeError("boom")
            return await super().llen(queue)

    lengths = await redis_routes._get_celery_queue_lengths(_FailingRedis())
    assert lengths["email"] == -1


@pytest.mark.asyncio
async def test_redis_connection_audit(monkeypatch) -> None:
    monkeypatch.setattr(redis_routes.settings, "redis_url", "redis://localhost:6379/0")
    async def _client():
        return _DummyRedis()

    monkeypatch.setattr(redis_routes, "get_redis_client", _client)

    response = await redis_routes.redis_connection_audit(current_user=SimpleNamespace())
    assert response.connections[0]["upstash_detected"] is False
    assert "redis://localhost:6379/0" in response.connections[0]["api_cache"]


@pytest.mark.asyncio
async def test_get_redis_client_unavailable(monkeypatch) -> None:
    async def _none():
        return None

    monkeypatch.setattr(redis_routes, "get_async_cache_redis_client", _none)

    with pytest.raises(RuntimeError, match="Redis unavailable"):
        await redis_routes.get_redis_client()


@pytest.mark.asyncio
async def test_redis_stats_error(monkeypatch) -> None:
    async def _boom():
        raise RuntimeError("down")

    monkeypatch.setattr(redis_routes, "get_redis_client", _boom)

    with pytest.raises(HTTPException) as exc:
        await redis_routes.redis_stats(current_user=SimpleNamespace())
    assert exc.value.status_code == 500


@pytest.mark.asyncio
async def test_celery_queue_status_error(monkeypatch) -> None:
    async def _client():
        return _DummyRedis()

    async def _boom(_client):
        raise RuntimeError("queue fail")

    monkeypatch.setattr(redis_routes, "get_redis_client", _client)
    monkeypatch.setattr(redis_routes, "_get_celery_queue_lengths", _boom)

    with pytest.raises(HTTPException) as exc:
        await redis_routes.celery_queue_status(current_user=SimpleNamespace())
    assert exc.value.status_code == 500


@pytest.mark.asyncio
async def test_redis_connection_audit_handles_error(monkeypatch) -> None:
    async def _boom():
        raise RuntimeError("down")

    monkeypatch.setattr(redis_routes.settings, "redis_url", "")
    monkeypatch.setattr(redis_routes, "get_redis_client", _boom)

    with pytest.raises(HTTPException) as exc:
        await redis_routes.redis_connection_audit(current_user=SimpleNamespace())
    assert exc.value.status_code == 500


@pytest.mark.asyncio
async def test_flush_celery_queues(monkeypatch) -> None:
    class _FlushRedis(_DummyRedis):
        async def delete(self, queue: str) -> int:
            if queue == "email":
                raise RuntimeError("delete fail")
            return 1

        async def llen(self, queue: str) -> int:
            if queue == "email":
                return 2
            return await super().llen(queue)

    async def _client():
        return _FlushRedis()

    monkeypatch.setattr(redis_routes, "get_redis_client", _client)
    response = await redis_routes.flush_celery_queues(current_user=SimpleNamespace())
    assert "celery" in response.queues_flushed


@pytest.mark.asyncio
async def test_flush_celery_queues_error(monkeypatch) -> None:
    async def _boom():
        raise RuntimeError("down")

    monkeypatch.setattr(redis_routes, "get_redis_client", _boom)

    with pytest.raises(HTTPException) as exc:
        await redis_routes.flush_celery_queues(current_user=SimpleNamespace())
    assert exc.value.status_code == 500
