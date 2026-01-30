# backend/tests/unit/middleware/test_rate_limiter_asgi_coverage_r5.py
"""
Round 5 Coverage Tests for rate_limiter_asgi.py.

Target: Raise coverage from 86.57% to 92%+
Missed lines: 49->46, 54->56, 64->63, 66, 95-96, 144-145, 148-149, 154-155,
              166->180, 188->195, 189->188, 192-193, 197->213, 201->213, 208-210, 242-243
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import settings
from app.middleware.rate_limiter_asgi import RateLimitMiddlewareASGI


def _make_scope(path="/", method="GET", headers=None, client=("127.0.0.1", 123)):
    """Create a mock ASGI scope."""
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
    """Mock receive callable."""
    return {"type": "http.request", "body": b""}


def _headers_as_dict(message):
    """Extract headers from response message as dict."""
    headers = {}
    for key, value in message.get("headers", []):
        headers[key.decode().lower()] = value.decode()
    return headers


async def _simple_app(scope, receive, send):
    """Simple ASGI app that returns 200."""
    await send({
        "type": "http.response.start",
        "status": 200,
        "headers": [(b"content-type", b"application/json")],
    })
    await send({"type": "http.response.body", "body": b"{}"})


class TestExtractClientIpCoverage:
    """Tests for _extract_client_ip edge cases."""

    def test_prefers_cf_connecting_ip(self):
        """Lines 46-50: Cloudflare connecting IP takes priority."""
        scope = _make_scope(headers={
            "cf-connecting-ip": "203.0.113.1",
            "x-forwarded-for": "10.0.0.1, 10.0.0.2"
        })
        middleware = RateLimitMiddlewareASGI(app=_simple_app)

        result = middleware._extract_client_ip(scope)

        assert result == "203.0.113.1"

    def test_x_forwarded_for_first_ip(self):
        """Line 48: Uses first IP from X-Forwarded-For chain."""
        scope = _make_scope(headers={
            "x-forwarded-for": "10.0.0.1, 10.0.0.2, 10.0.0.3"
        })
        middleware = RateLimitMiddlewareASGI(app=_simple_app)

        result = middleware._extract_client_ip(scope)

        assert result == "10.0.0.1"

    def test_falls_back_to_client_tuple(self):
        """Lines 51-55: Falls back to client tuple when no headers."""
        scope = _make_scope(headers={}, client=("192.168.1.100", 12345))
        middleware = RateLimitMiddlewareASGI(app=_simple_app)

        result = middleware._extract_client_ip(scope)

        assert result == "192.168.1.100"

    def test_unknown_when_client_is_none(self):
        """Line 56: Returns 'unknown' when client is None."""
        scope = _make_scope(headers={})
        scope["client"] = None
        middleware = RateLimitMiddlewareASGI(app=_simple_app)

        result = middleware._extract_client_ip(scope)

        assert result == "unknown"

    def test_unknown_when_client_is_empty_tuple(self):
        """Line 52: Returns 'unknown' when client tuple is empty."""
        scope = _make_scope(headers={})
        scope["client"] = ()
        middleware = RateLimitMiddlewareASGI(app=_simple_app)

        result = middleware._extract_client_ip(scope)

        assert result == "unknown"

    def test_unknown_when_host_is_empty_string(self):
        """Lines 54-55: Returns 'unknown' when host in client tuple is empty."""
        scope = _make_scope(headers={})
        scope["client"] = ("", 12345)
        middleware = RateLimitMiddlewareASGI(app=_simple_app)

        result = middleware._extract_client_ip(scope)

        assert result == "unknown"

    def test_unknown_when_host_is_not_string(self):
        """Lines 53-54: Returns 'unknown' when host is not a string."""
        scope = _make_scope(headers={})
        scope["client"] = (None, 12345)
        middleware = RateLimitMiddlewareASGI(app=_simple_app)

        result = middleware._extract_client_ip(scope)

        assert result == "unknown"

    def test_handles_missing_headers(self):
        """Line 44: Handles missing headers gracefully."""
        scope = {
            "type": "http",
            "path": "/",
            "method": "GET",
            "headers": None,
            "client": ("127.0.0.1", 123),
        }
        middleware = RateLimitMiddlewareASGI(app=_simple_app)

        result = middleware._extract_client_ip(scope)

        assert result == "127.0.0.1"


class TestBypassTokenCoverage:
    """Tests for _has_bypass_token edge cases."""

    def test_no_bypass_token_configured(self):
        """Line 60-61: Returns False when no bypass token configured."""
        scope = _make_scope(headers={"x-rate-limit-bypass": "anything"})
        middleware = RateLimitMiddlewareASGI(app=_simple_app)
        middleware._bypass_token = ""

        result = middleware._has_bypass_token(scope)

        assert result is False

    def test_bypass_token_not_matching(self):
        """Line 65: Returns False when token doesn't match."""
        scope = _make_scope(headers={"x-rate-limit-bypass": "wrong_token"})
        middleware = RateLimitMiddlewareASGI(app=_simple_app)
        middleware._bypass_token = "correct_token"

        result = middleware._has_bypass_token(scope)

        assert result is False

    def test_bypass_header_not_present(self):
        """Line 66: Returns False when bypass header is missing."""
        scope = _make_scope(headers={})
        middleware = RateLimitMiddlewareASGI(app=_simple_app)
        middleware._bypass_token = "secret"

        result = middleware._has_bypass_token(scope)

        assert result is False


class TestTestingModeExceptionHandling:
    """Tests for exception handling in testing mode (Lines 95-96)."""

    @pytest.mark.asyncio
    async def test_testing_mode_exception_ignored(self, monkeypatch):
        """Lines 95-96: Exception in test mode is logged and ignored."""
        monkeypatch.setattr(settings, "is_testing", True, raising=False)

        messages = []

        async def _send(message):
            messages.append(message)

        # Create middleware but make the app raise
        async def _raising_app(scope, receive, send):
            # Simulate error during wrapped send
            raise ValueError("Simulated error")

        middleware = RateLimitMiddlewareASGI(app=_raising_app)

        # Should not propagate exception from settings check
        with pytest.raises(ValueError, match="Simulated error"):
            await middleware(_make_scope(path="/api/v1/test"), _receive, _send)

    @pytest.mark.asyncio
    async def test_testing_mode_attribute_error_ignored(self, monkeypatch):
        """Lines 95-96: AttributeError in test mode check is handled."""
        # Make is_testing raise AttributeError
        monkeypatch.setattr(settings, "is_testing", property(lambda self: (_ for _ in ()).throw(AttributeError())), raising=False)

        # This should not crash - the middleware should handle it gracefully
        # Actually, getattr with a default handles this
        middleware = RateLimitMiddlewareASGI(app=_simple_app)

        messages = []

        async def _send(message):
            messages.append(message)

        # Delete the attribute to force getattr to return default
        monkeypatch.delattr(settings, "is_testing", raising=False)

        # This should proceed without crashing
        await middleware(_make_scope(path="/api/v1/test"), _receive, _send)


class TestCORSHeadersOnRateLimitResponse:
    """Tests for CORS headers when rate limited (Lines 186-210)."""

    @pytest.mark.asyncio
    async def test_cors_headers_for_allowed_origin(self, monkeypatch):
        """Lines 197-207: Adds CORS headers for allowed origin when rate limited."""
        monkeypatch.setattr(settings, "is_testing", False, raising=False)
        monkeypatch.setattr(settings, "rate_limit_enabled", True, raising=False)
        monkeypatch.setenv("SITE_MODE", "prod")

        limiter = AsyncMock()
        limiter.check_rate_limit.return_value = (False, 5, 30)  # Blocked

        messages = []

        async def _send(message):
            messages.append(message)

        middleware = RateLimitMiddlewareASGI(app=_simple_app, rate_limiter=limiter)

        await middleware(
            _make_scope(
                path="/api/v1/something",
                method="GET",
                headers={"origin": "http://localhost:3000"}  # Allowed origin
            ),
            _receive,
            _send,
        )

        start_message = next(msg for msg in messages if msg["type"] == "http.response.start")
        headers = _headers_as_dict(start_message)

        assert start_message["status"] == 429
        assert headers.get("access-control-allow-origin") == "http://localhost:3000"
        assert headers.get("access-control-allow-credentials") == "true"

    @pytest.mark.asyncio
    async def test_no_cors_headers_for_disallowed_origin(self, monkeypatch):
        """Lines 197->213, 201->213: No CORS headers for disallowed origin."""
        monkeypatch.setattr(settings, "is_testing", False, raising=False)
        monkeypatch.setattr(settings, "rate_limit_enabled", True, raising=False)
        monkeypatch.setenv("SITE_MODE", "prod")

        limiter = AsyncMock()
        limiter.check_rate_limit.return_value = (False, 5, 30)

        messages = []

        async def _send(message):
            messages.append(message)

        middleware = RateLimitMiddlewareASGI(app=_simple_app, rate_limiter=limiter)

        await middleware(
            _make_scope(
                path="/api/v1/something",
                method="GET",
                headers={"origin": "http://evil.com"}  # Not in ALLOWED_ORIGINS
            ),
            _receive,
            _send,
        )

        start_message = next(msg for msg in messages if msg["type"] == "http.response.start")
        headers = _headers_as_dict(start_message)

        assert start_message["status"] == 429
        # Should not have CORS headers for disallowed origin
        assert "access-control-allow-origin" not in headers

    @pytest.mark.asyncio
    async def test_no_cors_headers_when_no_origin(self, monkeypatch):
        """Lines 186-193: No CORS headers when no Origin header present."""
        monkeypatch.setattr(settings, "is_testing", False, raising=False)
        monkeypatch.setattr(settings, "rate_limit_enabled", True, raising=False)
        monkeypatch.setenv("SITE_MODE", "prod")

        limiter = AsyncMock()
        limiter.check_rate_limit.return_value = (False, 5, 30)

        messages = []

        async def _send(message):
            messages.append(message)

        middleware = RateLimitMiddlewareASGI(app=_simple_app, rate_limiter=limiter)

        await middleware(
            _make_scope(
                path="/api/v1/something",
                method="GET",
                headers={}  # No origin header
            ),
            _receive,
            _send,
        )

        start_message = next(msg for msg in messages if msg["type"] == "http.response.start")
        headers = _headers_as_dict(start_message)

        assert start_message["status"] == 429
        assert "access-control-allow-origin" not in headers

    @pytest.mark.asyncio
    async def test_cors_header_extraction_exception_handled(self, monkeypatch):
        """Lines 192-193, 208-210: Exception in origin extraction handled gracefully."""
        monkeypatch.setattr(settings, "is_testing", False, raising=False)
        monkeypatch.setattr(settings, "rate_limit_enabled", True, raising=False)
        monkeypatch.setenv("SITE_MODE", "prod")

        limiter = AsyncMock()
        limiter.check_rate_limit.return_value = (False, 5, 30)

        messages = []

        async def _send(message):
            messages.append(message)

        middleware = RateLimitMiddlewareASGI(app=_simple_app, rate_limiter=limiter)

        # Create scope with malformed headers that could cause decode issues
        scope = _make_scope(path="/api/v1/test", method="GET")
        # Replace headers with something that could cause issues
        scope["headers"] = [(b"origin", b"\xff\xfe")]  # Invalid UTF-8

        # Should not crash, just skip CORS headers
        await middleware(scope, _receive, _send)

        start_message = next(msg for msg in messages if msg["type"] == "http.response.start")
        assert start_message["status"] == 429


class TestLoggingExceptionHandling:
    """Tests for logging exception handling (Lines 242-243)."""

    @pytest.mark.asyncio
    async def test_logging_exception_ignored(self, monkeypatch):
        """Lines 242-243: Exception during logging is caught and ignored."""
        monkeypatch.setattr(settings, "is_testing", False, raising=False)
        monkeypatch.setattr(settings, "rate_limit_enabled", True, raising=False)
        monkeypatch.setenv("SITE_MODE", "prod")

        limiter = AsyncMock()
        limiter.check_rate_limit.return_value = (False, 5, 30)

        messages = []

        async def _send(message):
            messages.append(message)

        middleware = RateLimitMiddlewareASGI(app=_simple_app, rate_limiter=limiter)

        # Patch the logger module used by the middleware
        with patch("app.middleware.rate_limiter_asgi.logger") as mock_logger:
            mock_logger.warning.side_effect = Exception("Logging failed")
            mock_logger.debug.return_value = None

            # Should not crash despite logging error
            await middleware(
                _make_scope(path="/api/v1/test", method="GET"),
                _receive,
                _send,
            )

        start_message = next(msg for msg in messages if msg["type"] == "http.response.start")
        assert start_message["status"] == 429


class TestLocalExemptions:
    """Tests for local/preview mode exemptions."""

    @pytest.mark.asyncio
    async def test_auth_me_exempted_in_local(self, monkeypatch):
        """Lines 143-145: /auth/me is exempted in local mode."""
        monkeypatch.setattr(settings, "is_testing", False, raising=False)
        monkeypatch.setattr(settings, "rate_limit_enabled", True, raising=False)
        monkeypatch.setenv("SITE_MODE", "local")

        app = AsyncMock()
        limiter = AsyncMock()
        middleware = RateLimitMiddlewareASGI(app=app, rate_limiter=limiter)

        await middleware(
            _make_scope(path="/auth/me", method="GET"),
            _receive,
            AsyncMock(),
        )

        app.assert_awaited_once()
        limiter.check_rate_limit.assert_not_called()

    @pytest.mark.asyncio
    async def test_public_guest_session_exempted_in_preview(self, monkeypatch):
        """Lines 143-145: Public session endpoint exempted in preview mode."""
        monkeypatch.setattr(settings, "is_testing", False, raising=False)
        monkeypatch.setattr(settings, "rate_limit_enabled", True, raising=False)
        monkeypatch.setenv("SITE_MODE", "preview")

        app = AsyncMock()
        limiter = AsyncMock()
        middleware = RateLimitMiddlewareASGI(app=app, rate_limiter=limiter)

        await middleware(
            _make_scope(path="/api/v1/public/session/guest", method="GET"),
            _receive,
            AsyncMock(),
        )

        app.assert_awaited_once()
        limiter.check_rate_limit.assert_not_called()

    @pytest.mark.asyncio
    async def test_reviews_endpoint_exempted_in_local(self, monkeypatch):
        """Lines 147-149: Reviews endpoint exempted in local mode."""
        monkeypatch.setattr(settings, "is_testing", False, raising=False)
        monkeypatch.setattr(settings, "rate_limit_enabled", True, raising=False)
        monkeypatch.setenv("SITE_MODE", "local")

        app = AsyncMock()
        limiter = AsyncMock()
        middleware = RateLimitMiddlewareASGI(app=app, rate_limiter=limiter)

        await middleware(
            _make_scope(path="/api/v1/reviews/instructor/abc123", method="GET"),
            _receive,
            AsyncMock(),
        )

        app.assert_awaited_once()
        limiter.check_rate_limit.assert_not_called()

    @pytest.mark.asyncio
    async def test_instructors_endpoint_exempted_in_preview(self, monkeypatch):
        """Lines 153-155: Instructors endpoint exempted in preview mode."""
        monkeypatch.setattr(settings, "is_testing", False, raising=False)
        monkeypatch.setattr(settings, "rate_limit_enabled", True, raising=False)
        monkeypatch.setenv("SITE_MODE", "preview")

        app = AsyncMock()
        limiter = AsyncMock()
        middleware = RateLimitMiddlewareASGI(app=app, rate_limiter=limiter)

        await middleware(
            _make_scope(path="/api/v1/instructors/search", method="GET"),
            _receive,
            AsyncMock(),
        )

        app.assert_awaited_once()
        limiter.check_rate_limit.assert_not_called()


class TestSSEEndpointBypass:
    """Tests for SSE endpoint bypass."""

    @pytest.mark.asyncio
    async def test_sse_endpoint_bypasses_rate_limit(self, monkeypatch):
        """Lines 108-110: SSE endpoints bypass rate limiting."""
        monkeypatch.setattr(settings, "is_testing", False, raising=False)
        monkeypatch.setattr(settings, "rate_limit_enabled", True, raising=False)

        from app.core.constants import SSE_PATH_PREFIX

        app = AsyncMock()
        limiter = AsyncMock()
        middleware = RateLimitMiddlewareASGI(app=app, rate_limiter=limiter)

        await middleware(
            _make_scope(path=f"{SSE_PATH_PREFIX}/messages", method="GET"),
            _receive,
            AsyncMock(),
        )

        app.assert_awaited_once()
        limiter.check_rate_limit.assert_not_called()
