from __future__ import annotations

from typing import Callable

from fastapi.testclient import TestClient

from app.core import broadcast as broadcast_module
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
    broadcast_initialized: bool | None = None,
) -> None:
    monkeypatch.setattr(ready_module, "SessionLocal", session_factory)
    monkeypatch.setattr(ready_module, "get_healthcheck_redis_client", redis_factory)
    if broadcast_initialized is not None:
        monkeypatch.setattr(
            broadcast_module, "is_broadcast_initialized", lambda: broadcast_initialized
        )


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
        broadcast_initialized=True,
    )
    resp = client.get("/ready")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "notifications_healthy": True}


def test_ready_probe_messaging_degraded(client: TestClient, monkeypatch) -> None:
    """Test that uninitialized Broadcaster returns degraded status."""
    _patch_dependencies(
        monkeypatch,
        session_factory=lambda: DummySession(),
        redis_factory=lambda: DummyRedis(),
        broadcast_initialized=False,
    )
    resp = client.get("/ready")
    assert resp.status_code == 200  # Still returns 200, just degraded
    assert resp.json() == {"status": "degraded", "notifications_healthy": False}
