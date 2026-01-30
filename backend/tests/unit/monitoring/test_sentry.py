# backend/tests/unit/monitoring/test_sentry.py
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from fastapi import Request
import pytest

pytest.importorskip("sentry_sdk")

from app.monitoring import sentry as sentry_module


class DummyScope:
    def __init__(self) -> None:
        self.tags: dict[str, str] = {}
        self.user: dict[str, str] | None = None

    def set_tag(self, key: str, value: str) -> None:
        self.tags[key] = value

    def set_user(self, user: dict[str, str]) -> None:
        self.user = user


def _make_request(path: str = "/api/v1/bookings", headers: list[tuple[bytes, bytes]] | None = None) -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "headers": headers or [],
    }
    return Request(scope)


def test_init_sentry_enabled_when_dsn_set(monkeypatch):
    monkeypatch.setenv("SENTRY_DSN", "https://example@o0.ingest.sentry.io/0")
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("GIT_SHA", "gitsha")

    with patch("app.monitoring.sentry.sentry_sdk.init") as mock_init:
        enabled = sentry_module.init_sentry()

    assert enabled is True
    mock_init.assert_called_once()
    kwargs = mock_init.call_args.kwargs
    assert kwargs["dsn"] == "https://example@o0.ingest.sentry.io/0"
    assert kwargs["environment"] == "production"
    assert kwargs["release"] == "gitsha"


def test_init_sentry_disabled_without_dsn(monkeypatch):
    monkeypatch.delenv("SENTRY_DSN", raising=False)

    with patch("app.monitoring.sentry.sentry_sdk.init") as mock_init:
        enabled = sentry_module.init_sentry()

    assert enabled is False
    mock_init.assert_not_called()


def test_apply_scope_context_attaches_request_and_user():
    request = _make_request()
    request.state.request_id = "req-123"
    request.state.current_user = SimpleNamespace(id="user-1", email="user@example.com")

    scope = DummyScope()
    sentry_module._apply_scope_context(scope, request)

    assert scope.tags["request_id"] == "req-123"
    assert scope.user == {"id": "user-1", "email": "user@example.com"}


def test_apply_event_context_attaches_request_and_user():
    request = _make_request(headers=[(b"x-request-id", b"req-456")])
    request.state.user_id = "user-2"
    request.state.user_email = "user2@example.com"

    event: dict[str, object] = {}
    sentry_module._apply_event_context(event, request)

    assert event["tags"]["request_id"] == "req-456"
    assert event["user"]["id"] == "user-2"
    assert event["user"]["email"] == "user2@example.com"


def test_traces_sampler_skips_health_checks():
    assert (
        sentry_module._traces_sampler({"asgi_scope": {"path": "/api/v1/health"}}) == 0.0
    )
    assert (
        sentry_module._traces_sampler({"asgi_scope": {"path": "/api/v1/health/lite"}})
        == 0.0
    )
    assert (
        sentry_module._traces_sampler({"asgi_scope": {"path": "/api/v1/ready"}}) == 0.0
    )
    assert (
        sentry_module._traces_sampler({"asgi_scope": {"path": "/api/v1/bookings"}})
        == sentry_module.DEFAULT_TRACES_SAMPLE_RATE
    )
