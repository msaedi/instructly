"""
Pure ASGI Rate Limiter Middleware

This is a pure ASGI implementation that avoids the BaseHTTPMiddleware
"No response returned" issue.
"""

import logging
import re
import time
from typing import Optional

from starlette.datastructures import MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from ..core.config import settings
from ..core.constants import ALLOWED_ORIGINS, CORS_ORIGIN_REGEX, SSE_PATH_PREFIX
from .rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


class RateLimitMiddlewareASGI:
    """
    Pure ASGI middleware for rate limiting.

    This implementation avoids the BaseHTTPMiddleware issues
    by working directly with ASGI scope, receive, and send.
    """

    def __init__(self, app: ASGIApp, rate_limiter: Optional[RateLimiter] = None) -> None:
        self.app = app
        self.rate_limiter = rate_limiter or RateLimiter()
        self.general_limit = getattr(settings, "rate_limit_general_per_minute", 100)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """ASGI application entrypoint."""

        # Only handle HTTP requests
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # In test environment: do not enforce, but still emit standard headers
        try:
            if getattr(settings, "is_testing", False):

                async def send_testing_wrapper(message: Message) -> None:
                    if message["type"] == "http.response.start":
                        headers = MutableHeaders(scope=message)
                        headers["X-RateLimit-Limit"] = str(self.general_limit)
                        headers["X-RateLimit-Remaining"] = str(self.general_limit)
                        headers["X-RateLimit-Reset"] = str(int(time.time()) + 60)
                    await send(message)

                await self.app(scope, receive, send_testing_wrapper)
                return
        except Exception:
            pass

        # Honor global rate limit toggle (disable entirely when false)
        if not getattr(settings, "rate_limit_enabled", True):
            await self.app(scope, receive, send)
            return

        # Get the path
        path = scope.get("path", "")
        method = scope.get("method", "GET")

        # Skip rate limiting for health checks, metrics (all), and SSE endpoints
        # SSE connections are long-lived and should never be rate-limited
        if (
            path in ["/health", "/metrics/health", "/metrics/performance"]
            or path.startswith("/metrics")
            or path.startswith(SSE_PATH_PREFIX)
        ):
            await self.app(scope, receive, send)
            return

        if method == "GET" and path == "/health":
            await self.app(scope, receive, send)
            return

        # Always allow CORS preflight requests
        if method == "OPTIONS":
            await self.app(scope, receive, send)
            return

        # Get client IP
        client = scope.get("client")
        client_ip = client[0] if client else "unknown"

        # Light exemptions for local/preview on low-risk routes
        site_mode = getattr(settings, "site_mode", "local") or "local"
        if site_mode in {"local", "preview"}:
            if path in {"/auth/me", "/api/public/session/guest"} or path.startswith("/metrics"):
                await self.app(scope, receive, send)
                return

        # Apply general rate limit
        allowed, requests_made, retry_after = self.rate_limiter.check_rate_limit(
            identifier=client_ip, limit=self.general_limit, window_seconds=60, window_name="general"
        )

        if not allowed:
            # Try to reflect CORS headers for blocked responses
            origin_header = None
            try:
                for k, v in scope.get("headers", []) or []:
                    if k.decode().lower() == "origin":
                        origin_header = v.decode()
                        break
            except Exception:
                origin_header = None

            cors_headers: dict[str, str] = {}
            try:
                if origin_header:
                    origin_allowed = origin_header in ALLOWED_ORIGINS or (
                        CORS_ORIGIN_REGEX and re.match(CORS_ORIGIN_REGEX, origin_header)
                    )
                    if origin_allowed:
                        cors_headers = {
                            "Access-Control-Allow-Origin": origin_header,
                            "Access-Control-Allow-Credentials": "true",
                            "Access-Control-Allow-Headers": "*",
                            "Access-Control-Allow-Methods": "*",
                        }
            except Exception:
                # Best-effort; if anything fails, send without extra CORS headers
                cors_headers = {}

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
                    **cors_headers,
                },
            )
            try:
                # TEMP TRACE: log bucket info for analysis
                logger.warning(
                    "[RATE_LIMIT] 429",
                    extra={
                        "path": path,
                        "method": method,
                        "bucket": "general",
                        "key": client_ip,
                        "count_before": requests_made,
                        "limit": self.general_limit,
                        "retry_after": retry_after,
                    },
                )
            except Exception:
                pass

            # Send the response
            await response(scope, receive, send)
            return

        # Get remaining requests for headers
        remaining = self.rate_limiter.get_remaining_requests(
            identifier=client_ip, limit=self.general_limit, window_seconds=60, window_name="general"
        )

        # Create a wrapper for send to add rate limit headers
        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                # Add rate limit headers
                headers = MutableHeaders(scope=message)
                headers["X-RateLimit-Limit"] = str(self.general_limit)
                headers["X-RateLimit-Remaining"] = str(remaining)
                headers["X-RateLimit-Reset"] = str(int(time.time()) + 60)

            await send(message)

        # Process the request with our wrapped send
        await self.app(scope, receive, send_wrapper)
