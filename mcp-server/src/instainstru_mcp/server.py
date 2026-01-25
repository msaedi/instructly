"""FastMCP server entry point for InstaInstru admin tools."""

from __future__ import annotations

import os
import secrets
import logging

from typing import Any, TYPE_CHECKING, cast
from starlette.responses import JSONResponse
from starlette.routing import Route

from .auth import MCPAuth, get_auth0_validator
from .client import InstaInstruClient
from .config import Settings
from .tools import founding, instructors, invites, metrics, search

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from fastmcp import FastMCP


class DualAuthMiddleware:
    """Raw ASGI middleware supporting simple Bearer tokens and Auth0 JWTs."""

    PUBLIC_PATHS = {"/api/v1/health"}

    def __init__(self, app: Any, settings: Settings | None = None) -> None:
        self.app = app
        self.simple_token = os.environ.get("INSTAINSTRU_MCP_API_SERVICE_TOKEN")
        self.auth0_validator = get_auth0_validator(settings=settings)

        if not self.simple_token and not self.auth0_validator:
            logger.warning(
                "No authentication configured! Server will reject all requests."
            )

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if path in self.PUBLIC_PATHS:
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        auth_header = headers.get(b"authorization", b"").decode()
        if not auth_header.startswith("Bearer "):
            self._log_auth_failure(scope)
            await self._send_error(
                scope,
                receive,
                send,
                status_code=401,
                message="Missing or invalid Authorization header",
            )
            return

        token = auth_header[7:]
        auth_result = await self._authenticate(token)
        if auth_result is None:
            self._log_auth_failure(scope)
            await self._send_error(
                scope,
                receive,
                send,
                status_code=401,
                message="Invalid token",
            )
            return

        scope["auth"] = auth_result
        await self.app(scope, receive, send)

    async def _authenticate(self, token: str) -> dict | None:
        if self.simple_token:
            if secrets.compare_digest(token, self.simple_token):
                logger.debug("Authenticated via simple Bearer token")
                return {"method": "simple_token"}

        if self.auth0_validator:
            try:
                import jwt as pyjwt

                claims = self.auth0_validator.validate(token)
                logger.debug(
                    "Authenticated via Auth0: %s",
                    claims.get("email", claims.get("sub")),
                )
                return {"method": "auth0", "claims": claims}
            except pyjwt.InvalidTokenError:
                pass

        if not self.simple_token and not self.auth0_validator:
            logger.error("No authentication methods configured")

        return None

    def _log_auth_failure(self, scope: dict) -> None:
        path = scope.get("path", "unknown")
        client = scope.get("client")
        client_ip = client[0] if client else "unknown"
        logger.warning("Auth failed: path=%s client_ip=%s", path, client_ip)

    async def _send_error(self, scope, receive, send, status_code: int, message: str):
        response = JSONResponse({"error": message}, status_code=status_code)
        await response(scope, receive, send)


def create_mcp(
    settings: Settings | None = None,
    auth: MCPAuth | None = None,
    client: InstaInstruClient | None = None,
) -> FastMCP:
    from fastmcp import FastMCP

    settings = settings or Settings()  # type: ignore[call-arg]
    auth = auth or MCPAuth(settings)
    client = client or InstaInstruClient(settings, auth)

    mcp = FastMCP("InstaInstru Admin")

    founding.register_tools(mcp, client)
    instructors.register_tools(mcp, client)
    invites.register_tools(mcp, client)
    search.register_tools(mcp, client)
    metrics.register_tools(mcp, client)

    return mcp


def _attach_health_route(app: Any) -> None:
    async def health_check(_request):
        """Health check endpoint for load balancer."""
        return JSONResponse({"status": "ok", "service": "instainstru-mcp"})

    app.routes.append(Route("/api/v1/health", health_check, methods=["GET", "HEAD"]))


def create_app(settings: Settings | None = None):
    mcp = create_mcp(settings=settings)
    app_instance = cast(Any, mcp).http_app(transport="sse")
    _attach_health_route(app_instance)
    return DualAuthMiddleware(app_instance, settings=settings)


_app: Any | None = None


def get_app() -> Any:
    """Get or create the app instance (lazy initialization)."""
    global _app
    if _app is None:
        _app = create_app()
    return _app


def main() -> None:
    import uvicorn

    port = int(os.getenv("PORT", "8001"))
    uvicorn.run(
        "instainstru_mcp.server:get_app",
        host="0.0.0.0",
        port=port,
        factory=True,
    )
