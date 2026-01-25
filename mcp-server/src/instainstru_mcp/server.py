"""FastMCP server entry point for InstaInstru admin tools."""

from __future__ import annotations

import os
import secrets
import logging

from typing import Any, TYPE_CHECKING, cast
import httpx
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

    EXEMPT_PATHS = {
        "/api/v1/health",
        "/.well-known/oauth-protected-resource",
        "/.well-known/oauth-authorization-server",
    }

    # RFC 9728 allows path-inserted metadata URLs like /.well-known/oauth-protected-resource/sse
    EXEMPT_PATH_PREFIXES = (
        "/.well-known/oauth-protected-resource/",
    )

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
        if path in self.EXEMPT_PATHS or path.startswith(self.EXEMPT_PATH_PREFIXES):
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        auth_header = headers.get(b"authorization", b"").decode()
        logger.info(
            "Auth header present: %s, starts with Bearer: %s",
            bool(auth_header),
            auth_header.startswith("Bearer ") if auth_header else False,
        )
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
        logger.info("Attempting authentication, token length: %d", len(token))
        if self.simple_token:
            if secrets.compare_digest(token, self.simple_token):
                logger.debug("Authenticated via simple Bearer token")
                return {"method": "simple_token"}

        logger.info(
            "Trying Auth0 validation, validator present: %s",
            bool(self.auth0_validator),
        )
        if self.auth0_validator:
            try:
                import jwt as pyjwt

                claims = self.auth0_validator.validate(token)
                logger.debug(
                    "Authenticated via Auth0: %s",
                    claims.get("email", claims.get("sub")),
                )
                return {"method": "auth0", "claims": claims}
            except pyjwt.InvalidTokenError as exc:
                error_msg = str(exc)
                if (
                    "Invalid payload string" in error_msg
                    or "invalid start byte" in error_msg.lower()
                    or "Not enough segments" in error_msg
                ):
                    logger.info(
                        "JWT decode failed, trying opaque token validation via /userinfo"
                    )
                    claims = _validate_opaque_token_sync(
                        token,
                        self.auth0_validator.domain,
                    )
                    if claims:
                        logger.debug(
                            "Authenticated via Auth0 userinfo: %s",
                            claims.get("email", claims.get("sub")),
                        )
                        return {"method": "auth0", "claims": claims}
                logger.info("Invalid Auth0 token: %s", exc)

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


def _attach_oauth_metadata_routes(app: Any, settings: Settings) -> None:
    async def oauth_protected_resource(request):
        """Return OAuth 2.0 Protected Resource Metadata (RFC 9728)."""
        if not settings.auth0_domain or not settings.auth0_audience:
            return JSONResponse(
                {"error": "Auth0 not configured"},
                status_code=503,
            )

        # Resource should be the actual SSE endpoint URL per RFC 9728
        resource_url = f"{settings.auth0_audience}/sse"
        issuer = f"https://{settings.auth0_domain}/"
        return JSONResponse(
            {
                "resource": resource_url,
                "authorization_servers": [issuer],
                "scopes_supported": ["openid", "profile", "email"],
                "client_id": "XzpdyOxOTN7QniAxJZWGELKyPRHnIAd4",  # Pre-registered Auth0 SPA
            }
        )

    async def oauth_authorization_server(_request):
        """Return OAuth 2.0 Authorization Server Metadata (RFC 8414)."""
        if not settings.auth0_domain or not settings.auth0_audience:
            return JSONResponse(
                {"error": "Auth0 not configured"},
                status_code=503,
            )

        base_url = f"https://{settings.auth0_domain}"
        issuer = f"{base_url}/"
        return JSONResponse(
            {
                "issuer": issuer,
                "authorization_endpoint": f"{base_url}/authorize",
                "token_endpoint": f"{base_url}/oauth/token",
                "jwks_uri": f"{base_url}/.well-known/jwks.json",
                "response_types_supported": ["code"],
                "grant_types_supported": ["authorization_code", "refresh_token"],
                "token_endpoint_auth_methods_supported": ["none"],  # PKCE public clients
                "code_challenge_methods_supported": ["S256"],
                "scopes_supported": ["openid", "profile", "email", "offline_access"],
            }
        )

    app.routes.append(
        Route(
            "/.well-known/oauth-protected-resource",
            oauth_protected_resource,
            methods=["GET"],
        )
    )
    # RFC 9728 path-inserted metadata: handle requests like /sse appended to the well-known path
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


def _validate_opaque_token_sync(token: str, auth0_domain: str) -> dict | None:
    """Validate opaque token via Auth0 /userinfo endpoint (sync)."""
    try:
        response = httpx.get(
            f"https://{auth0_domain}/userinfo",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10.0,
        )
        if response.status_code == 200:
            user_info = response.json()
            logger.info(
                "Opaque token validated for user: %s",
                user_info.get("email", user_info.get("sub")),
            )
            return user_info
        logger.warning("Opaque token validation returned %s", response.status_code)
        return None
    except Exception as exc:
        logger.warning("Opaque token validation failed: %s", exc)
        return None


def create_app(settings: Settings | None = None):
    settings = settings or Settings()  # type: ignore[call-arg]
    mcp = create_mcp(settings=settings)
    app_instance = cast(Any, mcp).http_app(transport="sse")
    _attach_health_route(app_instance)
    _attach_oauth_metadata_routes(app_instance, settings)
    return DualAuthMiddleware(app_instance, settings=settings)


_app: Any | None = None


def get_app() -> Any:
    """Get or create the app instance (lazy initialization)."""
    global _app
    if _app is None:
        settings = Settings()  # type: ignore[call-arg]
        mcp = create_mcp(settings=settings)
        app_instance = cast(Any, mcp).http_app(transport="sse")
        _attach_health_route(app_instance)
        _attach_oauth_metadata_routes(app_instance, settings)
        _app = DualAuthMiddleware(app_instance, settings=settings)
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
