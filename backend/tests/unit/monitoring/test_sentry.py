# backend/tests/unit/monitoring/test_sentry.py
from __future__ import annotations

from contextlib import contextmanager
import logging
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

    with patch("app.monitoring.sentry.sentry_sdk.init") as mock_init, patch.object(
        sentry_module, "FastApiIntegration"
    ) as mock_integration, patch.object(
        sentry_module, "LoggingIntegration"
    ) as mock_logging_integration, patch.object(
        sentry_module, "CeleryIntegration"
    ) as mock_celery_integration:
        mock_instance = object()
        mock_logging_instance = object()
        mock_celery_instance = object()
        mock_integration.return_value = mock_instance
        mock_logging_integration.return_value = mock_logging_instance
        mock_celery_integration.return_value = mock_celery_instance
        enabled = sentry_module.init_sentry()

    assert enabled is True
    mock_init.assert_called_once()
    kwargs = mock_init.call_args.kwargs
    assert kwargs["dsn"] == "https://example@o0.ingest.sentry.io/0"
    assert kwargs["environment"] == "production"
    assert kwargs["release"] == "gitsha"
    assert kwargs["send_default_pii"] is True
    assert kwargs["traces_sample_rate"] == 0.0
    assert kwargs["traces_sampler"] is None
    assert kwargs["profiles_sample_rate"] == sentry_module.DEFAULT_PROFILES_SAMPLE_RATE
    assert kwargs["enable_logs"] is True
    assert kwargs["integrations"] == [mock_logging_instance, mock_instance, mock_celery_instance]
    mock_integration.assert_called_once_with(
        transaction_style="endpoint",
        failed_request_status_codes=sentry_module.FAILED_REQUEST_STATUS_CODES,
    )
    mock_logging_integration.assert_called_once_with(
        level=logging.INFO,
        event_level=logging.ERROR,
    )


def test_init_sentry_disabled_without_dsn(monkeypatch):
    monkeypatch.delenv("SENTRY_DSN", raising=False)

    with patch("app.monitoring.sentry.sentry_sdk.init") as mock_init:
        enabled = sentry_module.init_sentry()

    assert enabled is False
    mock_init.assert_not_called()


def test_resolve_release_uses_git_sha_fallback(monkeypatch):
    monkeypatch.delenv("GIT_SHA", raising=False)
    monkeypatch.delenv("RENDER_GIT_COMMIT", raising=False)

    with patch("app.monitoring.sentry.subprocess.check_output") as mock_output:
        mock_output.return_value = "abc123\n"
        assert sentry_module._resolve_release() == "abc123"


def test_apply_scope_context_attaches_request_and_user():
    request = _make_request()
    request.state.request_id = "req-123"
    request.state.current_user = SimpleNamespace(id="user-1", email="user@example.com")

    scope = DummyScope()
    with patch.object(sentry_module, "_extract_otel_trace_id", return_value="trace-abc"):
        sentry_module._apply_scope_context(scope, request)

    assert scope.tags["request_id"] == "req-123"
    assert scope.tags["otel_trace_id"] == "trace-abc"
    assert scope.user == {"id": "user-1", "email": "user@example.com"}


def test_apply_event_context_attaches_request_and_user():
    request = _make_request(headers=[(b"x-request-id", b"req-456")])
    request.state.user_id = "user-2"
    request.state.user_email = "user2@example.com"

    event: dict[str, object] = {}
    with patch.object(sentry_module, "_extract_otel_trace_id", return_value="trace-xyz"):
        sentry_module._apply_event_context(event, request)

    assert event["tags"]["request_id"] == "req-456"
    assert event["tags"]["otel_trace_id"] == "trace-xyz"
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


def test_resolve_environment_fallbacks(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "staging")
    monkeypatch.delenv("ENV", raising=False)
    monkeypatch.delenv("SENTRY_ENVIRONMENT", raising=False)
    assert sentry_module._resolve_environment() == "staging"

    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.setenv("SENTRY_ENVIRONMENT", "sentry")
    assert sentry_module._resolve_environment() == "sentry"

    monkeypatch.delenv("SENTRY_ENVIRONMENT", raising=False)
    from app.core import config as cfg

    monkeypatch.setattr(cfg.settings, "environment", "qa", raising=False)
    assert sentry_module._resolve_environment() == "qa"


def test_resolve_git_sha_handles_failure():
    with patch("app.monitoring.sentry.subprocess.check_output", side_effect=OSError):
        assert sentry_module._resolve_git_sha() is None


def test_sampling_path_helpers_and_otel_extract(monkeypatch):
    request = _make_request(path="/api/v1/metrics")
    assert sentry_module._extract_sampling_path({"request": request}) == "/api/v1/metrics"
    assert sentry_module._is_healthcheck_path(None) is False
    assert sentry_module._is_healthcheck_path("/api/v1/ready/") is True

    with patch("app.monitoring.otel.is_otel_enabled", return_value=False):
        assert sentry_module._extract_otel_trace_id() is None

    original_sdk = sentry_module.sentry_sdk
    try:
        sentry_module.sentry_sdk = None
        assert sentry_module.is_sentry_configured() is False
    finally:
        sentry_module.sentry_sdk = original_sdk


@pytest.mark.asyncio
async def test_sentry_context_middleware_noop_when_disabled(monkeypatch):
    called = {"app": False}

    async def app(scope, receive, send):
        called["app"] = True

    middleware = sentry_module.SentryContextMiddleware(app)
    monkeypatch.setattr(sentry_module, "is_sentry_configured", lambda: False)

    scope = {"type": "http", "method": "GET", "path": "/api/v1/health", "headers": []}
    await middleware(scope, lambda: None, lambda: None)
    assert called["app"] is True


@pytest.mark.asyncio
async def test_sentry_context_middleware_applies_context(monkeypatch):
    called = {"app": False, "scope": False, "processor": False}

    async def app(scope, receive, send):
        called["app"] = True

    class DummyScopeWithProcessor(DummyScope):
        def __init__(self) -> None:
            super().__init__()
            self.processor = None

        def add_event_processor(self, processor):
            self.processor = processor

    dummy_scope = DummyScopeWithProcessor()

    @contextmanager
    def configure_scope():
        yield dummy_scope

    dummy_sdk = SimpleNamespace(configure_scope=configure_scope)

    monkeypatch.setattr(sentry_module, "sentry_sdk", dummy_sdk)
    monkeypatch.setattr(sentry_module, "is_sentry_configured", lambda: True)

    def fake_apply_scope(scope_obj, request):
        called["scope"] = True

    def fake_apply_event(event, request):
        called["processor"] = True
        return event

    monkeypatch.setattr(sentry_module, "_apply_scope_context", fake_apply_scope)
    monkeypatch.setattr(sentry_module, "_apply_event_context", fake_apply_event)

    middleware = sentry_module.SentryContextMiddleware(app)
    scope = {"type": "http", "method": "GET", "path": "/api/v1/bookings", "headers": []}
    await middleware(scope, lambda: None, lambda: None)

    assert called["app"] is True
    assert called["scope"] is True
    assert dummy_scope.processor is not None

    dummy_scope.processor({}, {})
    assert called["processor"] is True
