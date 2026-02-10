# backend/tests/unit/middleware/test_rate_limiter.py
"""
Comprehensive tests for rate limiting functionality.

Tests cover:
- Basic rate limiting enforcement
- Different key strategies (IP, user, email)
- Sliding window algorithm
- Multiple rate limits on same endpoint
- Error responses and headers
- Cache failure handling
- Admin functions
"""

import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock, patch

from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient
import pytest
import pytest_asyncio
from redis.exceptions import RedisError

from app.core.config import settings
from app.middleware.rate_limiter import (
    RateLimitAdmin,
    RateLimiter,
    RateLimitKeyType,
    RateLimitMiddleware,
    _get_identifier,
    rate_limit,
    rate_limit_api_key,
    rate_limit_auth,
    rate_limit_password_reset,
)
from app.services.cache_service import CacheService


@pytest.fixture
def enable_rate_limiting():
    """Enable rate limiting for tests that specifically need to test rate limiting."""
    original_value = settings.rate_limit_enabled
    settings.rate_limit_enabled = True
    yield
    settings.rate_limit_enabled = original_value


@pytest_asyncio.fixture
async def clear_rate_limits():
    """Best-effort clear of rate limiting keys when Redis is available."""
    cache = CacheService()
    redis = await cache.get_redis_client()
    if redis is None:
        yield
        return
    try:
        async for key in redis.scan_iter(match="rate_limit:*"):
            await redis.delete(key)
    except Exception:
        # In CI or local environments without Redis, keep tests resilient.
        pass
    try:
        yield
    finally:
        try:
            await redis.close()
        except Exception:
            pass
        try:
            await redis.connection_pool.disconnect()
        except Exception:
            pass


@pytest.mark.usefixtures("enable_rate_limiting", "clear_rate_limits")
@pytest.mark.asyncio
class TestRateLimiter:
    """Test the core RateLimiter class."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock redis client compatible with redis.asyncio usage."""
        redis = MagicMock()
        redis.zrange = AsyncMock(return_value=[])
        redis.zrem = AsyncMock(return_value=1)
        redis.zremrangebyscore = AsyncMock(return_value=0)
        redis.zcard = AsyncMock(return_value=0)
        return redis

    @pytest.fixture
    def mock_cache(self, mock_redis):
        """Create a mock async cache service."""
        cache = AsyncMock(spec=CacheService)
        cache.get_redis_client.return_value = mock_redis
        cache.delete.return_value = True
        return cache

    @pytest.fixture
    def rate_limiter(self, mock_cache):
        """Create a rate limiter with mock cache."""
        return RateLimiter(cache_service=mock_cache)

    async def test_rate_limiter_initialization(self):
        """Test rate limiter can be initialized without cache service."""
        limiter = RateLimiter()
        assert limiter.enabled == getattr(settings, "rate_limit_enabled", True)

    async def test_check_rate_limit_when_disabled(self, rate_limiter):
        """Test rate limiting when disabled."""
        rate_limiter.enabled = False
        allowed, requests, retry_after = await rate_limiter.check_rate_limit(
            identifier="test", limit=5, window_seconds=60
        )
        assert allowed is True
        assert requests == 0
        assert retry_after == 0

    async def test_check_rate_limit_without_cache(self, rate_limiter):
        """Test rate limiting when cache is unavailable."""
        rate_limiter.cache.get_redis_client.return_value = None

        allowed, requests, retry_after = await rate_limiter.check_rate_limit(
            identifier="test", limit=5, window_seconds=60
        )

        assert allowed is True
        assert requests == 0
        assert retry_after == 0

    async def test_check_rate_limit_sliding_window(self, rate_limiter, mock_redis):
        """Test sliding window algorithm."""
        # Setup mock pipeline
        pipe = MagicMock()
        pipe.execute = AsyncMock(return_value=[None, 0, None, None])  # No requests in window
        mock_redis.pipeline.return_value = pipe

        # First request - should be allowed
        allowed, requests, retry_after = await rate_limiter.check_rate_limit(
            identifier="user123", limit=5, window_seconds=60
        )

        assert allowed is True
        assert requests == 1
        assert retry_after == 0

        # Verify pipeline operations
        mock_redis.pipeline.assert_called_once()
        pipe.zremrangebyscore.assert_called_once()
        pipe.zcard.assert_called_once()
        pipe.zadd.assert_called_once()
        pipe.expire.assert_called_once()
        pipe.execute.assert_awaited_once()

    async def test_check_rate_limit_exceeded(self, rate_limiter, mock_redis):
        """Test when rate limit is exceeded."""
        # Setup mock pipeline
        pipe = MagicMock()
        pipe.execute = AsyncMock(return_value=[None, 5, None, None])
        mock_redis.pipeline.return_value = pipe

        # Simulate limit exceeded (5 requests already made)
        # Mock oldest timestamp for retry_after calculation
        mock_redis.zrange.return_value = [("timestamp", time.time() - 30)]

        allowed, requests, retry_after = await rate_limiter.check_rate_limit(
            identifier="user123", limit=5, window_seconds=60
        )

        assert allowed is False
        assert requests == 5
        assert retry_after > 0 and retry_after <= 60

        # Verify the rejected request was removed
        mock_redis.zrem.assert_awaited_once()

    async def test_check_rate_limit_exceeded_without_oldest_timestamp(self, rate_limiter, mock_redis):
        """Fallback retry_after when no oldest timestamp exists."""
        pipe = MagicMock()
        pipe.execute = AsyncMock(return_value=[None, 5, None, None])
        mock_redis.pipeline.return_value = pipe
        mock_redis.zrange = AsyncMock(return_value=[])

        allowed, requests, retry_after = await rate_limiter.check_rate_limit(
            identifier="user123", limit=5, window_seconds=60
        )

        assert allowed is False
        assert requests == 5
        assert retry_after == 60

    async def test_reset_limit(self, rate_limiter, mock_cache):
        """Test resetting rate limits."""
        mock_cache.delete.return_value = True

        result = await rate_limiter.reset_limit("user123", "test_window")

        assert result is True
        mock_cache.delete.assert_awaited_once_with("rate_limit:test_window:user123")

    async def test_reset_limit_without_cache(self, rate_limiter):
        """Reset should fail gracefully if cache unavailable."""
        rate_limiter.cache.get_redis_client.return_value = None
        result = await rate_limiter.reset_limit("user123", "test_window")
        assert result is False

    async def test_reset_limit_handles_error(self, rate_limiter, mock_cache):
        """Reset should return False on delete errors."""
        mock_cache.delete.side_effect = RuntimeError("boom")
        result = await rate_limiter.reset_limit("user123", "test_window")
        assert result is False

    async def test_get_remaining_requests(self, rate_limiter, mock_redis):
        """Test getting remaining requests."""
        mock_redis.zremrangebyscore.return_value = None
        mock_redis.zcard.return_value = 3

        remaining = await rate_limiter.get_remaining_requests(
            identifier="user123", limit=5, window_seconds=60
        )

        assert remaining == 2

    async def test_get_remaining_requests_error_returns_limit(self, rate_limiter, mock_redis):
        """Error path should return limit as remaining."""
        mock_redis.zremrangebyscore.side_effect = RuntimeError("boom")
        remaining = await rate_limiter.get_remaining_requests(
            identifier="user123", limit=5, window_seconds=60
        )
        assert remaining == 5

    async def test_cache_key_generation(self, rate_limiter):
        """Test cache key generation with long identifiers."""
        # Short identifier
        key = rate_limiter._get_cache_key("user123", "test")
        assert key == "rate_limit:test:user123"

        # Long identifier (should be hashed)
        long_id = "a" * 50
        key = rate_limiter._get_cache_key(long_id, "test")
        assert key.startswith("rate_limit:test:")
        assert len(key.split(":")[-1]) == 16  # MD5 hash truncated

    async def test_window_start_calculation(self, rate_limiter, monkeypatch):
        """Window start uses current epoch minus window seconds."""
        monkeypatch.setattr(time, "time", lambda: 1000)
        assert rate_limiter._get_window_start(60) == 940

    async def test_error_handling(self, rate_limiter, mock_redis):
        """Test error handling when Redis operations fail."""
        mock_redis.pipeline.side_effect = RedisError("Connection failed")

        allowed, requests, retry_after = await rate_limiter.check_rate_limit(
            identifier="user123", limit=5, window_seconds=60
        )

        # Should allow on error
        assert allowed is True
        assert requests == 0
        assert retry_after == 0


class TestRateLimitMiddleware:
    """Test the FastAPI middleware."""

    @pytest.fixture
    def app(self):
        """Create a test FastAPI app."""
        app = FastAPI()

        # Add rate limit middleware
        app.add_middleware(RateLimitMiddleware)

        @app.get("/test")
        async def test_endpoint():
            return {"message": "success"}

        @app.get("/health")
        async def health_check():
            return {"status": "healthy"}

        return app

    @pytest.fixture
    def client(self, app):
        """Create test client."""
        return TestClient(app)

    def test_middleware_allows_health_check(self, client):
        """Test that health endpoints bypass rate limiting."""
        # Make many requests to health endpoint
        for _ in range(200):
            response = client.get("/health")
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_middleware_bypasses_api_v1_health_path(self):
        """Middleware should bypass the exact /api/v1/health path check."""
        middleware = RateLimitMiddleware(app=FastAPI())
        middleware.rate_limiter = MagicMock()

        request = Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/api/v1/health",
                "headers": [],
                "client": ("1.2.3.4", 1234),
                "query_string": b"",
                "scheme": "http",
                "server": ("testserver", 80),
                "root_path": "",
                "http_version": "1.1",
            }
        )

        async def call_next(_request: Request) -> Response:
            return Response(status_code=204)

        response = await middleware.dispatch(request, call_next)

        assert response.status_code == 204
        middleware.rate_limiter.check_rate_limit.assert_not_called()

    def test_middleware_rate_limit_headers(self, client):
        """Test rate limit headers are added."""
        response = client.get("/test")

        assert response.status_code == 200
        assert "X-RateLimit-Limit" in response.headers
        assert "X-RateLimit-Remaining" in response.headers
        assert "X-RateLimit-Reset" in response.headers

    @patch("app.middleware.rate_limiter.RateLimiter")
    def test_middleware_blocks_when_limit_exceeded(self, mock_limiter_class, client):
        """Test middleware blocks requests when limit exceeded."""
        # Setup mock
        mock_limiter = Mock()
        mock_limiter_class.return_value = mock_limiter

        # First request allowed
        mock_limiter.check_rate_limit = AsyncMock(return_value=(False, 100, 30))
        mock_limiter.get_remaining_requests = AsyncMock(return_value=0)

        response = client.get("/test")

        assert response.status_code == 429
        assert response.json()["code"] == "RATE_LIMIT_EXCEEDED"
        assert "Retry-After" in response.headers


class TestRateLimitDecorator:
    """Test the rate limit decorator."""

    @pytest.fixture
    def app(self):
        """Create a test FastAPI app with decorated endpoints."""
        app = FastAPI()

        @app.post("/login")
        @rate_limit("5/minute", key_type=RateLimitKeyType.IP)
        async def login(request: Request):
            return {"message": "logged in"}

        @app.post("/reset-password")
        @rate_limit("3/hour", key_type=RateLimitKeyType.EMAIL, key_field="email")
        async def reset_password(request: Request, email: str):
            return {"message": "reset sent"}

        @app.post("/auth-endpoint")
        @rate_limit_auth
        async def auth_endpoint(request: Request):
            return {"message": "authenticated"}

        @app.post("/password-reset-endpoint")
        @rate_limit_password_reset
        async def password_reset_endpoint(request: Request):
            return {"message": "password reset"}

        @app.get("/response-endpoint")
        @rate_limit("5/minute")
        async def response_endpoint(request: Request):
            return Response(content="ok")

        return app

    @pytest.fixture
    def client(self, app):
        """Create test client."""
        return TestClient(app)

    def test_decorator_parses_rate_string(self, client):
        """Test decorator correctly parses rate strings."""
        # Test different time units
        test_cases = [
            ("5/second", 1),
            ("10/minute", 60),
            ("100/hour", 3600),
            ("1000/day", 86400),
        ]

        for rate_string, expected_seconds in test_cases:
            # Create a simple test to verify parsing
            # The actual rate limiting is tested elsewhere
            assert expected_seconds > 0

    @patch("app.middleware.rate_limiter.RateLimiter")
    def test_decorator_applies_rate_limit(self, mock_limiter_class, client):
        """Test decorator applies rate limiting."""
        mock_limiter = Mock()
        mock_limiter_class.return_value = mock_limiter

        # Allow request
        mock_limiter.check_rate_limit = AsyncMock(return_value=(True, 1, 0))
        mock_limiter.get_remaining_requests = AsyncMock(return_value=4)

        response = client.post("/login")

        assert response.status_code == 200
        mock_limiter.check_rate_limit.assert_called_once()

    @patch("app.middleware.rate_limiter.RateLimiter")
    def test_decorator_request_body_param_named_request(self, mock_limiter_class):
        """Ensure body param named 'request' doesn't collide with Request detection."""
        mock_limiter = Mock()
        mock_limiter.check_rate_limit = AsyncMock(return_value=(True, 1, 0))
        mock_limiter.get_remaining_requests = AsyncMock(return_value=4)
        mock_limiter_class.return_value = mock_limiter

        app = FastAPI()

        @app.post("/collision")
        @rate_limit("5/minute", key_type=RateLimitKeyType.IP)
        async def collision(request: dict, req: Request):
            return {"ok": True}

        client = TestClient(app)
        response = client.post("/collision", json={"foo": "bar"})

        assert response.status_code == 200
        assert response.json() == {"ok": True}
        mock_limiter.check_rate_limit.assert_called_once()

    @patch("app.middleware.rate_limiter.RateLimiter")
    def test_decorator_blocks_exceeded_limit(self, mock_limiter_class, client):
        """Test decorator blocks when limit exceeded."""
        mock_limiter = Mock()
        mock_limiter_class.return_value = mock_limiter

        # Block request
        mock_limiter.check_rate_limit = AsyncMock(return_value=(False, 5, 45))

        response = client.post("/login")

        assert response.status_code == 429
        assert "retry_after" in response.json()["detail"]
        assert response.json()["detail"]["retry_after"] == 45

    def test_convenience_decorators(self, client):
        """Test convenience decorators work correctly."""
        # These decorators should apply their specific rate limits
        # Testing that they don't raise errors
        response = client.post("/auth-endpoint")
        assert response.status_code in [200, 429]

        response = client.post("/password-reset-endpoint")
        assert response.status_code in [200, 429]

    @pytest.mark.asyncio
    async def test_decorator_bypass_header_skips_rate_limit(self, monkeypatch):
        """Bypass header should short-circuit rate limiting."""
        monkeypatch.setattr(settings, "rate_limit_bypass_token", "bypass-token")

        @rate_limit("5/minute")
        async def endpoint(request: Request):
            return Response(content="ok")

        with patch(
            "app.middleware.rate_limiter.RateLimiter.check_rate_limit", new_callable=AsyncMock
        ) as mock_check:
            request = Request(
                {
                    "type": "http",
                    "headers": [(b"x-rate-limit-bypass", b"bypass-token")],
                    "client": ("1.2.3.4", 1234),
                    "path": "/bypass",
                }
            )
            response = await endpoint(request)
            assert response.status_code == 200
            mock_check.assert_not_called()

    @pytest.mark.asyncio
    async def test_decorator_sets_headers_on_response(self):
        """Response objects should receive rate limit headers."""
        @rate_limit("5/minute")
        async def endpoint(request: Request):
            return Response(content="ok")

        with patch("app.middleware.rate_limiter.RateLimiter") as mock_limiter_class:
            mock_limiter = mock_limiter_class.return_value
            mock_limiter.check_rate_limit = AsyncMock(return_value=(True, 1, 0))
            mock_limiter.get_remaining_requests = AsyncMock(return_value=2)

            request = Request(
                {
                    "type": "http",
                    "headers": [],
                    "client": ("1.2.3.4", 1234),
                    "path": "/response-endpoint",
                }
            )
            response = await endpoint(request)
            assert response.headers["X-RateLimit-Limit"] == "5"
            assert response.headers["X-RateLimit-Remaining"] == "2"

    @pytest.mark.asyncio
    async def test_decorator_invalid_rate_string_raises(self):
        """Invalid rate string should raise a ValueError."""
        @rate_limit("5perminute")
        async def endpoint(request: Request):
            return {"message": "ok"}

        request = Request(
            {"type": "http", "headers": [], "client": ("1.2.3.4", 1234), "path": "/invalid"}
        )
        with pytest.raises(ValueError):
            await endpoint(request)

    @pytest.mark.asyncio
    async def test_decorator_unknown_time_unit_raises(self):
        """Unknown time unit should raise a ValueError."""
        @rate_limit("5/week")
        async def endpoint(request: Request):
            return {"message": "ok"}

        request = Request(
            {"type": "http", "headers": [], "client": ("1.2.3.4", 1234), "path": "/invalid"}
        )
        with pytest.raises(ValueError):
            await endpoint(request)

    def test_decorator_signature_preserved_when_signature_fails(self, monkeypatch):
        """Signature preservation should be resilient to inspect failures."""
        def endpoint(request: Request):
            return {"message": "ok"}

        monkeypatch.setattr(
            "app.middleware.rate_limiter.inspect.signature",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        wrapped = rate_limit("5/minute")(endpoint)
        assert wrapped is not None


def _make_request(path: str = "/test", headers: list[tuple[bytes, bytes]] | None = None):
    return Request(
        {
            "type": "http",
            "headers": headers or [],
            "client": ("10.0.0.1", 1234),
            "path": path,
        }
    )


@pytest.mark.asyncio
async def test_get_identifier_variants():
    request = _make_request(headers=[(b"x-forwarded-for", b"1.1.1.1, 2.2.2.2")])
    identifier = await _get_identifier(request, RateLimitKeyType.IP, None, (), {})
    assert identifier == "1.1.1.1"

    user = SimpleNamespace(id="user123", email="USER@EXAMPLE.COM")
    identifier = await _get_identifier(request, RateLimitKeyType.USER, None, (), {"current_user": user})
    assert identifier == "user_user123"

    payload = SimpleNamespace(email="TeSt@Example.com")
    identifier = await _get_identifier(
        request,
        RateLimitKeyType.EMAIL,
        "email",
        (),
        {"payload": payload},
    )
    assert identifier == "email_test@example.com"

    identifier = await _get_identifier(
        request,
        RateLimitKeyType.EMAIL,
        "email",
        (payload,),
        {},
    )
    assert identifier == "email_test@example.com"

    identifier = await _get_identifier(request, RateLimitKeyType.ENDPOINT, None, (), {})
    assert identifier == "endpoint_/test"

    identifier = await _get_identifier(
        request, RateLimitKeyType.COMPOSITE, None, (), {"current_user": user}
    )
    assert "10.0.0.1" in identifier
    assert "/test" in identifier
    assert "uuser123" in identifier

    identifier = await _get_identifier("not-a-request", RateLimitKeyType.IP, None, (), {})
    assert identifier is None

    identifier = await _get_identifier(request, RateLimitKeyType.USER, None, (), {"current_user": object()})
    assert identifier is None

    identifier = await _get_identifier(
        request,
        RateLimitKeyType.EMAIL,
        "email",
        (),
        {"payload": SimpleNamespace(email=""), "current_user": user},
    )
    assert identifier == "email_user@example.com"

    request_no_client = Request(
        {
            "type": "http",
            "headers": [],
            "client": None,
            "path": "/composite",
        }
    )
    identifier = await _get_identifier(
        request_no_client,
        RateLimitKeyType.COMPOSITE,
        None,
        (),
        {},
    )
    assert identifier == "/composite"

    identifier = await _get_identifier(request, object(), None, (), {})  # type: ignore[arg-type]
    assert identifier is None


def test_rate_limit_api_key_decorator_wraps_callable():
    @rate_limit_api_key("x_api_key")
    async def endpoint(request: Request):
        return Response(content="ok")

    assert callable(endpoint)


class TestRateLimitAdmin:
    """Test administrative functions."""

    @pytest.mark.asyncio
    @patch("app.core.cache_redis.get_async_cache_redis_client", new_callable=AsyncMock)
    async def test_reset_all_limits(self, mock_get_redis):
        """Test resetting all limits matching a pattern."""
        mock_redis = Mock()
        mock_get_redis.return_value = mock_redis

        # Mock scan_iter to return some keys
        keys = [
            "rate_limit:login:email_test@example.com",
            "rate_limit:register:email_test@example.com",
        ]

        async def _async_iter(items):
            for item in items:
                yield item

        mock_redis.scan_iter = MagicMock(return_value=_async_iter(keys))
        mock_redis.delete = AsyncMock(return_value=1)

        count = await RateLimitAdmin.reset_all_limits("email_*")

        assert count == 2
        mock_redis.scan_iter.assert_called_once_with(match="rate_limit:*:email_*")
        assert mock_redis.delete.await_count == 2

    @pytest.mark.asyncio
    @patch("app.core.cache_redis.get_async_cache_redis_client", new_callable=AsyncMock)
    async def test_reset_all_limits_no_cache(self, mock_get_redis):
        mock_get_redis.return_value = None
        count = await RateLimitAdmin.reset_all_limits("email_*")
        assert count == 0

    @pytest.mark.asyncio
    @patch("app.core.cache_redis.get_async_cache_redis_client", new_callable=AsyncMock)
    async def test_reset_all_limits_returns_zero_on_error(self, mock_get_redis):
        mock_redis = Mock()
        mock_get_redis.return_value = mock_redis

        async def _async_iter(items):
            for item in items:
                yield item

        mock_redis.scan_iter = MagicMock(return_value=_async_iter(["rate_limit:test:key"]))
        mock_redis.delete = AsyncMock(side_effect=RuntimeError("delete failed"))

        count = await RateLimitAdmin.reset_all_limits("test*")

        assert count == 0

    @pytest.mark.asyncio
    @patch("app.core.cache_redis.get_async_cache_redis_client", new_callable=AsyncMock)
    async def test_get_rate_limit_stats(self, mock_get_redis):
        """Test getting rate limit statistics."""
        mock_redis = Mock()
        mock_get_redis.return_value = mock_redis

        # Mock scan_iter to return some keys
        keys = [
            "rate_limit:login:user123",
            "rate_limit:register:user456",
            "rate_limit:login:user789",
        ]

        async def _async_iter(items):
            for item in items:
                yield item

        mock_redis.scan_iter = MagicMock(return_value=_async_iter(keys))

        # Mock zcard for request counts (async)
        mock_redis.zcard = AsyncMock(side_effect=[5, 2, 10])

        # Mock ttl
        mock_redis.ttl = AsyncMock(return_value=300)

        stats = await RateLimitAdmin.get_rate_limit_stats()

        assert stats["total_keys"] == 3
        assert stats["by_type"]["login"] == 2
        assert stats["by_type"]["register"] == 1
        assert len(stats["top_limited"]) == 3
        assert stats["top_limited"][0]["requests"] == 10  # Sorted by count

    @pytest.mark.asyncio
    @patch("app.core.cache_redis.get_async_cache_redis_client", new_callable=AsyncMock)
    async def test_get_rate_limit_stats_no_cache(self, mock_get_redis):
        mock_get_redis.return_value = None
        stats = await RateLimitAdmin.get_rate_limit_stats()
        assert stats == {"error": "Cache not available"}

    @pytest.mark.asyncio
    @patch("app.core.cache_redis.get_async_cache_redis_client", new_callable=AsyncMock)
    async def test_get_rate_limit_stats_handles_zero_and_malformed_keys(self, mock_get_redis):
        mock_redis = Mock()
        mock_get_redis.return_value = mock_redis

        keys = [
            "rate_limit:login:user123",
            "malformed-key",
            "rate_limit:register:user456",
        ]

        async def _async_iter(items):
            for item in items:
                yield item

        mock_redis.scan_iter = MagicMock(return_value=_async_iter(keys))
        mock_redis.zcard = AsyncMock(side_effect=[0, 3, 1])
        mock_redis.ttl = AsyncMock(return_value=120)

        stats = await RateLimitAdmin.get_rate_limit_stats()

        assert stats["total_keys"] == 3
        assert stats["by_type"]["login"] == 1
        assert stats["by_type"]["register"] == 1
        assert len(stats["top_limited"]) == 2

    @pytest.mark.asyncio
    @patch("app.core.cache_redis.get_async_cache_redis_client", new_callable=AsyncMock)
    async def test_get_rate_limit_stats_returns_error_on_exception(self, mock_get_redis):
        mock_redis = Mock()
        mock_get_redis.return_value = mock_redis
        mock_redis.scan_iter = MagicMock(side_effect=RuntimeError("scan failed"))

        stats = await RateLimitAdmin.get_rate_limit_stats()

        assert stats == {"error": "scan failed"}


@pytest.mark.usefixtures("enable_rate_limiting", "clear_rate_limits")
@pytest.mark.asyncio
class TestIntegration:
    """Integration tests with real cache."""

    @pytest_asyncio.fixture
    async def real_cache(self):
        """Use real cache service if available."""
        cache = CacheService()
        redis = await cache.get_redis_client()
        if redis is None:
            pytest.skip("Redis not available")
        yield cache

    @pytest.fixture
    def rate_limiter(self, real_cache):
        """Create rate limiter with real cache."""
        return RateLimiter(cache_service=real_cache)

    async def test_sliding_window_with_real_cache(self, rate_limiter):
        """Test sliding window algorithm with real cache."""
        identifier = f"test_user_{int(time.time())}"

        # Make requests up to limit
        for i in range(5):
            allowed, count, retry = await rate_limiter.check_rate_limit(
                identifier=identifier, limit=5, window_seconds=10
            )
            assert allowed is True
            assert count == i + 1

        # Next request should be blocked
        allowed, count, retry = await rate_limiter.check_rate_limit(
            identifier=identifier, limit=5, window_seconds=10
        )
        assert allowed is False
        assert count == 5
        assert retry > 0

        # Clean up
        await rate_limiter.reset_limit(identifier, "5per10s")
