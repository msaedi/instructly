"""FastMCP server entry point for InstaInstru admin tools."""

from __future__ import annotations

import logging
import os
import secrets
from typing import TYPE_CHECKING, Any, cast

import httpx
import jwt as pyjwt
from jwt import PyJWKClient
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse, RedirectResponse
from starlette.routing import Route

from .client import InstaInstruClient
from .config import Settings
from .tools import founding, instructors, invites, metrics, search

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from fastmcp import FastMCP

# Allowed admin emails (enforce access control server-side)
ALLOWED_EMAILS = {
    "admin@instainstru.com",
    "faeze@instainstru.com",
    "mehdi@instainstru.com",
}


class WorkOSAuthMiddleware:
    """ASGI middleware supporting simple Bearer tokens and WorkOS JWTs."""

    EXEMPT_PATHS = {
        "/api/v1/health",
        "/.well-known/oauth-protected-resource",
        "/.well-known/oauth-authorization-server",
        "/.well-known/openid-configuration",
        "/register",
        "/oauth2/register",
    }

    EXEMPT_PATH_PREFIXES = ("/.well-known/oauth-protected-resource/",)

    def __init__(self, app: Any, settings: Settings) -> None:
        self.app = app
        self.settings = settings
        self.simple_token = os.environ.get("INSTAINSTRU_MCP_API_SERVICE_TOKEN")

        # WorkOS JWT validation
        self.workos_domain = settings.workos_domain
        self.workos_issuer = f"https://{self.workos_domain}"
        self.jwks_client = None

        if self.workos_domain:
            jwks_url = f"{self.workos_issuer}/oauth2/jwks"
            self.jwks_client = PyJWKClient(jwks_url)
            logger.info("WorkOS JWT validation configured for %s", self.workos_domain)

        if not self.simple_token and not self.jwks_client:
            logger.warning("No authentication configured!")

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if path in self.EXEMPT_PATHS or path.startswith(self.EXEMPT_PATH_PREFIXES):
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        auth_header = headers.get(b"authorization", b"").decode()

        if not auth_header.startswith("Bearer "):
            await self._send_401(
                scope,
                receive,
                send,
                "Missing or invalid Authorization header",
            )
            return

        token = auth_header[7:]
        auth_result = self._authenticate(token)

        if auth_result is None:
            await self._send_401(scope, receive, send, "Invalid token")
            return

        # Check email allowlist for WorkOS tokens
        if auth_result.get("method") == "workos":
            email = auth_result.get("claims", {}).get("email", "").lower()
            if email not in ALLOWED_EMAILS:
                logger.warning("Access denied for email: %s", email)
                await self._send_error(scope, receive, send, 403, "Access denied")
                return

        scope["auth"] = auth_result
        await self.app(scope, receive, send)

    def _authenticate(self, token: str) -> dict | None:
        # Try simple token first
        if self.simple_token and secrets.compare_digest(token, self.simple_token):
            logger.debug("Authenticated via simple Bearer token")
            return {"method": "simple_token"}

        # Try WorkOS JWT
        if self.jwks_client:
            try:
                signing_key = self.jwks_client.get_signing_key_from_jwt(token)
                claims = pyjwt.decode(
                    token,
                    signing_key.key,
                    algorithms=["RS256"],
                    issuer=self.workos_issuer,
                    options={"verify_aud": False},
                )
                logger.info(
                    "Authenticated via WorkOS: %s",
                    claims.get("email", claims.get("sub")),
                )
                return {"method": "workos", "claims": claims}
            except pyjwt.InvalidTokenError as exc:
                logger.info("WorkOS JWT validation failed: %s", exc)

        return None

    async def _send_401(self, scope, receive, send, message: str):
        """Send 401 with WWW-Authenticate header per RFC 9728."""
        resource_metadata_url = "https://mcp.instainstru.com/.well-known/oauth-protected-resource"
        headers = {
            "WWW-Authenticate": f'Bearer resource_metadata="{resource_metadata_url}"',
        }
        response = JSONResponse({"error": message}, status_code=401, headers=headers)
        await response(scope, receive, send)

    async def _send_error(self, scope, receive, send, status_code: int, message: str):
        response = JSONResponse({"error": message}, status_code=status_code)
        await response(scope, receive, send)


def _load_settings() -> Settings:
    token = os.environ.get("INSTAINSTRU_MCP_API_SERVICE_TOKEN", "")
    return Settings(api_service_token=token)


def _cors_headers() -> dict[str, str]:
    """Return CORS headers for cross-origin requests."""
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Authorization, Content-Type, Accept",
    }


def create_mcp(settings: Settings | None = None) -> "FastMCP":
    from fastmcp import FastMCP

    from .auth import MCPAuth

    settings = settings or _load_settings()
    auth = MCPAuth(settings)
    client = InstaInstruClient(settings, auth)

    mcp = FastMCP("iNSTAiNSTRU Admin")

    founding.register_tools(mcp, client)
    instructors.register_tools(mcp, client)
    invites.register_tools(mcp, client)
    search.register_tools(mcp, client)
    metrics.register_tools(mcp, client)

    return mcp


def _attach_health_route(app: Any) -> None:
    async def health_check(_request):
        return JSONResponse({"status": "ok", "service": "instainstru-mcp"})

    app.routes.append(Route("/api/v1/health", health_check, methods=["GET", "HEAD"]))


def _attach_oauth_metadata_routes(app: Any, settings: Settings) -> None:
    """Attach OAuth 2.0 Protected Resource Metadata endpoint (RFC 9728)."""

    async def oauth_protected_resource(_request):
        if not settings.workos_domain:
            return JSONResponse({"error": "WorkOS not configured"}, status_code=503)

        return JSONResponse(
            {
                "resource": "https://mcp.instainstru.com/sse",
                "authorization_servers": [f"https://{settings.workos_domain}"],
                "bearer_methods_supported": ["header"],
                "scopes_supported": ["openid", "profile", "email"],
            }
        )

    async def oauth_authorization_server(_request):
        """Proxy WorkOS OAuth authorization server metadata."""
        if not settings.workos_domain:
            return JSONResponse({"error": "WorkOS not configured"}, status_code=503)

        workos_metadata_url = (
            f"https://{settings.workos_domain}/.well-known/oauth-authorization-server"
        )
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(workos_metadata_url, timeout=10.0)
            return JSONResponse(response.json(), headers=_cors_headers())
        except Exception as exc:  # pragma: no cover - defensive
            return JSONResponse({"error": str(exc)}, status_code=502, headers=_cors_headers())

    async def openid_configuration(_request):
        """Proxy WorkOS OpenID configuration."""
        if not settings.workos_domain:
            return JSONResponse({"error": "WorkOS not configured"}, status_code=503)

        workos_url = f"https://{settings.workos_domain}/.well-known/openid-configuration"
        fallback_url = f"https://{settings.workos_domain}/.well-known/oauth-authorization-server"
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(workos_url, timeout=10.0)
            if response.status_code == 200:
                return JSONResponse(response.json(), headers=_cors_headers())
            return RedirectResponse(url=fallback_url, status_code=302, headers=_cors_headers())
        except Exception:
            return RedirectResponse(url=fallback_url, status_code=302, headers=_cors_headers())

    async def register_redirect(request):
        """Redirect or proxy client registration to WorkOS."""
        if not settings.workos_domain:
            return JSONResponse({"error": "WorkOS not configured"}, status_code=503)

        workos_url = f"https://{settings.workos_domain}/oauth2/register"
        if request.method == "POST":
            try:
                body = await request.body()
                headers = {"Content-Type": "application/json"}
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        workos_url,
                        content=body,
                        headers=headers,
                        timeout=10.0,
                    )
                return JSONResponse(
                    response.json(),
                    status_code=response.status_code,
                    headers=_cors_headers(),
                )
            except Exception as exc:
                return JSONResponse({"error": str(exc)}, status_code=502, headers=_cors_headers())

        return RedirectResponse(url=workos_url, status_code=302, headers=_cors_headers())

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
    app.routes.append(
        Route(
            "/register",
            register_redirect,
            methods=["GET", "POST", "OPTIONS"],
        )
    )
    app.routes.append(
        Route(
            "/oauth2/register",
            register_redirect,
            methods=["GET", "POST", "OPTIONS"],
        )
    )


def create_app(settings: Settings | None = None):
    settings = settings or _load_settings()
    mcp = create_mcp(settings=settings)
    app_instance = cast(Any, mcp).http_app(transport="sse")
    _attach_health_route(app_instance)
    _attach_oauth_metadata_routes(app_instance, settings)
    app_with_auth = WorkOSAuthMiddleware(app_instance, settings)
    return CORSMiddleware(
        app_with_auth,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Accept"],
        expose_headers=["*"],
    )


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
        host="0.0.0.0",  # nosec B104
        port=port,
        factory=True,
    )
