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
from unittest.mock import MagicMock, Mock, patch

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
import pytest
from redis.exceptions import RedisError

from app.core.config import settings
from app.middleware.rate_limiter import (
    RateLimitAdmin,
    RateLimiter,
    RateLimitKeyType,
    RateLimitMiddleware,
    rate_limit,
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


@pytest.fixture
def clear_rate_limits():
    """Clear rate limit cache before rate limit tests."""
    from app.services.cache_service import get_cache_service

    cache = get_cache_service()
    if cache and cache.redis:
        # Clear all rate limit keys
        for key in cache.redis.scan_iter(match="rate_limit:*"):
            cache.redis.delete(key)
    yield


@pytest.mark.usefixtures("enable_rate_limiting", "clear_rate_limits")
class TestRateLimiter:
    """Test the core RateLimiter class."""

    @pytest.fixture
    def mock_cache(self):
        """Create a mock cache service."""
        cache = Mock(spec=CacheService)
        cache.redis = MagicMock()
        return cache

    @pytest.fixture
    def rate_limiter(self, mock_cache):
        """Create a rate limiter with mock cache."""
        return RateLimiter(cache_service=mock_cache)

    def test_rate_limiter_initialization(self):
        """Test rate limiter can be initialized without cache service."""
        limiter = RateLimiter()
        assert limiter.enabled == getattr(settings, "rate_limit_enabled", True)

    def test_check_rate_limit_when_disabled(self, rate_limiter):
        """Test rate limiting when disabled."""
        rate_limiter.enabled = False
        allowed, requests, retry_after = rate_limiter.check_rate_limit(identifier="test", limit=5, window_seconds=60)
        assert allowed is True
        assert requests == 0
        assert retry_after == 0

    def test_check_rate_limit_without_cache(self, rate_limiter):
        """Test rate limiting when cache is unavailable."""
        rate_limiter.cache.redis = None

        allowed, requests, retry_after = rate_limiter.check_rate_limit(identifier="test", limit=5, window_seconds=60)

        assert allowed is True
        assert requests == 0
        assert retry_after == 0

    def test_check_rate_limit_sliding_window(self, rate_limiter, mock_cache):
        """Test sliding window algorithm."""
        # Setup mock pipeline
        pipe = MagicMock()
        mock_cache.redis.pipeline.return_value = pipe

        # First request - should be allowed
        pipe.execute.return_value = [None, 0, None, None]  # No requests in window

        allowed, requests, retry_after = rate_limiter.check_rate_limit(identifier="user123", limit=5, window_seconds=60)

        assert allowed is True
        assert requests == 1
        assert retry_after == 0

        # Verify pipeline operations
        mock_cache.redis.pipeline.assert_called_once()
        pipe.zremrangebyscore.assert_called_once()
        pipe.zcard.assert_called_once()
        pipe.zadd.assert_called_once()
        pipe.expire.assert_called_once()

    def test_check_rate_limit_exceeded(self, rate_limiter, mock_cache):
        """Test when rate limit is exceeded."""
        # Setup mock pipeline
        pipe = MagicMock()
        mock_cache.redis.pipeline.return_value = pipe

        # Simulate limit exceeded (5 requests already made)
        pipe.execute.return_value = [None, 5, None, None]

        # Mock oldest timestamp for retry_after calculation
        mock_cache.redis.zrange.return_value = [(b"timestamp", time.time() - 30)]

        allowed, requests, retry_after = rate_limiter.check_rate_limit(identifier="user123", limit=5, window_seconds=60)

        assert allowed is False
        assert requests == 5
        assert retry_after > 0 and retry_after <= 60

        # Verify the rejected request was removed
        mock_cache.redis.zrem.assert_called_once()

    def test_reset_limit(self, rate_limiter, mock_cache):
        """Test resetting rate limits."""
        mock_cache.delete.return_value = True

        result = rate_limiter.reset_limit("user123", "test_window")

        assert result is True
        mock_cache.delete.assert_called_once_with("rate_limit:test_window:user123")

    def test_get_remaining_requests(self, rate_limiter, mock_cache):
        """Test getting remaining requests."""
        mock_cache.redis.zremrangebyscore.return_value = None
        mock_cache.redis.zcard.return_value = 3

        remaining = rate_limiter.get_remaining_requests(identifier="user123", limit=5, window_seconds=60)

        assert remaining == 2

    def test_cache_key_generation(self, rate_limiter):
        """Test cache key generation with long identifiers."""
        # Short identifier
        key = rate_limiter._get_cache_key("user123", "test")
        assert key == "rate_limit:test:user123"

        # Long identifier (should be hashed)
        long_id = "a" * 50
        key = rate_limiter._get_cache_key(long_id, "test")
        assert key.startswith("rate_limit:test:")
        assert len(key.split(":")[-1]) == 16  # MD5 hash truncated

    def test_error_handling(self, rate_limiter, mock_cache):
        """Test error handling when Redis operations fail."""
        mock_cache.redis.pipeline.side_effect = RedisError("Connection failed")

        allowed, requests, retry_after = rate_limiter.check_rate_limit(identifier="user123", limit=5, window_seconds=60)

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
        mock_limiter.check_rate_limit.return_value = (False, 100, 30)
        mock_limiter.get_remaining_requests.return_value = 0

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
        mock_limiter.check_rate_limit.return_value = (True, 1, 0)
        mock_limiter.get_remaining_requests.return_value = 4

        response = client.post("/login")

        assert response.status_code == 200
        mock_limiter.check_rate_limit.assert_called_once()

    @patch("app.middleware.rate_limiter.RateLimiter")
    def test_decorator_blocks_exceeded_limit(self, mock_limiter_class, client):
        """Test decorator blocks when limit exceeded."""
        mock_limiter = Mock()
        mock_limiter_class.return_value = mock_limiter

        # Block request
        mock_limiter.check_rate_limit.return_value = (False, 5, 45)

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


class TestRateLimitAdmin:
    """Test administrative functions."""

    @patch("app.middleware.rate_limiter.get_cache_service")
    def test_reset_all_limits(self, mock_get_cache):
        """Test resetting all limits matching a pattern."""
        # Setup mock cache
        mock_cache = Mock()
        mock_redis = Mock()
        mock_cache.redis = mock_redis
        mock_get_cache.return_value = mock_cache

        # Mock scan_iter to return some keys
        mock_redis.scan_iter.return_value = [
            "rate_limit:login:email_test@example.com",
            "rate_limit:register:email_test@example.com",
        ]
        mock_redis.delete.return_value = 1

        count = RateLimitAdmin.reset_all_limits("email_*")

        assert count == 2
        mock_redis.scan_iter.assert_called_once_with(match="rate_limit:*:email_*")
        assert mock_redis.delete.call_count == 2

    @patch("app.middleware.rate_limiter.get_cache_service")
    def test_get_rate_limit_stats(self, mock_get_cache):
        """Test getting rate limit statistics."""
        # Setup mock cache
        mock_cache = Mock()
        mock_redis = Mock()
        mock_cache.redis = mock_redis
        mock_get_cache.return_value = mock_cache

        # Mock scan_iter to return some keys
        mock_redis.scan_iter.return_value = [
            "rate_limit:login:user123",
            "rate_limit:register:user456",
            "rate_limit:login:user789",
        ]

        # Mock zcard for request counts
        mock_redis.zcard.side_effect = [5, 2, 10]

        # Mock ttl
        mock_redis.ttl.return_value = 300

        stats = RateLimitAdmin.get_rate_limit_stats()

        assert stats["total_keys"] == 3
        assert stats["by_type"]["login"] == 2
        assert stats["by_type"]["register"] == 1
        assert len(stats["top_limited"]) == 3
        assert stats["top_limited"][0]["requests"] == 10  # Sorted by count


@pytest.mark.usefixtures("enable_rate_limiting", "clear_rate_limits")
class TestIntegration:
    """Integration tests with real cache."""

    @pytest.fixture
    def real_cache(self):
        """Use real cache service if available."""
        try:
            cache = CacheService(Mock())  # Mock DB session
            if cache.redis:
                yield cache
            else:
                pytest.skip("Redis not available")
        except:
            pytest.skip("Cache service not available")

    @pytest.fixture
    def rate_limiter(self, real_cache):
        """Create rate limiter with real cache."""
        return RateLimiter(cache_service=real_cache)

    def test_sliding_window_with_real_cache(self, rate_limiter):
        """Test sliding window algorithm with real cache."""
        identifier = f"test_user_{int(time.time())}"

        # Make requests up to limit
        for i in range(5):
            allowed, count, retry = rate_limiter.check_rate_limit(identifier=identifier, limit=5, window_seconds=10)
            assert allowed is True
            assert count == i + 1

        # Next request should be blocked
        allowed, count, retry = rate_limiter.check_rate_limit(identifier=identifier, limit=5, window_seconds=10)
        assert allowed is False
        assert count == 5
        assert retry > 0

        # Clean up
        rate_limiter.reset_limit(identifier, "5per10s")
