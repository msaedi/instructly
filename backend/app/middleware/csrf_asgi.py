"""
ASGI middleware to enforce basic CSRF Origin/Referer checks for state-changing requests.

Rules:
- Enforced only for methods: POST, PUT, PATCH, DELETE
- Allowed when Origin/Referer host matches the configured frontend for the current SITE_MODE
- Skips known webhook paths (e.g., Stripe webhooks)

This is an additional defense-in-depth layer on top of CORS.
"""

from __future__ import annotations

import logging
import os
from typing import Optional
from urllib.parse import urlparse

from starlette.datastructures import MutableHeaders
from starlette.responses import JSONResponse

from ..core.config import settings

logger = logging.getLogger(__name__)


class CsrfOriginMiddlewareASGI:
    def __init__(self, app):
        self.app = app

    def _allowed_frontend_host(self) -> Optional[str]:
        site_mode = os.getenv("SITE_MODE", "").lower().strip()
        if site_mode == "preview":
            return settings.preview_frontend_domain
        if site_mode in {"prod", "production", "live"}:
            # Use first configured prod origin's host if available
            csv = (settings.prod_frontend_origins_csv or "").strip()
            first = [o.strip() for o in csv.split(",") if o.strip()]
            if first:
                try:
                    return urlparse(first[0]).hostname or first[0].replace("https://", "").replace("http://", "")
                except Exception:
                    return first[0]
            return "app.instainstru.com"
        # dev: no strict CSRF check
        return None

    def _is_webhook_path(self, path: str) -> bool:
        p = (path or "").lower()
        return "webhook" in p or "/payments/webhooks" in p

    def _is_exempt_path(self, path: str) -> bool:
        """Paths that should not be subject to CSRF origin checks.

        - During tests only: exempt auth endpoints (login, login-with-session, register)
          to allow TestClient to post credentials without Origin/Referer.
        - In all runtime modes, keep CSRF checks for these endpoints.
        """
        try:
            if not bool(getattr(settings, "is_testing", False)):
                return False
        except Exception:
            return False
        p = (path or "").lower()
        return p.startswith("/auth/login") or p.startswith("/auth/login-with-session") or p.startswith("/auth/register")

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "GET").upper()
        if method not in {"POST", "PUT", "PATCH", "DELETE"}:
            await self.app(scope, receive, send)
            return

        # Keep CSRF checks ON during tests so security tests can assert 403.
        # Only dev/local SITE_MODE disables origin checks above via _allowed_frontend_host().

        path = scope.get("path", "")
        if self._is_webhook_path(path) or self._is_exempt_path(path):
            await self.app(scope, receive, send)
            return

        allowed_host = self._allowed_frontend_host()
        if not allowed_host:
            await self.app(scope, receive, send)
            return

        origin = ""
        referer = ""
        try:
            for k, v in scope.get("headers", []) or []:
                k_l = k.decode().lower()
                if k_l == "origin":
                    origin = v.decode()
                elif k_l == "referer":
                    referer = v.decode()
        except Exception:
            origin = origin or ""
            referer = referer or ""

        def _host_of(url: str) -> str:
            try:
                return urlparse(url).hostname or ""
            except Exception:
                return ""

        oh = _host_of(origin)
        rh = _host_of(referer)

        if oh != allowed_host and rh != allowed_host:
            # Block with JSON response and include CORS-reflecting headers when safe
            headers = {
                "Content-Type": "application/json",
            }
            logger.info(
                "csrf_block",
                extra={
                    "event": "csrf_block",
                    "route": path,
                    "origin": origin,
                    "referer": referer,
                    "allowed_host": allowed_host,
                },
            )
            response = JSONResponse(
                status_code=403,
                content={
                    "detail": "Cross-site request blocked (invalid Origin/Referer)",
                    "code": "CSRF_ORIGIN_MISMATCH",
                },
                headers=headers,
            )
            await response(scope, receive, send)
            return

        # pass-through
        await self.app(scope, receive, send)
