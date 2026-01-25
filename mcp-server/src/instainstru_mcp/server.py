"""FastMCP server entry point for InstaInstru admin tools."""

from __future__ import annotations

import os
import secrets

from typing import Any, cast

from fastmcp import FastMCP
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.routing import Route

from .auth import MCPAuth
from .client import InstaInstruClient
from .config import Settings
from .tools import founding, instructors, invites, metrics, search


class BearerAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.url.path == "/api/v1/health":
            return await call_next(request)

        expected_token = os.environ.get("INSTAINSTRU_MCP_AUTH_TOKEN")
        if not expected_token:
            return JSONResponse(
                {"error": "Server authentication not configured"},
                status_code=500,
            )

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                {"error": "Missing or invalid Authorization header"},
                status_code=401,
            )

        provided_token = auth_header[7:]
        if not secrets.compare_digest(provided_token, expected_token):
            return JSONResponse({"error": "Invalid token"}, status_code=401)

        return await call_next(request)


def create_mcp(
    settings: Settings | None = None,
    auth: MCPAuth | None = None,
    client: InstaInstruClient | None = None,
) -> FastMCP:
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
    app_instance.add_middleware(BearerAuthMiddleware)
    _attach_health_route(app_instance)
    return app_instance


mcp = create_mcp()
app = cast(Any, mcp).http_app(transport="sse")
app.add_middleware(BearerAuthMiddleware)
_attach_health_route(app)


def main() -> None:
    import uvicorn

    port = int(os.getenv("PORT", "8001"))
    uvicorn.run("instainstru_mcp.server:app", host="0.0.0.0", port=port)
