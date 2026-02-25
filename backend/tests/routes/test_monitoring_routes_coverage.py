from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
import pytest

from app.models.booking import PaymentStatus
import app.routes.v1.monitoring as monitoring_routes


class _DummyCacheService:
    async def get_stats(self) -> dict:
        return {
            "basic_stats": {"hits": 5, "misses": 1},
            "redis": {"used_memory_human": "1M"},
            "key_patterns": {"avail:*": 3},
        }


@pytest.mark.asyncio
async def test_verify_monitoring_api_key_allows_non_prod(monkeypatch) -> None:
    monkeypatch.setattr(monitoring_routes.settings, "environment", "local", raising=False)
    await monitoring_routes.verify_monitoring_api_key(api_key=None)


@pytest.mark.asyncio
async def test_verify_monitoring_api_key_missing_in_production(monkeypatch) -> None:
    monkeypatch.setattr(monitoring_routes.settings, "environment", "production", raising=False)
    monkeypatch.delenv("MONITORING_API_KEY", raising=False)

    with pytest.raises(HTTPException) as exc:
        await monitoring_routes.verify_monitoring_api_key(api_key=None)

    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_verify_monitoring_api_key_invalid(monkeypatch) -> None:
    monkeypatch.setattr(monitoring_routes.settings, "environment", "production", raising=False)
    monkeypatch.setenv("MONITORING_API_KEY", "expected-key")

    with pytest.raises(HTTPException) as exc:
        await monitoring_routes.verify_monitoring_api_key(api_key="wrong-key")

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_get_monitoring_dashboard_success(monkeypatch, db) -> None:
    now = datetime.now(timezone.utc)
    performance = {
        "timestamp": now,
        "database": {"average_pool_usage_percent": 80, "slow_queries_count": 25},
        "requests": {"active_count": 60, "total_count": 120, "average_response_time_ms": 45.2},
        "memory": {"used_mb": 8000.0, "total_mb": 10000.0, "percent": 80.0},
        "alerts": [],
    }
    cache_health = {
        "status": "healthy",
        "hit_rate": "95.0%",
        "total_requests": 20,
        "errors": 0,
        "recommendations": ["Tune TTL for availability cache"],
    }

    monkeypatch.setattr(monitoring_routes.settings, "environment", "local", raising=False)
    monkeypatch.setattr(
        monitoring_routes.monitor, "get_performance_summary", lambda: performance
    )
    monkeypatch.setattr(
        monitoring_routes.monitor, "check_cache_health", lambda _stats: cache_health
    )
    monkeypatch.setattr(monitoring_routes, "get_cache_service", lambda _db: _DummyCacheService())
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
    monkeypatch.setattr(monitoring_routes, "get_db_pool_status", lambda: pool_status)

    response = await monitoring_routes.get_monitoring_dashboard(db)

    assert response.status == "ok"
    assert response.database.pool.size == 10
    assert response.cache.status == "healthy"
    assert response.recommendations


@pytest.mark.asyncio
async def test_get_monitoring_dashboard_error(monkeypatch, db) -> None:
    monkeypatch.setattr(monitoring_routes.settings, "environment", "local", raising=False)
    monkeypatch.setattr(
        monitoring_routes.monitor,
        "get_performance_summary",
        lambda: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    with pytest.raises(HTTPException) as exc:
        await monitoring_routes.get_monitoring_dashboard(db)

    assert exc.value.status_code == 500


@pytest.mark.asyncio
async def test_get_slow_queries_and_requests(monkeypatch) -> None:
    now = datetime.now(timezone.utc)
    monkeypatch.setattr(
        monitoring_routes.monitor,
        "slow_queries",
        [
            {
                "query": "SELECT 1",
                "duration_ms": 123.4,
                "timestamp": now,
                "endpoint": "/api/v1/bookings",
            },
            {
                "query": "SELECT 2",
                "duration_ms": 456.7,
                "timestamp": now,
                "endpoint": "/api/v1/bookings",
            },
            {
                "query": "SELECT 3",
                "duration_ms": 789.0,
                "timestamp": now,
                "endpoint": "/api/v1/bookings",
            },
        ],
    )
    monkeypatch.setattr(
        monitoring_routes.monitor,
        "slow_requests",
        [
            {
                "path": "/api/v1/search",
                "method": "GET",
                "duration_ms": 999.0,
                "timestamp": now,
                "status_code": 200,
            }
        ],
    )

    queries = await monitoring_routes.get_slow_queries(limit=2)
    requests = await monitoring_routes.get_slow_requests(limit=5)

    assert queries.total_count >= 3
    assert len(queries.slow_queries) == 2
    assert requests.total_count == 1


@pytest.mark.asyncio
async def test_get_extended_cache_stats(monkeypatch, db) -> None:
    monkeypatch.setattr(monitoring_routes, "get_cache_service", lambda _db: _DummyCacheService())
    stats = await monitoring_routes.get_extended_cache_stats(db)

    assert stats.basic_stats.hits == 5
    # redis_info and key_patterns remain Dict types
    assert stats.redis_info["used_memory_human"] == "1M"
    assert stats.key_patterns["avail:*"] == 3


@pytest.mark.asyncio
async def test_acknowledge_alert(monkeypatch) -> None:
    monkeypatch.setattr(
        monitoring_routes.monitor, "_last_alert_time", {"cpu": datetime.now(timezone.utc)}
    )
    acknowledged = await monitoring_routes.acknowledge_alert("cpu")
    assert acknowledged.status == "acknowledged"

    with pytest.raises(HTTPException) as exc:
        await monitoring_routes.acknowledge_alert("missing")

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_get_payment_system_health_branches() -> None:
    now = datetime.now(timezone.utc)

    class _Repo:
        def get_payment_status_counts(self, _now):
            return [
                SimpleNamespace(
                    payment_status=PaymentStatus.PAYMENT_METHOD_REQUIRED.value,
                    count=6,
                ),
                SimpleNamespace(payment_status=PaymentStatus.AUTHORIZED.value, count=2),
            ]

        def get_recent_event_counts(self, _since):
            return [SimpleNamespace(event_type="auth", count=3)]

        def count_overdue_authorizations(self, _now):
            return 12

        def get_last_successful_authorization(self):
            return SimpleNamespace(created_at=now - timedelta(minutes=180))

    response = await monitoring_routes.get_payment_system_health(_Repo())
    assert response.status == "critical"
    assert response.minutes_since_last_auth == 180
    assert any("overdue" in alert for alert in response.alerts)


@pytest.mark.asyncio
async def test_trigger_payment_health_check(monkeypatch) -> None:
    class _Task:
        id = "task-123"

    with patch("app.routes.v1.monitoring.enqueue_task", return_value=_Task()) as mock_enqueue:
        response = await monitoring_routes.trigger_payment_health_check()

    assert response.task_id == "task-123"
    mock_enqueue.assert_called_once_with("app.tasks.payment_tasks.check_authorization_health")


@pytest.mark.asyncio
async def test_trigger_payment_health_check_error(monkeypatch) -> None:
    with patch(
        "app.routes.v1.monitoring.enqueue_task",
        side_effect=RuntimeError("boom"),
    ):
        with pytest.raises(HTTPException) as exc:
            await monitoring_routes.trigger_payment_health_check()

    assert exc.value.status_code == 500


# ---- L60: api_key mismatch with correct MONITORING_API_KEY set ----
@pytest.mark.asyncio
async def test_verify_monitoring_api_key_valid(monkeypatch) -> None:
    monkeypatch.setattr(monitoring_routes.settings, "environment", "production", raising=False)
    monkeypatch.setenv("MONITORING_API_KEY", "correct-key")

    # Should not raise with matching key
    await monitoring_routes.verify_monitoring_api_key(api_key="correct-key")


# ---- L161-178: _generate_recommendations thresholds ----
def test_generate_recommendations_no_issues() -> None:
    performance = {
        "database": {"average_pool_usage_percent": 30, "slow_queries_count": 5},
        "requests": {"active_count": 10},
        "memory": {"percent": 40},
    }
    cache_health: dict = {}
    recs = monitoring_routes._generate_recommendations(performance, cache_health)
    assert recs == []


def test_generate_recommendations_all_thresholds() -> None:
    performance = {
        "database": {"average_pool_usage_percent": 80, "slow_queries_count": 25},
        "requests": {"active_count": 60},
        "memory": {"percent": 80},
    }
    cache_health = {"recommendations": ["Tune cache TTL"]}
    recs = monitoring_routes._generate_recommendations(performance, cache_health)
    types = [r["type"] for r in recs]
    assert "database" in types
    assert "cache" in types
    assert "memory" in types
    assert "requests" in types
    # Should have at least 5 recommendations (2 db + 1 cache + 1 memory + 1 requests)
    assert len(recs) >= 5


def test_generate_recommendations_only_db_pool() -> None:
    performance = {
        "database": {"average_pool_usage_percent": 71, "slow_queries_count": 5},
        "requests": {"active_count": 10},
        "memory": {"percent": 40},
    }
    recs = monitoring_routes._generate_recommendations(performance, {})
    assert len(recs) == 1
    assert recs[0]["type"] == "database"
    assert "pool" in recs[0]["message"].lower()


# ---- L227-229: payment health with no overdue and no last auth ----
@pytest.mark.asyncio
async def test_payment_health_healthy_no_auth() -> None:
    class _Repo:
        def get_payment_status_counts(self, _now):
            return []

        def get_recent_event_counts(self, _since):
            return []

        def count_overdue_authorizations(self, _now):
            return 0

        def get_last_successful_authorization(self):
            return None

    response = await monitoring_routes.get_payment_system_health(_Repo())
    assert response.status == "healthy"
    assert response.minutes_since_last_auth is None
    assert response.alerts == []


# ---- payment health with warning threshold (overdue 6-10) ----
@pytest.mark.asyncio
async def test_payment_health_warning_threshold() -> None:
    now = datetime.now(timezone.utc)

    class _Repo:
        def get_payment_status_counts(self, _now):
            return []

        def get_recent_event_counts(self, _since):
            return []

        def count_overdue_authorizations(self, _now):
            return 6

        def get_last_successful_authorization(self):
            return SimpleNamespace(created_at=now - timedelta(minutes=10))

    response = await monitoring_routes.get_payment_system_health(_Repo())
    assert response.status == "warning"
    assert any("overdue" in a for a in response.alerts)


# ---- payment health with long time since auth ----
@pytest.mark.asyncio
async def test_payment_health_no_recent_auth_warning() -> None:
    now = datetime.now(timezone.utc)

    class _Repo:
        def get_payment_status_counts(self, _now):
            return []

        def get_recent_event_counts(self, _since):
            return []

        def count_overdue_authorizations(self, _now):
            return 0

        def get_last_successful_authorization(self):
            return SimpleNamespace(created_at=now - timedelta(minutes=150))

    response = await monitoring_routes.get_payment_system_health(_Repo())
    assert response.status == "warning"
    assert any("authorizations" in a.lower() for a in response.alerts)
