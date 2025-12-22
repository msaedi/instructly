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
        self._invite_path = re.compile(r"^/api/instructors/[^/]+/bgc/(invite|recheck)$")
        self.invite_limit = 10
        self.invite_window_seconds = 3600
        # Bypass token for load testing (configured via RATE_LIMIT_BYPASS_TOKEN env var)
        self._bypass_token: str = getattr(settings, "rate_limit_bypass_token", "") or ""

    @staticmethod
    def _extract_client_ip(scope: Scope) -> str:
        headers = scope.get("headers") or []
        for header_name in ("cf-connecting-ip", "x-forwarded-for"):
            for key, value in headers:
                if key.decode().lower() == header_name:
                    candidate: str = value.decode().split(",")[0].strip()
                    if candidate:
                        return candidate
        client_info = scope.get("client")
        if isinstance(client_info, (tuple, list)) and client_info:
            host = client_info[0]
            if isinstance(host, str) and host:
                return host
        return "unknown"

    def _has_bypass_token(self, scope: Scope) -> bool:
        """Check if request has valid rate limit bypass token."""
        if not self._bypass_token:
            return False
        headers = scope.get("headers") or []
        for key, value in headers:
            if key.decode().lower() == "x-rate-limit-bypass":
                return bool(value.decode() == self._bypass_token)
        return False

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """ASGI application entrypoint."""

        # Only handle HTTP requests
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Check for rate limit bypass token (for load testing)
        if self._has_bypass_token(scope):
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

        # Skip rate limiting for health checks and SSE endpoints
        # SSE connections are long-lived and should never be rate-limited
        if path == "/api/v1/health" or path.startswith(SSE_PATH_PREFIX):
            await self.app(scope, receive, send)
            return

        # Always allow CORS preflight requests
        if method == "OPTIONS":
            await self.app(scope, receive, send)
            return

        # Get client IP
        client_ip = self._extract_client_ip(scope)

        if method == "POST" and self._invite_path.match(path):
            allowed_invite, _, retry_after_invite = await self.rate_limiter.check_rate_limit(
                identifier=f"invite:{client_ip}",
                limit=self.invite_limit,
                window_seconds=self.invite_window_seconds,
                window_name="bgc_invite_ip",
            )
            if not allowed_invite:
                response = JSONResponse(
                    status_code=429,
                    content={
                        "code": "rate_limited",
                        "detail": "Too many invites from this IP. Try again later.",
                    },
                    headers={"Retry-After": str(retry_after_invite)},
                )
                await response(scope, receive, send)
                return

        # Light exemptions for local/preview on low-risk routes
        site_mode = getattr(settings, "site_mode", "local") or "local"
        if site_mode in {"local", "preview"}:
            # Public read-only endpoints that don't need rate limiting in dev
            if path in {"/auth/me", "/api/v1/public/session/guest"}:
                await self.app(scope, receive, send)
                return
            # Public v1 read-only endpoints (reviews, services, instructors)
            if path.startswith("/api/v1/reviews/instructor/") and method == "GET":
                await self.app(scope, receive, send)
                return
            if path.startswith("/api/v1/services/") and method == "GET":
                await self.app(scope, receive, send)
                return
            if path.startswith("/api/v1/instructors") and method == "GET":
                await self.app(scope, receive, send)
                return

        if path == "/api/v1/internal/metrics":
            metrics_limit = getattr(settings, "metrics_rate_limit_per_min", 6)
            if metrics_limit > 0:
                allowed_metrics, _, retry_after_metrics = await self.rate_limiter.check_rate_limit(
                    identifier=f"metrics:{client_ip}",
                    limit=metrics_limit,
                    window_seconds=60,
                    window_name="metrics",
                )
                if not allowed_metrics:
                    response = JSONResponse(
                        status_code=429,
                        content={
                            "detail": "Rate limit exceeded. Try again later.",
                            "code": "RATE_LIMIT_EXCEEDED",
                            "retry_after": retry_after_metrics,
                        },
                        headers={"Retry-After": str(retry_after_metrics)},
                    )
                    await response(scope, receive, send)
                    return

        # Apply general rate limit
        allowed, requests_made, retry_after = await self.rate_limiter.check_rate_limit(
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
        remaining = await self.rate_limiter.get_remaining_requests(
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
