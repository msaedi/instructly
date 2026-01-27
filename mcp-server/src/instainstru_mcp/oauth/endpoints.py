"""OAuth 2.0 endpoints for MCP metadata proxying."""

from __future__ import annotations

import logging
from typing import Any

import httpx
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from ..config import Settings

logger = logging.getLogger(__name__)


def attach_oauth_routes(app: Any, settings: Settings) -> None:
    def _base_url(request: Request) -> str:
        if settings.oauth_issuer:
            return settings.oauth_issuer.rstrip("/")
        host = request.headers.get("host", "mcp.instainstru.com")
        if host.startswith("http://") or host.startswith("https://"):
            return host.rstrip("/")
        return f"https://{host}".rstrip("/")

    async def oauth_authorization_server(request: Request):
        """Proxy WorkOS authorization server metadata for MCP compatibility."""
        if not settings.workos_domain:
            return JSONResponse({"error": "WorkOS not configured"}, status_code=503)
        workos_url = f"https://{settings.workos_domain}/.well-known/oauth-authorization-server"
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(workos_url, timeout=10.0)
            return JSONResponse(response.json(), status_code=response.status_code)
        except Exception as exc:
            logger.error("WorkOS metadata fetch failed: %s", exc)
            return JSONResponse(
                {"error": "WorkOS metadata fetch failed"},
                status_code=502,
            )

    async def oauth_protected_resource(request: Request):
        """Return protected resource metadata pointing to WorkOS."""
        if not settings.workos_domain:
            return JSONResponse({"error": "WorkOS not configured"}, status_code=503)
        issuer = _base_url(request)
        return JSONResponse(
            {
                "resource": issuer,
                "authorization_servers": [f"https://{settings.workos_domain}"],
                "bearer_methods_supported": ["header"],
            }
        )

    async def openid_configuration(request: Request):
        """Proxy WorkOS OpenID configuration."""
        if not settings.workos_domain:
            return JSONResponse({"error": "WorkOS not configured"}, status_code=503)
        workos_url = f"https://{settings.workos_domain}/.well-known/openid-configuration"
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(workos_url, timeout=10.0)
            return JSONResponse(response.json(), status_code=response.status_code)
        except Exception as exc:
            logger.error("WorkOS OIDC metadata fetch failed: %s", exc)
            return JSONResponse(
                {"error": "WorkOS OIDC metadata fetch failed"},
                status_code=502,
            )

    async def jwks_endpoint(_request: Request):
        """Proxy WorkOS JWKS."""
        if not settings.workos_domain:
            return JSONResponse({"error": "WorkOS not configured"}, status_code=503)
        workos_url = f"https://{settings.workos_domain}/oauth2/jwks"
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(workos_url, timeout=10.0)
            return JSONResponse(response.json(), status_code=response.status_code)
        except Exception as exc:
            logger.error("WorkOS JWKS fetch failed: %s", exc)
            return JSONResponse(
                {"error": "WorkOS JWKS fetch failed"},
                status_code=502,
            )

    async def userinfo(request: Request):
        """Proxy WorkOS userinfo endpoint."""
        if not settings.workos_domain:
            return JSONResponse({"error": "WorkOS not configured"}, status_code=503)
        auth_header = request.headers.get("authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse({"error": "invalid_request"}, status_code=401)
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"https://{settings.workos_domain}/oauth2/userinfo",
                    headers={"Authorization": auth_header},
                    timeout=10.0,
                )
            return JSONResponse(response.json(), status_code=response.status_code)
        except Exception as exc:
            logger.error("WorkOS userinfo fetch failed: %s", exc)
            return JSONResponse(
                {"error": "WorkOS userinfo fetch failed"},
                status_code=502,
            )

    app.routes.append(
        Route(
            "/.well-known/oauth-protected-resource",
            oauth_protected_resource,
            methods=["GET"],
        )
    )
    app.routes.append(
        Route(
            "/.well-known/oauth-protected-resource/{path:path}",
            oauth_protected_resource,
            methods=["GET"],
        )
    )
    app.routes.append(
        Route(
            "/.well-known/oauth-authorization-server",
            oauth_authorization_server,
            methods=["GET"],
        )
    )
    app.routes.append(
        Route(
            "/.well-known/openid-configuration",
            openid_configuration,
            methods=["GET"],
        )
    )
    app.routes.append(Route("/.well-known/jwks.json", jwks_endpoint, methods=["GET"]))
    app.routes.append(Route("/oauth2/userinfo", userinfo, methods=["GET"]))
