# backend/app/middleware/rate_limiter.py
"""
Rate limiting middleware for InstaInstru platform.

Implements comprehensive rate limiting to protect against:
- DDoS attacks
- Brute force attacks
- Email spam
- Resource exhaustion

Uses DragonflyDB (Redis-compatible) for distributed rate limiting.
"""

from enum import Enum
from functools import wraps
import hashlib
import inspect
import logging
import time
from typing import Any, Callable, Dict, Optional, Tuple

from fastapi import HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from ..core.config import settings
from ..services.cache_service import CacheService, get_cache_service

logger = logging.getLogger(__name__)


class RateLimitKeyType(Enum):
    """Types of keys for rate limiting."""

    IP = "ip"
    USER = "user"
    EMAIL = "email"
    ENDPOINT = "endpoint"
    COMPOSITE = "composite"


class RateLimitAlgorithm(Enum):
    """Rate limiting algorithms."""

    SLIDING_WINDOW = "sliding_window"
    TOKEN_BUCKET = "token_bucket"
    FIXED_WINDOW = "fixed_window"


class RateLimiter:
    """
    Core rate limiting logic using sliding window algorithm.

    Provides accurate rate limiting with Redis/DragonflyDB backend.
    """

    def __init__(self, cache_service: Optional[CacheService] = None):
        """
        Initialize rate limiter.

        Args:
            cache_service: Cache service instance (uses singleton if not provided)
        """
        self.cache = cache_service or get_cache_service()
        self.enabled = getattr(settings, "rate_limit_enabled", True)

    def _get_cache_key(self, identifier: str, window_name: str) -> str:
        """
        Generate cache key for rate limiting.

        Args:
            identifier: Unique identifier (IP, user ID, email, etc.)
            window_name: Name of the rate limit window

        Returns:
            Cache key string
        """
        # Hash long identifiers to keep keys reasonable
        if len(identifier) > 32:
            identifier = hashlib.md5(identifier.encode()).hexdigest()[:16]

        return f"rate_limit:{window_name}:{identifier}"

    def _get_window_start(self, window_seconds: int) -> int:
        """
        Get the start timestamp for the current window.

        Args:
            window_seconds: Window size in seconds

        Returns:
            Window start timestamp
        """
        now = int(time.time())
        return now - window_seconds

    def check_rate_limit(
        self, identifier: str, limit: int, window_seconds: int, window_name: Optional[str] = None
    ) -> Tuple[bool, int, int]:
        """
        Check if request is within rate limit using sliding window.

        Args:
            identifier: Unique identifier for rate limiting
            limit: Maximum requests allowed
            window_seconds: Time window in seconds
            window_name: Optional name for the window (for cache key)

        Returns:
            Tuple of (allowed, requests_made, retry_after_seconds)
        """
        if not self.enabled:
            return True, 0, 0

        if not self.cache.redis:
            # If cache is unavailable, allow request but log warning
            logger.warning("Rate limiting bypassed - cache unavailable")
            return True, 0, 0

        window_name = window_name or f"{limit}per{window_seconds}s"
        cache_key = self._get_cache_key(identifier, window_name)

        try:
            # Use Redis pipeline for atomic operations
            pipe = self.cache.redis.pipeline()

            now = time.time()
            window_start = now - window_seconds

            # Remove old entries outside the window
            pipe.zremrangebyscore(cache_key, 0, window_start)

            # Count requests in current window
            pipe.zcard(cache_key)

            # Add current request timestamp
            pipe.zadd(cache_key, {str(now): now})

            # Set expiration on the key
            pipe.expire(cache_key, window_seconds + 60)  # Extra 60s buffer

            # Execute pipeline
            results = pipe.execute()

            # results[1] is the count before adding current request
            requests_in_window = results[1]

            if requests_in_window >= limit:
                # Get oldest request timestamp to calculate retry_after
                oldest_timestamp = self.cache.redis.zrange(cache_key, 0, 0, withscores=True)

                if oldest_timestamp:
                    retry_after = int(oldest_timestamp[0][1] + window_seconds - now)
                    retry_after = max(1, retry_after)  # At least 1 second
                else:
                    retry_after = window_seconds

                # Remove the current request we just added since it's rejected
                self.cache.redis.zrem(cache_key, str(now))

                return False, requests_in_window, retry_after

            return True, requests_in_window + 1, 0

        except Exception as e:
            logger.error(f"Rate limit check failed: {e}")
            # On error, allow request but log
            return True, 0, 0

    def reset_limit(self, identifier: str, window_name: str) -> bool:
        """
        Reset rate limit for an identifier.

        Args:
            identifier: Unique identifier
            window_name: Window name

        Returns:
            True if reset successful
        """
        if not self.cache.redis:
            return False

        cache_key = self._get_cache_key(identifier, window_name)

        try:
            return self.cache.delete(cache_key)
        except Exception as e:
            logger.error(f"Failed to reset rate limit: {e}")
            return False

    def get_remaining_requests(
        self, identifier: str, limit: int, window_seconds: int, window_name: Optional[str] = None
    ) -> int:
        """
        Get remaining requests in current window.

        Args:
            identifier: Unique identifier
            limit: Maximum requests allowed
            window_seconds: Window size in seconds
            window_name: Optional window name

        Returns:
            Number of remaining requests
        """
        if not self.enabled or not self.cache.redis:
            return limit

        window_name = window_name or f"{limit}per{window_seconds}s"
        cache_key = self._get_cache_key(identifier, window_name)

        try:
            # Remove old entries and count current
            window_start = time.time() - window_seconds
            self.cache.redis.zremrangebyscore(cache_key, 0, window_start)
            current_count = self.cache.redis.zcard(cache_key)

            return max(0, limit - current_count)

        except Exception as e:
            logger.error(f"Failed to get remaining requests: {e}")
            return limit


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware for rate limiting.

    Applies general rate limits to all endpoints.
    """

    def __init__(self, app, rate_limiter: Optional[RateLimiter] = None):
        super().__init__(app)
        self.rate_limiter = rate_limiter or RateLimiter()

        # General rate limits from config
        self.general_limit = getattr(settings, "rate_limit_general_per_minute", 100)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Apply rate limiting to incoming requests."""

        # Skip rate limiting for health checks
        if request.url.path == "/health":
            return await call_next(request)

        # Get client identifier (IP address)
        client_ip = request.client.host if request.client else "unknown"

        # Apply general rate limit
        allowed, requests_made, retry_after = self.rate_limiter.check_rate_limit(
            identifier=client_ip, limit=self.general_limit, window_seconds=60, window_name="general"
        )

        if not allowed:
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "detail": f"Rate limit exceeded. Try again in {retry_after} seconds.",
                    "code": "RATE_LIMIT_EXCEEDED",
                    "retry_after": retry_after,
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(self.general_limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(time.time()) + retry_after),
                },
            )

        # Process request
        response = await call_next(request)

        # Add rate limit headers
        remaining = self.rate_limiter.get_remaining_requests(
            identifier=client_ip, limit=self.general_limit, window_seconds=60, window_name="general"
        )

        response.headers["X-RateLimit-Limit"] = str(self.general_limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(int(time.time()) + 60)

        return response


def rate_limit(
    rate_string: str,
    key_type: RateLimitKeyType = RateLimitKeyType.IP,
    key_field: Optional[str] = None,
    error_message: Optional[str] = None,
):
    """
    Decorator for applying rate limits to specific endpoints.

    Args:
        rate_string: Rate limit string (e.g., "5/minute", "100/hour", "1000/day")
        key_type: Type of key to use for rate limiting
        key_field: Specific field to use for key (e.g., "email" from request body)
        error_message: Custom error message

    Example:
        @rate_limit("5/minute", key_type=RateLimitKeyType.IP)
        @rate_limit("3/hour", key_type=RateLimitKeyType.EMAIL, key_field="email")
        async def login(request: LoginRequest):
            ...
    """

    def decorator(func: Callable) -> Callable:
        # Check if the function is async
        import asyncio

        is_async = asyncio.iscoroutinefunction(func)

        async def _call_wrapped(*args: Any, **kwargs: Any) -> Any:
            result = func(*args, **kwargs)
            if inspect.isawaitable(result):
                return await result
            return result

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Find request object in args/kwargs
            request = None
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break
            if not request:
                request = kwargs.get("request")

            if not request:
                # Can't rate limit without request, just call function
                return await _call_wrapped(*args, **kwargs)

            # Parse rate string (e.g., "5/minute" -> (5, 60))
            parts = rate_string.split("/")
            if len(parts) != 2:
                raise ValueError(f"Invalid rate string: {rate_string}")

            limit = int(parts[0])

            # Convert time unit to seconds
            time_unit = parts[1].lower()
            time_multipliers = {"second": 1, "minute": 60, "hour": 3600, "day": 86400}

            # Handle plural forms
            for unit, multiplier in time_multipliers.items():
                if time_unit.startswith(unit):
                    window_seconds = multiplier
                    break
            else:
                raise ValueError(f"Unknown time unit: {time_unit}")

            # Get identifier based on key type
            identifier = await _get_identifier(request, key_type, key_field, args, kwargs)

            if not identifier:
                # Can't identify request, allow it
                return await _call_wrapped(*args, **kwargs)

            # Check rate limit
            rate_limiter = RateLimiter()
            window_name = f"{func.__name__}_{rate_string.replace('/', 'per')}"

            allowed, requests_made, retry_after = rate_limiter.check_rate_limit(
                identifier=identifier,
                limit=limit,
                window_seconds=window_seconds,
                window_name=window_name,
            )

            if not allowed:
                error_msg = (
                    error_message or f"Rate limit exceeded. Try again in {retry_after} seconds."
                )

                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail={
                        "message": error_msg,
                        "code": "RATE_LIMIT_EXCEEDED",
                        "retry_after": retry_after,
                    },
                    headers={
                        "Retry-After": str(retry_after),
                        "X-RateLimit-Limit": str(limit),
                        "X-RateLimit-Remaining": "0",
                        "X-RateLimit-Reset": str(int(time.time()) + retry_after),
                    },
                )

            # Add rate limit headers to response
            response = await _call_wrapped(*args, **kwargs)

            if isinstance(response, Response):
                remaining = rate_limiter.get_remaining_requests(
                    identifier=identifier,
                    limit=limit,
                    window_seconds=window_seconds,
                    window_name=window_name,
                )

                response.headers["X-RateLimit-Limit"] = str(limit)
                response.headers["X-RateLimit-Remaining"] = str(remaining)
                response.headers["X-RateLimit-Reset"] = str(int(time.time()) + window_seconds)

            return response

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            # For sync functions, we need to run the async wrapper in a new event loop
            import asyncio

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(async_wrapper(*args, **kwargs))
            finally:
                loop.close()

        # Return async wrapper for async functions, sync wrapper for sync functions
        wrapper = async_wrapper if is_async else sync_wrapper
        # Preserve the original function signature for FastAPI dependency injection
        try:
            wrapper.__signature__ = inspect.signature(func)
        except Exception:
            pass
        return wrapper

    return decorator


async def _get_identifier(
    request: Request,
    key_type: RateLimitKeyType,
    key_field: Optional[str],
    args: tuple,
    kwargs: dict,
) -> Optional[str]:
    """
    Extract identifier from request based on key type.

    Args:
        request: FastAPI request object
        key_type: Type of key to extract
        key_field: Specific field for extraction
        args: Function arguments
        kwargs: Function keyword arguments

    Returns:
        Identifier string or None
    """

    # Ensure we have a Request object
    if not isinstance(request, Request):
        logger.warning(f"Expected Request object, got {type(request).__name__}")
        return None

    if key_type == RateLimitKeyType.IP:
        # Get client IP
        if request.client:
            # Check for X-Forwarded-For header (proxy/load balancer)
            forwarded_for = request.headers.get("X-Forwarded-For")
            if forwarded_for:
                # Take the first IP in the chain
                return forwarded_for.split(",")[0].strip()
            return request.client.host
        return "unknown"

    elif key_type == RateLimitKeyType.USER:
        # Get user ID from authenticated user
        # Look for current_user in kwargs (from dependency injection)
        user = kwargs.get("current_user")
        if user and hasattr(user, "id"):
            return f"user_{user.id}"
        return None

    elif key_type == RateLimitKeyType.EMAIL:
        # Get email from request body or authenticated user
        if key_field:
            # For POST requests with Pydantic models, check kwargs
            # FastAPI passes the parsed model as a keyword argument
            for arg_name, arg_value in kwargs.items():
                if hasattr(arg_value, key_field):
                    email = getattr(arg_value, key_field)
                    if email:
                        return f"email_{email.lower()}"

            # Also check positional args for Pydantic models
            for arg in args:
                if hasattr(arg, key_field) and not isinstance(arg, Request):
                    email = getattr(arg, key_field)
                    if email:
                        return f"email_{email.lower()}"

        # Try from authenticated user
        user = kwargs.get("current_user")
        if user and hasattr(user, "email"):
            return f"email_{user.email.lower()}"

        return None

    elif key_type == RateLimitKeyType.ENDPOINT:
        # Use endpoint path as identifier
        return f"endpoint_{request.url.path}"

    elif key_type == RateLimitKeyType.COMPOSITE:
        # Combine multiple identifiers
        parts = []

        # Add IP
        if request.client:
            parts.append(request.client.host)

        # Add endpoint
        parts.append(request.url.path)

        # Add user if authenticated
        user = kwargs.get("current_user")
        if user and hasattr(user, "id"):
            parts.append(f"u{user.id}")

        return "_".join(parts)

    return None


# Convenience decorators for common patterns
def rate_limit_auth(func: Callable) -> Callable:
    """Apply authentication-specific rate limits."""
    return rate_limit("5/minute", key_type=RateLimitKeyType.IP)(func)


def rate_limit_password_reset(func: Callable) -> Callable:
    """Apply password reset rate limits."""
    # First by IP to prevent distributed attacks
    func = rate_limit("10/hour", key_type=RateLimitKeyType.IP)(func)
    # Then by email to prevent targeted attacks
    func = rate_limit("3/hour", key_type=RateLimitKeyType.EMAIL, key_field="email")(func)
    return func


def rate_limit_api_key(api_key_field: str = "api_key"):
    """Apply rate limits based on API key."""

    def decorator(func: Callable) -> Callable:
        return rate_limit(
            "1000/hour", key_type=RateLimitKeyType.COMPOSITE, key_field=api_key_field
        )(func)

    return decorator


# Admin functions for rate limit management
class RateLimitAdmin:
    """Administrative functions for rate limit management."""

    @staticmethod
    def reset_all_limits(identifier_pattern: str) -> int:
        """
        Reset all rate limits matching a pattern.

        Args:
            identifier_pattern: Pattern to match (e.g., "email_*")

        Returns:
            Number of limits reset
        """
        cache = get_cache_service()
        if not cache.redis:
            return 0

        pattern = f"rate_limit:*:{identifier_pattern}"
        count = 0

        try:
            for key in cache.redis.scan_iter(match=pattern):
                if cache.redis.delete(key):
                    count += 1

            logger.info(f"Reset {count} rate limits matching pattern: {identifier_pattern}")
            return count

        except Exception as e:
            logger.error(f"Failed to reset rate limits: {e}")
            return 0

    @staticmethod
    def get_rate_limit_stats() -> Dict[str, Any]:
        """Get statistics about current rate limits."""
        cache = get_cache_service()
        if not cache.redis:
            return {"error": "Cache not available"}

        stats = {"total_keys": 0, "by_type": {}, "top_limited": []}

        try:
            # Scan all rate limit keys
            for key in cache.redis.scan_iter(match="rate_limit:*"):
                stats["total_keys"] += 1

                # Parse key type
                parts = key.split(":")
                if len(parts) >= 2:
                    window_type = parts[1]
                    stats["by_type"][window_type] = stats["by_type"].get(window_type, 0) + 1

                # Get request count
                count = cache.redis.zcard(key)
                if count > 0:
                    ttl = cache.redis.ttl(key)
                    stats["top_limited"].append({"key": key, "requests": count, "ttl_seconds": ttl})

            # Sort by request count
            stats["top_limited"].sort(key=lambda x: x["requests"], reverse=True)
            stats["top_limited"] = stats["top_limited"][:10]  # Top 10

            return stats

        except Exception as e:
            logger.error(f"Failed to get rate limit stats: {e}")
            return {"error": str(e)}


# Export key components
__all__ = [
    "RateLimiter",
    "RateLimitMiddleware",
    "rate_limit",
    "rate_limit_auth",
    "rate_limit_password_reset",
    "rate_limit_api_key",
    "RateLimitKeyType",
    "RateLimitAdmin",
]
