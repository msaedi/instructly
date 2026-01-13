from unittest.mock import AsyncMock

import pytest

from app.core.config import settings
from app.middleware.rate_limiter_asgi import RateLimitMiddlewareASGI


def _make_scope(path="/", method="GET", headers=None, client=("127.0.0.1", 123)):
    raw_headers = []
    for key, value in (headers or {}).items():
        raw_headers.append((key.encode(), value.encode()))
    return {
        "type": "http",
        "path": path,
        "method": method,
        "headers": raw_headers,
        "client": client,
        "scheme": "http",
        "server": ("testserver", 80),
    }


async def _receive():
    return {"type": "http.request", "body": b""}


def _headers_as_dict(message):
    headers = {}
    for key, value in message.get("headers", []):
        headers[key.decode().lower()] = value.decode()
    return headers


async def _simple_app(scope, receive, send):
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-type", b"application/json")],
        }
    )
    await send({"type": "http.response.body", "body": b"{}"})


def test_extract_client_ip_prefers_forwarded():
    scope = _make_scope(headers={"x-forwarded-for": "10.0.0.1, 10.0.0.2"})
    middleware = RateLimitMiddlewareASGI(app=_simple_app)

    assert middleware._extract_client_ip(scope) == "10.0.0.1"


def test_extract_client_ip_falls_back_to_client():
    scope = _make_scope(headers={})
    middleware = RateLimitMiddlewareASGI(app=_simple_app)

    assert middleware._extract_client_ip(scope) == "127.0.0.1"


def test_extract_client_ip_unknown_when_missing_client():
    scope = _make_scope(headers={})
    scope["client"] = None
    middleware = RateLimitMiddlewareASGI(app=_simple_app)

    assert middleware._extract_client_ip(scope) == "unknown"


def test_has_bypass_token_matches():
    scope = _make_scope(headers={"x-rate-limit-bypass": "secret"})
    middleware = RateLimitMiddlewareASGI(app=_simple_app)
    middleware._bypass_token = "secret"

    assert middleware._has_bypass_token(scope) is True


@pytest.mark.asyncio
async def test_non_http_scope_passthrough():
    app = AsyncMock()
    middleware = RateLimitMiddlewareASGI(app=app)
    scope = {"type": "websocket"}

    await middleware(scope, _receive, AsyncMock())

    app.assert_awaited_once()


@pytest.mark.asyncio
async def test_bypass_token_skips_limiter(monkeypatch):
    monkeypatch.setattr(settings, "is_testing", False, raising=False)
    monkeypatch.setattr(settings, "rate_limit_enabled", True, raising=False)

    app = AsyncMock()
    limiter = AsyncMock()
    middleware = RateLimitMiddlewareASGI(app=app, rate_limiter=limiter)
    middleware._bypass_token = "secret"

    await middleware(_make_scope(headers={"x-rate-limit-bypass": "secret"}), _receive, AsyncMock())

    app.assert_awaited_once()
    limiter.check_rate_limit.assert_not_called()


@pytest.mark.asyncio
async def test_testing_env_adds_rate_limit_headers(monkeypatch):
    monkeypatch.setattr(settings, "is_testing", True, raising=False)

    messages = []

    async def _send(message):
        messages.append(message)

    middleware = RateLimitMiddlewareASGI(app=_simple_app)

    await middleware(_make_scope(path="/api/v1/test"), _receive, _send)

    start_message = next(msg for msg in messages if msg["type"] == "http.response.start")
    headers = _headers_as_dict(start_message)
    assert "x-ratelimit-limit" in headers
    assert "x-ratelimit-remaining" in headers
    assert "x-ratelimit-reset" in headers


@pytest.mark.asyncio
async def test_rate_limit_disabled_skips_limiter(monkeypatch):
    monkeypatch.setattr(settings, "is_testing", False, raising=False)
    monkeypatch.setattr(settings, "rate_limit_enabled", False, raising=False)

    app = AsyncMock()
    limiter = AsyncMock()
    middleware = RateLimitMiddlewareASGI(app=app, rate_limiter=limiter)

    await middleware(_make_scope(path="/api/v1/test"), _receive, AsyncMock())

    app.assert_awaited_once()
    limiter.check_rate_limit.assert_not_called()


@pytest.mark.asyncio
async def test_health_check_skipped(monkeypatch):
    monkeypatch.setattr(settings, "is_testing", False, raising=False)
    monkeypatch.setattr(settings, "rate_limit_enabled", True, raising=False)

    app = AsyncMock()
    limiter = AsyncMock()
    middleware = RateLimitMiddlewareASGI(app=app, rate_limiter=limiter)

    await middleware(_make_scope(path="/api/v1/health"), _receive, AsyncMock())

    app.assert_awaited_once()
    limiter.check_rate_limit.assert_not_called()


@pytest.mark.asyncio
async def test_options_skipped(monkeypatch):
    monkeypatch.setattr(settings, "is_testing", False, raising=False)
    monkeypatch.setattr(settings, "rate_limit_enabled", True, raising=False)

    app = AsyncMock()
    limiter = AsyncMock()
    middleware = RateLimitMiddlewareASGI(app=app, rate_limiter=limiter)

    await middleware(_make_scope(path="/api/v1/test", method="OPTIONS"), _receive, AsyncMock())

    app.assert_awaited_once()
    limiter.check_rate_limit.assert_not_called()


@pytest.mark.asyncio
async def test_invite_rate_limit_blocks(monkeypatch):
    monkeypatch.setattr(settings, "is_testing", False, raising=False)
    monkeypatch.setattr(settings, "rate_limit_enabled", True, raising=False)

    limiter = AsyncMock()
    limiter.check_rate_limit.return_value = (False, 1, 120)

    messages = []

    async def _send(message):
        messages.append(message)

    middleware = RateLimitMiddlewareASGI(app=_simple_app, rate_limiter=limiter)

    await middleware(
        _make_scope(path="/api/instructors/abc/bgc/invite", method="POST"),
        _receive,
        _send,
    )

    start_message = next(msg for msg in messages if msg["type"] == "http.response.start")
    assert start_message["status"] == 429


@pytest.mark.asyncio
async def test_invite_rate_limit_allows_falls_through(monkeypatch):
    monkeypatch.setattr(settings, "is_testing", False, raising=False)
    monkeypatch.setattr(settings, "rate_limit_enabled", True, raising=False)

    limiter = AsyncMock()
    limiter.check_rate_limit.side_effect = [(True, 0, 0), (True, 1, 0)]
    limiter.get_remaining_requests.return_value = 9

    messages = []

    async def _send(message):
        messages.append(message)

    middleware = RateLimitMiddlewareASGI(app=_simple_app, rate_limiter=limiter)

    await middleware(
        _make_scope(path="/api/instructors/abc/bgc/invite", method="POST"),
        _receive,
        _send,
    )

    assert limiter.check_rate_limit.call_count == 2
    start_message = next(msg for msg in messages if msg["type"] == "http.response.start")
    assert start_message["status"] == 200


@pytest.mark.asyncio
async def test_local_exemptions_skip(monkeypatch):
    monkeypatch.setattr(settings, "is_testing", False, raising=False)
    monkeypatch.setattr(settings, "rate_limit_enabled", True, raising=False)
    monkeypatch.setenv("SITE_MODE", "local")

    app = AsyncMock()
    limiter = AsyncMock()
    middleware = RateLimitMiddlewareASGI(app=app, rate_limiter=limiter)

    await middleware(
        _make_scope(path="/api/v1/services/abc", method="GET"),
        _receive,
        AsyncMock(),
    )

    app.assert_awaited_once()
    limiter.check_rate_limit.assert_not_called()


@pytest.mark.asyncio
async def test_metrics_rate_limit_blocks(monkeypatch):
    monkeypatch.setattr(settings, "is_testing", False, raising=False)
    monkeypatch.setattr(settings, "rate_limit_enabled", True, raising=False)
    monkeypatch.setattr(settings, "metrics_rate_limit_per_min", 1, raising=False)

    limiter = AsyncMock()
    limiter.check_rate_limit.return_value = (False, 0, 30)

    messages = []

    async def _send(message):
        messages.append(message)

    middleware = RateLimitMiddlewareASGI(app=_simple_app, rate_limiter=limiter)

    await middleware(
        _make_scope(path="/api/v1/internal/metrics", method="GET"),
        _receive,
        _send,
    )

    start_message = next(msg for msg in messages if msg["type"] == "http.response.start")
    assert start_message["status"] == 429


@pytest.mark.asyncio
async def test_metrics_rate_limit_disabled_skips(monkeypatch):
    monkeypatch.setattr(settings, "is_testing", False, raising=False)
    monkeypatch.setattr(settings, "rate_limit_enabled", True, raising=False)
    monkeypatch.setattr(settings, "metrics_rate_limit_per_min", 0, raising=False)

    limiter = AsyncMock()
    limiter.check_rate_limit.return_value = (True, 1, 0)
    limiter.get_remaining_requests.return_value = 9

    messages = []

    async def _send(message):
        messages.append(message)

    middleware = RateLimitMiddlewareASGI(app=_simple_app, rate_limiter=limiter)

    await middleware(
        _make_scope(path="/api/v1/internal/metrics", method="GET"),
        _receive,
        _send,
    )

    assert limiter.check_rate_limit.call_count == 1


@pytest.mark.asyncio
async def test_general_rate_limit_blocked_adds_cors_headers(monkeypatch):
    monkeypatch.setattr(settings, "is_testing", False, raising=False)
    monkeypatch.setattr(settings, "rate_limit_enabled", True, raising=False)
    monkeypatch.setenv("SITE_MODE", "prod")

    limiter = AsyncMock()
    limiter.check_rate_limit.return_value = (False, 5, 15)

    messages = []

    async def _send(message):
        messages.append(message)

    middleware = RateLimitMiddlewareASGI(app=_simple_app, rate_limiter=limiter)

    await middleware(
        _make_scope(
            path="/api/v1/private",
            method="GET",
            headers={"origin": "http://localhost:3000"},
        ),
        _receive,
        _send,
    )

    start_message = next(msg for msg in messages if msg["type"] == "http.response.start")
    headers = _headers_as_dict(start_message)
    assert start_message["status"] == 429
    assert headers.get("access-control-allow-origin") == "http://localhost:3000"
    assert headers.get("x-ratelimit-remaining") == "0"


@pytest.mark.asyncio
async def test_general_rate_limit_allows_adds_headers(monkeypatch):
    monkeypatch.setattr(settings, "is_testing", False, raising=False)
    monkeypatch.setattr(settings, "rate_limit_enabled", True, raising=False)

    limiter = AsyncMock()
    limiter.check_rate_limit.return_value = (True, 1, 0)
    limiter.get_remaining_requests.return_value = 7

    messages = []

    async def _send(message):
        messages.append(message)

    middleware = RateLimitMiddlewareASGI(app=_simple_app, rate_limiter=limiter)

    await middleware(_make_scope(path="/api/v1/ok"), _receive, _send)

    start_message = next(msg for msg in messages if msg["type"] == "http.response.start")
    headers = _headers_as_dict(start_message)
    assert headers.get("x-ratelimit-remaining") == "7"
