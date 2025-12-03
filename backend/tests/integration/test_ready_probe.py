from __future__ import annotations

from typing import Callable

from fastapi.testclient import TestClient

from app.routes import ready as ready_module


class DummySession:
    def __init__(self, fail: bool = False):
        self._fail = fail

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, *_):
        if self._fail:
            raise RuntimeError("db down")
        return None


class DummyRedis:
    def __init__(self, fail: bool = False):
        self._fail = fail

    def ping(self):
        if self._fail:
            raise RuntimeError("cache down")


def _patch_dependencies(
    monkeypatch,
    *,
    session_factory: Callable[[], DummySession],
    redis_factory: Callable[[], DummyRedis],
) -> None:
    monkeypatch.setattr(ready_module, "SessionLocal", session_factory)
    monkeypatch.setattr(ready_module, "get_healthcheck_redis_client", redis_factory)


def test_ready_probe_db_failure(client: TestClient, monkeypatch) -> None:
    _patch_dependencies(
        monkeypatch,
        session_factory=lambda: DummySession(fail=True),
        redis_factory=lambda: DummyRedis(fail=False),
    )
    resp = client.get("/ready")
    assert resp.status_code == 503
    assert resp.json() == {"status": "db_not_ready", "notifications_healthy": None}


def test_ready_probe_cache_failure(client: TestClient, monkeypatch) -> None:
    _patch_dependencies(
        monkeypatch,
        session_factory=lambda: DummySession(),
        redis_factory=lambda: DummyRedis(fail=True),
    )
    resp = client.get("/ready")
    assert resp.status_code == 503
    assert resp.json() == {"status": "cache_not_ready", "notifications_healthy": None}


def test_ready_probe_success(client: TestClient, monkeypatch) -> None:
    _patch_dependencies(
        monkeypatch,
        session_factory=lambda: DummySession(),
        redis_factory=lambda: DummyRedis(),
    )
    # Mock notification service as not initialized (raises RuntimeError)
    # This tests the case where DB and Redis are up but notification service isn't started
    def _not_initialized():
        raise RuntimeError("Notification service not initialized")

    monkeypatch.setattr(
        "app.routes.v1.messages.get_notification_service",
        _not_initialized,
    )
    resp = client.get("/ready")
    assert resp.status_code == 200
    # notifications_healthy is None when notification service is not initialized
    assert resp.json() == {"status": "ok", "notifications_healthy": None}


class DummyNotificationService:
    """Mock notification service for testing."""

    def __init__(self, healthy: bool = True):
        self._healthy = healthy

    def is_healthy(self) -> bool:
        return self._healthy

    def get_health_details(self) -> dict:
        return {"healthy": self._healthy, "is_listening": self._healthy}


def test_ready_probe_notifications_degraded(client: TestClient, monkeypatch) -> None:
    """Test that unhealthy notification service returns degraded status."""
    _patch_dependencies(
        monkeypatch,
        session_factory=lambda: DummySession(),
        redis_factory=lambda: DummyRedis(),
    )
    # Patch the notification service getter
    monkeypatch.setattr(
        "app.routes.v1.messages.get_notification_service",
        lambda: DummyNotificationService(healthy=False),
    )
    resp = client.get("/ready")
    assert resp.status_code == 200  # Still returns 200, just degraded
    assert resp.json() == {"status": "degraded", "notifications_healthy": False}


def test_ready_probe_notifications_healthy(client: TestClient, monkeypatch) -> None:
    """Test that healthy notification service returns ok status."""
    _patch_dependencies(
        monkeypatch,
        session_factory=lambda: DummySession(),
        redis_factory=lambda: DummyRedis(),
    )
    # Patch the notification service getter
    monkeypatch.setattr(
        "app.routes.v1.messages.get_notification_service",
        lambda: DummyNotificationService(healthy=True),
    )
    resp = client.get("/ready")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "notifications_healthy": True}
