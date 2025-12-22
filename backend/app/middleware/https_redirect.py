# backend/app/middleware/https_redirect.py
"""
HTTPS redirect middleware for InstaInstru.

Forces HTTP traffic to HTTPS in production environments.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
import logging

from fastapi import Request
from fastapi.responses import RedirectResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)


class HTTPSRedirectMiddleware(BaseHTTPMiddleware):
    """
    Middleware to redirect HTTP requests to HTTPS.

    Only active in production environments to avoid issues during local development.
    Checks the X-Forwarded-Proto header which is set by load balancers/proxies.
    """

    def __init__(
        self,
        app: ASGIApp,
        force_https: bool = True,
        exclude_paths: list[str] | None = None,
    ) -> None:
        super().__init__(app)
        self.force_https = force_https
        self.exclude_paths = exclude_paths or ["/api/v1/health", "/api/v1/metrics/prometheus"]

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        # Skip HTTPS redirect for excluded paths (health checks, etc.)
        if request.url.path in self.exclude_paths:
            return await call_next(request)

        # Only redirect if force_https is enabled
        if not self.force_https:
            return await call_next(request)

        # Check if request is already HTTPS
        # In production, check the X-Forwarded-Proto header
        forwarded_proto = request.headers.get("X-Forwarded-Proto", "")

        # Also check the scheme directly (for local testing)
        is_https = forwarded_proto == "https" or request.url.scheme == "https"

        if not is_https and forwarded_proto == "http":
            # Build HTTPS URL
            url = request.url.replace(scheme="https")

            # Log the redirect for monitoring
            logger.info(f"Redirecting HTTP to HTTPS: {request.url} -> {url}")

            # Return permanent redirect
            return RedirectResponse(url=str(url), status_code=301)

        # Add Strict-Transport-Security header to HTTPS responses
        response = await call_next(request)

        if is_https:
            # HSTS header - tells browsers to only use HTTPS for 1 year
            response.headers[
                "Strict-Transport-Security"
            ] = "max-age=31536000; includeSubDomains; preload"

        return response


def create_https_redirect_middleware(
    force_https: bool = True,
) -> type[HTTPSRedirectMiddleware]:
    """
    Factory function to create HTTPS redirect middleware with configuration.

    Args:
        force_https: Whether to force HTTPS redirects (disable for local dev)

    Returns:
        Configured middleware class
    """

    class ConfiguredHTTPSRedirectMiddleware(HTTPSRedirectMiddleware):
        def __init__(self, app: ASGIApp) -> None:
            super().__init__(app, force_https=force_https)

    return ConfiguredHTTPSRedirectMiddleware
