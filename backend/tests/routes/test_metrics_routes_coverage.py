from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from fastapi import HTTPException, Request
import pytest

import app.routes.v1.metrics as metrics_routes


def _request() -> Request:
    return Request({"type": "http", "headers": []})


def test_ops_admin_required_modes(monkeypatch) -> None:
    monkeypatch.setenv("SITE_MODE", "prod")
    assert metrics_routes._ops_admin_required() is True

    monkeypatch.setenv("SITE_MODE", "beta")
    assert metrics_routes._ops_admin_required() is True

    monkeypatch.delenv("SITE_MODE", raising=False)
    assert metrics_routes._ops_admin_required() is False


@pytest.mark.asyncio
async def test_get_optional_user() -> None:
    class _Auth:
        def get_user_by_email(self, email: str):
            return SimpleNamespace(email=email)

    user = await metrics_routes._get_optional_user("admin@example.com", _Auth())
    assert user.email == "admin@example.com"
    assert await metrics_routes._get_optional_user(None, _Auth()) is None


@pytest.mark.asyncio
async def test_ensure_ops_access_behaviour(monkeypatch) -> None:
    monkeypatch.delenv("SITE_MODE", raising=False)
    assert await metrics_routes._ensure_ops_access(_request(), None) is None

    monkeypatch.setenv("SITE_MODE", "prod")
    with pytest.raises(HTTPException):
        await metrics_routes._ensure_ops_access(_request(), None)

    admin = SimpleNamespace(is_admin=True)
    assert await metrics_routes._ensure_ops_access(_request(), admin) is admin


def test_normalize_service_metrics() -> None:
    assert metrics_routes._normalize_service_metrics(None)["total_operations"] == 0

    metrics = metrics_routes._normalize_service_metrics({"op": {"count": "3"}})
    assert metrics["operations"]["op"] == 3
    assert metrics["total_operations"] == 3


def test_coerce_json_dict() -> None:
    assert metrics_routes._coerce_json_dict({"a": 1}, "err")["a"] == 1
    assert metrics_routes._coerce_json_dict(["bad"], "err")["error"] == "err"


def test_metrics_lite_returns_text(monkeypatch) -> None:
    monkeypatch.setattr(metrics_routes.retention_metrics, "render_text", lambda: "ok")
    assert metrics_routes.metrics_lite() == "ok"


@pytest.mark.asyncio
async def test_get_performance_metrics(monkeypatch) -> None:
    class _Service:
        def get_metrics(self):
            return {"op": {"count": 2}}

    cache_service = SimpleNamespace(
        get_stats=AsyncMock(return_value={"hits": 2, "misses": 1, "errors": 0})
    )
    metrics_repository = SimpleNamespace(get_active_connections_count=lambda: 3)

    monkeypatch.setattr(metrics_routes.psutil, "cpu_percent", lambda interval=1: 12.5)
    monkeypatch.setattr(
        metrics_routes.psutil, "virtual_memory", lambda: SimpleNamespace(percent=35.0)
    )
    monkeypatch.setattr(
        metrics_routes.psutil, "disk_usage", lambda _path: SimpleNamespace(percent=70.0)
    )
    # Must provide all required fields for DatabasePoolStatus
    pool_status = {
        "size": 10,
        "max_overflow": 5,
        "max_capacity": 15,
        "checked_in": 8,
        "checked_out": 2,
        "overflow_in_use": 0,
        "utilization_pct": 20.0,
    }
    monkeypatch.setattr(metrics_routes, "get_db_pool_status", lambda: pool_status)

    response = await metrics_routes.get_performance_metrics(
        availability_service=_Service(),
        booking_service=_Service(),
        conflict_checker=_Service(),
        cache_service=cache_service,
        metrics_repository=metrics_repository,
    )

    assert response.database.active_connections == 3
    # system remains Dict[str, float]
    assert response.system["cpu_percent"] == 12.5
    assert response.cache.hits == 2


@pytest.mark.asyncio
async def test_get_cache_metrics_branches(monkeypatch) -> None:
    with pytest.raises(HTTPException):
        await metrics_routes.get_cache_metrics(cache_service=None)

    class _Redis:
        async def info(self):
            return {"used_memory_human": "1M", "keyspace_hits": 2, "keyspace_misses": 1}

    cache_service = SimpleNamespace(
        get_stats=AsyncMock(
            return_value={
                "hits": 2,
                "misses": 8,
                "errors": 1,
                "availability_hits": 1,
                "availability_misses": 3,
                "availability_invalidations": 150,
            }
        ),
        get_redis_client=AsyncMock(return_value=_Redis()),
    )

    response = await metrics_routes.get_cache_metrics(cache_service=cache_service)
    # redis_info remains Dict[str, Any]
    assert response.redis_info["used_memory_human"] == "1M"
    assert response.availability_metrics.availability_total_requests == 4
    assert response.performance_insights


def test_cache_performance_insights() -> None:
    stats = {
        "hits": 1,
        "misses": 9,
        "errors": 1,
        "availability_hits": 1,
        "availability_misses": 4,
        "availability_invalidations": 200,
    }
    insights = metrics_routes._get_cache_performance_insights(stats)
    assert any("Low cache hit rate" in entry for entry in insights)
    assert any("High availability cache invalidation rate" in entry for entry in insights)


@pytest.mark.asyncio
async def test_get_availability_cache_metrics(monkeypatch) -> None:
    class _Redis:
        async def scan_iter(self, match: str, count: int):
            for key in ["avail:1", "availability:2"]:
                yield key

    cache_service = SimpleNamespace(
        get_stats=AsyncMock(
            return_value={
                "availability_hits": 1,
                "availability_misses": 3,
                "availability_invalidations": 1,
            }
        ),
        get_redis_client=AsyncMock(return_value=_Redis()),
    )

    response = await metrics_routes.get_availability_cache_metrics(cache_service=cache_service)
    assert response.availability_cache_metrics.total_requests == 4
    assert response.top_cached_keys_sample


@pytest.mark.asyncio
async def test_get_slow_queries(monkeypatch) -> None:
    metrics_repository = SimpleNamespace(
        get_slow_queries=lambda: [{"query": "SELECT 1", "mean_exec_time": 123.4}]
    )
    response = await metrics_routes.get_slow_queries(metrics_repository=metrics_repository)
    assert response.total_count == 1
    assert response.slow_queries[0].duration_ms == 123.4


@pytest.mark.asyncio
async def test_reset_cache_stats(monkeypatch) -> None:
    cache_service = SimpleNamespace(reset_stats=MagicMock())
    response = await metrics_routes.reset_cache_stats(cache_service=cache_service)
    cache_service.reset_stats.assert_called_once()
    assert response.success is True

    with pytest.raises(HTTPException):
        await metrics_routes.reset_cache_stats(cache_service=None)


@pytest.mark.asyncio
async def test_rate_limit_admin_endpoints(monkeypatch) -> None:
    async def _stats():
        return {
            "total_keys": 1,
            "breakdown_by_type": {"minute": 1},
            "top_limited_clients": [],
        }

    async def _reset(_pattern: str):
        return 2

    monkeypatch.setattr(metrics_routes.RateLimitAdmin, "get_rate_limit_stats", _stats)
    monkeypatch.setattr(metrics_routes.RateLimitAdmin, "reset_all_limits", _reset)

    stats = await metrics_routes.get_rate_limit_stats()
    assert stats.total_keys == 1

    reset = await metrics_routes.reset_rate_limits("email_*")
    assert reset.limits_reset == 2


@pytest.mark.asyncio
async def test_rate_limit_test_endpoint(monkeypatch) -> None:
    class _Limiter:
        async def check_rate_limit(self, **_kwargs):
            return True, 1, 0

        async def get_remaining_requests(self, **_kwargs):
            return 2

    monkeypatch.setattr(metrics_routes.rate_limiter_module, "RateLimiter", _Limiter)

    response = await metrics_routes.test_rate_limit(_request(), requests=3)
    assert response.message == "Rate limit test successful"
