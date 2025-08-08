"""
Pure ASGI Rate Limiter Middleware

This is a pure ASGI implementation that avoids the BaseHTTPMiddleware
"No response returned" issue.
"""

import json
import logging
import time
from typing import Optional

from starlette.datastructures import MutableHeaders
from starlette.responses import JSONResponse

from ..core.config import settings
from .rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


class RateLimitMiddlewareASGI:
    """
    Pure ASGI middleware for rate limiting.

    This implementation avoids the BaseHTTPMiddleware issues
    by working directly with ASGI scope, receive, and send.
    """

    def __init__(self, app, rate_limiter: Optional[RateLimiter] = None):
        self.app = app
        self.rate_limiter = rate_limiter or RateLimiter()
        self.general_limit = getattr(settings, "rate_limit_general_per_minute", 100)

    async def __call__(self, scope, receive, send):
        """ASGI application entrypoint."""

        # Only handle HTTP requests
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Get the path
        path = scope.get("path", "")

        # Skip rate limiting for health checks, metrics, and SSE endpoints
        # SSE connections are long-lived and should never be rate-limited
        if path in ["/health", "/metrics/health", "/metrics/performance"] or path.startswith("/api/messages/stream"):
            await self.app(scope, receive, send)
            return

        # Get client IP
        client = scope.get("client")
        client_ip = client[0] if client else "unknown"

        # Apply general rate limit
        allowed, requests_made, retry_after = self.rate_limiter.check_rate_limit(
            identifier=client_ip, limit=self.general_limit, window_seconds=60, window_name="general"
        )

        if not allowed:
            # Send rate limit response directly
            response = JSONResponse(
                status_code=429,
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

            # Send the response
            await response(scope, receive, send)
            return

        # Get remaining requests for headers
        remaining = self.rate_limiter.get_remaining_requests(
            identifier=client_ip, limit=self.general_limit, window_seconds=60, window_name="general"
        )

        # Create a wrapper for send to add rate limit headers
        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                # Add rate limit headers
                headers = MutableHeaders(scope=message)
                headers["X-RateLimit-Limit"] = str(self.general_limit)
                headers["X-RateLimit-Remaining"] = str(remaining)
                headers["X-RateLimit-Reset"] = str(int(time.time()) + 60)

            await send(message)

        # Process the request with our wrapped send
        await self.app(scope, receive, send_wrapper)
