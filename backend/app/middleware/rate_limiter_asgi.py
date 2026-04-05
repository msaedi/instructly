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

from ..core.config import secret_or_plain, settings
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
        self._bypass_token: str = secret_or_plain(
            getattr(settings, "rate_limit_bypass_token", None)
        ).strip()

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

    def _testing_send_wrapper(self, send: Send) -> Send:
        async def send_testing_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["X-RateLimit-Limit"] = str(self.general_limit)
                headers["X-RateLimit-Remaining"] = str(self.general_limit)
                headers["X-RateLimit-Reset"] = str(int(time.time()) + 60)
            await send(message)

        return send_testing_wrapper

    @staticmethod
    def _is_skipped_request(path: str, method: str) -> bool:
        return path == "/api/v1/health" or path.startswith(SSE_PATH_PREFIX) or method == "OPTIONS"

    @staticmethod
    def _origin_header(scope: Scope) -> str | None:
        try:
            for key, value in scope.get("headers", []) or []:
                if key.decode().lower() == "origin":
                    return str(value.decode())
        except Exception:
            return None
        return None

    @staticmethod
    def _cors_headers_for_origin(origin_header: str | None) -> dict[str, str]:
        if not origin_header:
            return {}
        try:
            origin_allowed = origin_header in ALLOWED_ORIGINS or (
                CORS_ORIGIN_REGEX and re.match(CORS_ORIGIN_REGEX, origin_header)
            )
            if origin_allowed:
                return {
                    "Access-Control-Allow-Origin": origin_header,
                    "Access-Control-Allow-Credentials": "true",
                    "Access-Control-Allow-Headers": "*",
                    "Access-Control-Allow-Methods": "*",
                }
        except Exception:
            return {}
        return {}

    @staticmethod
    def _invite_limit_response(retry_after: int) -> JSONResponse:
        return JSONResponse(
            status_code=429,
            content={
                "code": "rate_limited",
                "detail": "Too many invites from this IP. Try again later.",
            },
            headers={"Retry-After": str(retry_after)},
        )

    @staticmethod
    def _metrics_limit_response(retry_after: int) -> JSONResponse:
        return JSONResponse(
            status_code=429,
            content={
                "detail": "Rate limit exceeded. Try again later.",
                "code": "RATE_LIMIT_EXCEEDED",
                "retry_after": retry_after,
            },
            headers={"Retry-After": str(retry_after)},
        )

    def _is_local_exempt(self, path: str, method: str) -> bool:
        site_mode = getattr(settings, "site_mode", "local") or "local"
        if site_mode not in {"local", "preview"}:
            return False
        if path in {"/auth/me", "/api/v1/public/session/guest"}:
            return True
        if path.startswith("/api/v1/reviews/instructor/") and method == "GET":
            return True
        if path.startswith("/api/v1/services/") and method == "GET":
            return True
        return path.startswith("/api/v1/instructors") and method == "GET"

    async def _handle_invite_limit(
        self, scope: Scope, receive: Receive, send: Send, path: str, method: str, client_ip: str
    ) -> bool:
        if not (method == "POST" and self._invite_path.match(path)):
            return False
        allowed, _, retry_after = await self.rate_limiter.check_rate_limit(
            identifier=f"invite:{client_ip}",
            limit=self.invite_limit,
            window_seconds=self.invite_window_seconds,
            window_name="bgc_invite_ip",
        )
        if allowed:
            return False
        await self._invite_limit_response(retry_after)(scope, receive, send)
        return True

    async def _handle_metrics_limit(
        self, scope: Scope, receive: Receive, send: Send, path: str, client_ip: str
    ) -> bool:
        if path != "/api/v1/internal/metrics":
            return False
        metrics_limit = getattr(settings, "metrics_rate_limit_per_min", 6)
        if metrics_limit <= 0:
            return False
        allowed, _, retry_after = await self.rate_limiter.check_rate_limit(
            identifier=f"metrics:{client_ip}",
            limit=metrics_limit,
            window_seconds=60,
            window_name="metrics",
        )
        if allowed:
            return False
        await self._metrics_limit_response(retry_after)(scope, receive, send)
        return True

    def _log_general_limit_block(
        self, path: str, method: str, client_ip: str, requests_made: int, retry_after: int
    ) -> None:
        try:
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
            logger.debug("Non-fatal error ignored", exc_info=True)

    def _general_limit_response(
        self,
        scope: Scope,
        retry_after: int,
        client_ip: str,
        path: str,
        method: str,
        requests_made: int,
    ) -> JSONResponse:
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
                **self._cors_headers_for_origin(self._origin_header(scope)),
            },
        )
        self._log_general_limit_block(path, method, client_ip, requests_made, retry_after)
        return response

    def _success_send_wrapper(self, send: Send, remaining: int) -> Send:
        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["X-RateLimit-Limit"] = str(self.general_limit)
                headers["X-RateLimit-Remaining"] = str(remaining)
                headers["X-RateLimit-Reset"] = str(int(time.time()) + 60)
            await send(message)

        return send_wrapper

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """ASGI application entrypoint."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        if self._has_bypass_token(scope):
            await self.app(scope, receive, send)
            return
        try:
            if getattr(settings, "is_testing", False):
                await self.app(scope, receive, self._testing_send_wrapper(send))
                return
        except Exception:
            logger.debug("Non-fatal error ignored", exc_info=True)
        if not getattr(settings, "rate_limit_enabled", True):
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        method = scope.get("method", "GET")
        if self._is_skipped_request(path, method):
            await self.app(scope, receive, send)
            return
        client_ip = self._extract_client_ip(scope)
        if await self._handle_invite_limit(scope, receive, send, path, method, client_ip):
            return
        if self._is_local_exempt(path, method):
            await self.app(scope, receive, send)
            return
        if await self._handle_metrics_limit(scope, receive, send, path, client_ip):
            return
        allowed, requests_made, retry_after = await self.rate_limiter.check_rate_limit(
            identifier=client_ip, limit=self.general_limit, window_seconds=60, window_name="general"
        )
        if not allowed:
            response = self._general_limit_response(
                scope, retry_after, client_ip, path, method, requests_made
            )
            await response(scope, receive, send)
            return
        remaining = await self.rate_limiter.get_remaining_requests(
            identifier=client_ip, limit=self.general_limit, window_seconds=60, window_name="general"
        )
        await self.app(scope, receive, self._success_send_wrapper(send, remaining))
