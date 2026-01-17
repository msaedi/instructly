from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.routes.v1 import database_monitor as routes


class _PoolStub:
    def __init__(self, *, size=10, checked_in=5, checked_out=5, overflow=0, max_overflow=5):
        self._size = size
        self._checked_in = checked_in
        self._checked_out = checked_out
        self._overflow = overflow
        self._max_overflow = max_overflow
        self._pool = SimpleNamespace(maxsize=size)
        self._timeout = 30.0
        self._recycle = 60.0

    def size(self):
        return self._size

    def checkedin(self):
        return self._checked_in

    def checkedout(self):
        return self._checked_out

    def overflow(self):
        return self._overflow


@pytest.mark.asyncio
async def test_database_health_success(monkeypatch):
    # Must provide all required fields for DatabasePoolMetrics
    pool_status = {
        "size": 5,
        "checked_in": 3,
        "checked_out": 2,
        "overflow": 0,
        "total": 5,
        "max_size": 10,
        "usage_percent": 20.0,
    }
    monkeypatch.setattr(routes, "get_db_pool_status", lambda: pool_status)

    response = await routes.database_health()

    assert response.status == "healthy"


@pytest.mark.asyncio
async def test_database_health_failure(monkeypatch):
    monkeypatch.setattr(routes, "get_db_pool_status", lambda: (_ for _ in ()).throw(Exception("boom")))

    response = await routes.database_health()

    assert response.status == "unhealthy"
    assert response.error == "boom"


@pytest.mark.asyncio
async def test_database_pool_status_critical(monkeypatch):
    pool = _PoolStub(size=2, checked_in=0, checked_out=4, overflow=2, max_overflow=2)
    monkeypatch.setattr(routes, "engine", SimpleNamespace(pool=pool))

    response = await routes.database_pool_status(current_user=SimpleNamespace())

    assert response.status == "critical"
    assert response.pool.usage_percent > 80


@pytest.mark.asyncio
async def test_database_pool_status_error(monkeypatch):
    monkeypatch.setattr(routes, "engine", SimpleNamespace(pool=None))

    with pytest.raises(Exception) as exc:
        await routes.database_pool_status(current_user=SimpleNamespace())
    assert getattr(exc.value, "status_code", None) == 500


@pytest.mark.asyncio
async def test_database_stats_success(monkeypatch):
    # Import the actual response schema to create a proper mock
    from app.schemas.database_monitor_responses import (
        DatabasePoolConfiguration,
        DatabasePoolMetrics,
        DatabasePoolStatusResponse,
        DatabaseRecommendations,
    )

    # Create a proper DatabasePoolStatusResponse instance
    pool_metrics = DatabasePoolMetrics(
        size=1,
        checked_in=1,
        checked_out=0,
        overflow=0,
        total=1,
        max_size=5,
        usage_percent=10.0,
    )
    configuration = DatabasePoolConfiguration(
        pool_size=1,
        max_overflow=4,
        timeout=30.0,
        recycle=3600.0,
    )
    recommendations = DatabaseRecommendations(
        increase_pool_size=False,
        current_load="low",
    )
    pool_status = DatabasePoolStatusResponse(
        status="healthy",
        pool=pool_metrics,
        configuration=configuration,
        recommendations=recommendations,
    )

    async def _pool_status(_user):
        return pool_status

    monkeypatch.setattr(routes, "database_pool_status", _pool_status)

    response = await routes.database_stats(current_user=SimpleNamespace())

    assert response.health.status == "healthy"


@pytest.mark.asyncio
async def test_database_stats_error(monkeypatch):
    async def _boom(_user):
        raise RuntimeError("fail")

    monkeypatch.setattr(routes, "database_pool_status", _boom)

    with pytest.raises(Exception) as exc:
        await routes.database_stats(current_user=SimpleNamespace())
    assert getattr(exc.value, "status_code", None) == 500
