"""FastMCP server entry point for InstaInstru admin tools."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import secrets
import subprocess
import time
from typing import TYPE_CHECKING, Any, Tuple
from urllib.parse import parse_qs, urlencode

import httpx
import jwt as pyjwt
import sentry_sdk
from cryptography.hazmat.primitives import serialization
from jwt import PyJWK
from sentry_sdk.integrations.mcp import MCPIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
from starlette.routing import Route

from .client import InstaInstruClient
from .clients.sentry_client import SentryClient
from .config import Settings
from .grafana_client import GrafanaCloudClient
from .oauth.crypto import build_jwks, normalize_pem
from .oauth.endpoints import attach_oauth_routes
from .tools import (
    celery,
    founding,
    instructors,
    invites,
    metrics,
    observability,
    operations,
    search,
    sentry,
    sentry_debug,
    services,
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from fastmcp import FastMCP

# Allowed admin emails (enforce access control server-side)
ALLOWED_EMAILS = {
    "admin@instainstru.com",
    "faeze@instainstru.com",
    "mehdi@instainstru.com",
}


def get_git_sha() -> str:
    """Get short git SHA for release tracking."""
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except Exception:
        return "unknown"


def _init_sentry(settings: Settings) -> None:
    if not settings.sentry_dsn:
        return

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment,
        release=get_git_sha(),
        integrations=[
            StarletteIntegration(
                transaction_style="endpoint",
                failed_request_status_codes={403, *range(500, 600)},
            ),
            MCPIntegration(),
        ],
        send_default_pii=True,
        enable_logs=True,
        traces_sample_rate=0.1,
        profiles_sample_rate=0.1,
    )
    print(f"Sentry initialized for environment: {settings.environment}")


class DualAuthMiddleware:
    """ASGI middleware supporting simple Bearer tokens and self-issued JWTs.

    Optimized for streamable-http transport:
    - No response buffering (streaming compatible)
    - Async JWKS fetching with aggressive caching
    - MCP method detection for mixed auth
    """

    EXEMPT_PATHS = {
        "/api/v1/health",
        "/.well-known/oauth-protected-resource",
        "/.well-known/oauth-authorization-server",
        "/.well-known/openid-configuration",
        "/.well-known/jwks.json",
        "/oauth/token",
        "/oauth/authorize",
        "/oauth2/token",
        "/oauth2/register",
        "/authorize",
        "/callback",
    }

    EXEMPT_PATH_PREFIXES = (
        "/.well-known/oauth-protected-resource/",
        "/.well-known/oauth-authorization-server/",
        "/oauth/",
        "/oauth2/",
    )

    # MCP methods that don't require authentication (ChatGPT mixed-auth pattern)
    UNAUTHENTICATED_MCP_METHODS = {
        "initialize",
        "notifications/initialized",
        "tools/list",
    }

    # Token verification cache: token digest -> (expiry_timestamp, auth_result)
    _auth_cache: dict[str, Tuple[float, dict]] = {}
    _AUTH_CACHE_TTL = 55
    _AUTH_CACHE_MAX_SIZE = 1000

    # JWKS cache: kid -> (expiry_timestamp, signing_key)
    _jwks_cache: dict[str, Tuple[float, Any]] = {}
    _JWKS_CACHE_TTL = 3600  # 1 hour - JWKS keys rarely change

    def __init__(self, app: Any, settings: Settings) -> None:
        self.app = app
        self.settings = settings
        self.simple_token = os.environ.get("INSTAINSTRU_MCP_API_SERVICE_TOKEN")

        self.oauth_issuer = settings.oauth_issuer
        self.jwt_key_id = settings.jwt_key_id
        self.jwt_signing_key = None
        self.jwt_public_key = None
        self.workos_domain = settings.workos_domain
        self.workos_client_id = settings.workos_client_id
        self.workos_issuer = None
        self.workos_jwks_url = None

        if settings.jwt_public_key:
            try:
                self.jwt_public_key = serialization.load_pem_public_key(
                    normalize_pem(settings.jwt_public_key).encode()
                )
                jwks = build_jwks(self.jwt_public_key, self.jwt_key_id)
                jwk = jwks["keys"][0]
                jwk.update({"kid": self.jwt_key_id, "use": "sig", "alg": "RS256"})
                self.jwt_signing_key = PyJWK.from_dict(jwk).key
                logger.info("JWT validation configured for self-issued tokens")
            except Exception as exc:
                logger.warning("Failed to load JWT public key: %s", exc)

        if self.workos_domain:
            self.workos_issuer = f"https://{self.workos_domain}"
            self.workos_jwks_url = f"{self.workos_issuer}/oauth2/jwks"
            logger.info("WorkOS JWT validation configured for %s", self.workos_domain)

        if not self.simple_token and not self.jwt_signing_key and not self.workos_jwks_url:
            logger.warning("No authentication configured!")

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        scope = _normalize_session_query(scope)
        scope = _normalize_mcp_path(scope)
        headers = dict(scope.get("headers", []))
        session_id = headers.get(b"mcp-session-id", b"").decode()
        protocol_version = headers.get(b"mcp-protocol-version", b"").decode()
        if session_id or protocol_version:
            logger.info(
                "MCP headers: session_id=%s protocol_version=%s",
                session_id[:16] if session_id else "none",
                protocol_version or "none",
            )

        path = scope.get("path", "")
        if path in self.EXEMPT_PATHS or path.startswith(self.EXEMPT_PATH_PREFIXES):
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "")
        if method == "DELETE" and path in {"/mcp", "/mcp/"}:
            logger.info("MCP session DELETE request")
            await self.app(scope, receive, send)
            return

        auth_header = headers.get(b"authorization", b"").decode()
        content_type = headers.get(b"content-type", b"").decode()
        is_json = "application/json" in content_type

        body = b""
        receive_for_app = receive
        mcp_method: str | None = None

        # For POST requests, read body to detect MCP method
        if method == "POST":
            body = await _read_body(receive)
            receive_for_app = _replay_body(body)
            if is_json and body:
                try:
                    parsed = json.loads(body.decode())
                    if isinstance(parsed, dict):
                        mcp_method = parsed.get("method")
                except Exception:
                    pass

            # Allow unauthenticated access for discovery methods
            if mcp_method in self.UNAUTHENTICATED_MCP_METHODS:
                logger.info("Allowing unauthenticated MCP method: %s", mcp_method)
                await self.app(scope, receive_for_app, send)
                return

        # Require Bearer token for all other requests
        if not auth_header.startswith("Bearer "):
            await self._send_auth_required(scope, send, body, is_json)
            return

        token = auth_header[7:]
        host = _host_from_scope(scope)
        issuer = (self.oauth_issuer or f"https://{host}").rstrip("/")
        auth_result = await self._authenticate(token, issuer)

        if auth_result is None:
            await self._send_auth_required(scope, send, body, is_json)
            return

        # Check email allowlist only for self-issued JWT tokens
        if auth_result.get("method") == "jwt":
            claims = auth_result.get("claims", {})
            email = (
                claims.get("email") or claims.get("preferred_username") or claims.get("sub", "")
            ).lower()
            logger.info("Checking email allowlist for: %s", email)
            if not email or email not in ALLOWED_EMAILS:
                logger.warning("Access denied for email: %s", email)
                await self._send_error(scope, receive_for_app, send, 403, "Access denied")
                return

        scope["auth"] = auth_result
        await self.app(scope, receive_for_app, send)

    async def _authenticate(self, token: str, issuer: str) -> dict | None:
        now = time.time()
        cache_key = hashlib.sha256(token.encode()).hexdigest()

        # Check auth cache
        cached = self._auth_cache.get(cache_key)
        if cached:
            expiry, cached_result = cached
            if now < expiry:
                logger.debug("Auth cache hit")
                return cached_result
            del self._auth_cache[cache_key]

        result: dict | None = None

        # Try simple token first (fastest)
        if self.simple_token and secrets.compare_digest(token, self.simple_token):
            logger.debug("Authenticated via simple Bearer token")
            result = {"method": "simple_token"}

        # Try self-issued JWT
        if result is None and self.jwt_signing_key:
            try:
                header = pyjwt.get_unverified_header(token)
                kid = header.get("kid")
                if kid and not secrets.compare_digest(kid, self.jwt_key_id):
                    raise pyjwt.InvalidTokenError("Invalid key id")
                claims = pyjwt.decode(
                    token,
                    self.jwt_signing_key,
                    algorithms=["RS256"],
                    issuer=issuer,
                    audience=issuer,
                )
                logger.info(
                    "Authenticated via self-issued JWT: %s", claims.get("email", claims.get("sub"))
                )
                result = {"method": "jwt", "claims": claims}
            except pyjwt.InvalidTokenError as exc:
                logger.debug("Self-issued JWT validation failed: %s", exc)

        # Try WorkOS JWT (async JWKS fetch with caching)
        if result is None and self.workos_jwks_url and self.workos_issuer:
            result = await self._validate_workos_token(token)

        # Cache successful auth
        if result:
            self._cache_auth(cache_key, result, now)

        return result

    async def _validate_workos_token(self, token: str) -> dict | None:
        """Validate WorkOS JWT with async JWKS fetching and caching."""
        try:
            # Get the key ID from token header
            header = pyjwt.get_unverified_header(token)
            kid = header.get("kid")
            if not kid:
                logger.debug("WorkOS token missing kid")
                return None

            # Get signing key (from cache or fetch)
            signing_key = await self._get_workos_signing_key(kid)
            if not signing_key:
                return None

            # Validate the token
            claims = pyjwt.decode(
                token,
                signing_key,
                algorithms=["RS256"],
                issuer=self.workos_issuer,
                options={"verify_aud": False},
            )
            logger.info("Authenticated via WorkOS JWT: %s", claims.get("email", claims.get("sub")))
            return {"method": "workos", "claims": claims}

        except pyjwt.InvalidTokenError as exc:
            logger.debug("WorkOS JWT validation failed: %s", exc)
            return None
        except Exception as exc:
            logger.warning("WorkOS JWT validation error: %s", exc)
            return None

    async def _get_workos_signing_key(self, kid: str) -> Any | None:
        """Get WorkOS signing key with async fetch and caching."""
        if not self.workos_jwks_url:
            return None
        now = time.time()

        # Check cache
        cached = self._jwks_cache.get(kid)
        if cached:
            expiry, key = cached
            if now < expiry:
                logger.debug("JWKS cache hit for kid=%s", kid[:8])
                return key
            del self._jwks_cache[kid]

        # Fetch JWKS asynchronously
        logger.info("Fetching JWKS for kid=%s from %s", kid[:8], self.workos_jwks_url)
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(self.workos_jwks_url)
                response.raise_for_status()
                jwks_data = response.json()

            # Find the matching key
            for key_data in jwks_data.get("keys", []):
                if key_data.get("kid") == kid:
                    jwk = PyJWK.from_dict(key_data)
                    # Cache the key
                    self._jwks_cache[kid] = (now + self._JWKS_CACHE_TTL, jwk.key)
                    logger.info("Cached JWKS key for kid=%s", kid[:8])
                    return jwk.key

            logger.warning("Key not found in JWKS: kid=%s", kid[:8])
            return None

        except Exception as exc:
            logger.error("Failed to fetch JWKS: %s", exc)
            return None

    def _cache_auth(self, cache_key: str, result: dict, now: float) -> None:
        """Cache auth result with cleanup."""
        self._auth_cache[cache_key] = (now + self._AUTH_CACHE_TTL, result)

        # Cleanup if cache is too large
        if len(self._auth_cache) > self._AUTH_CACHE_MAX_SIZE:
            expired = [k for k, (exp, _) in self._auth_cache.items() if now >= exp]
            for k in expired:
                del self._auth_cache[k]

    async def _send_auth_required(self, scope, send, body: bytes, is_json: bool) -> None:
        """Send 401 with proper MCP error format for JSON requests."""
        www_auth = _www_authenticate_from_scope(scope)

        if is_json and body:
            # Parse request ID for proper JSON-RPC error
            request_id = None
            try:
                parsed = json.loads(body.decode())
                if isinstance(parsed, dict):
                    request_id = parsed.get("id")
            except Exception:
                pass

            mcp_error = {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": "Authentication required. Please connect your account to continue.",
                        }
                    ],
                    "_meta": {"mcp/www_authenticate": [www_auth]},
                    "isError": True,
                },
            }
            response = JSONResponse(
                mcp_error,
                status_code=200,  # MCP uses 200 with error in body
                headers={"WWW-Authenticate": www_auth},
            )
        else:
            response = JSONResponse(
                {"error": "Authentication required"},
                status_code=401,
                headers={"WWW-Authenticate": www_auth},
            )

        await response(scope, _noop_receive, send)

    async def _send_error(self, scope, receive, send, status_code: int, message: str) -> None:
        response = JSONResponse({"error": message}, status_code=status_code)
        await response(scope, receive, send)


def _load_settings() -> Settings:
    return Settings()


def _normalize_uuid(value: str) -> str:
    """Convert 32-char hex to UUID format with dashes."""
    normalized = value.replace("-", "").lower()
    if len(normalized) == 32 and all(ch in "0123456789abcdef" for ch in normalized):
        return (
            f"{normalized[:8]}-{normalized[8:12]}-{normalized[12:16]}-"
            f"{normalized[16:20]}-{normalized[20:]}"
        )
    return value


def _normalize_session_query(scope: dict) -> dict:
    path = scope.get("path", "")
    if "/messages/" not in path:
        return scope
    raw_query = scope.get("query_string", b"")
    if not raw_query:
        return scope
    try:
        params = parse_qs(raw_query.decode(), keep_blank_values=True)
    except UnicodeDecodeError:
        return scope
    if "session_id" not in params or not params["session_id"]:
        return scope
    normalized = [_normalize_uuid(value) for value in params["session_id"]]
    if normalized == params["session_id"]:
        return scope
    params["session_id"] = normalized
    new_scope = dict(scope)
    new_scope["query_string"] = urlencode(params, doseq=True).encode()
    return new_scope


def _normalize_mcp_path(scope: dict) -> dict:
    path = scope.get("path", "")
    if path != "/mcp/":
        return scope
    new_scope = dict(scope)
    new_scope["path"] = "/mcp"
    if "raw_path" in scope:
        new_scope["raw_path"] = b"/mcp"
    return new_scope


def _host_from_scope(scope: dict) -> str:
    host = "mcp.instainstru.com"
    for key, value in scope.get("headers", []):
        if key == b"host":
            host = value.decode()
            break
    return host


def _www_authenticate_from_scope(scope: dict) -> str:
    host = _host_from_scope(scope)
    resource_metadata_url = f"https://{host}/.well-known/oauth-protected-resource"
    return (
        f'Bearer resource_metadata="{resource_metadata_url}", '
        f'error="unauthorized", '
        f'error_description="Authentication required to access this resource"'
    )


async def _read_body(receive) -> bytes:
    body = b""
    more_body = True
    while more_body:
        message = await receive()
        if message.get("type") == "http.disconnect":
            break
        body += message.get("body", b"")
        more_body = message.get("more_body", False)
    return body


def _replay_body(body: bytes):
    sent = False

    async def receive():
        nonlocal sent
        if sent:
            return {"type": "http.request", "body": b"", "more_body": False}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    return receive


async def _noop_receive():
    return {"type": "http.request", "body": b"", "more_body": False}


def create_mcp(settings: Settings | None = None) -> "FastMCP":
    from fastmcp import FastMCP

    from .auth import MCPAuth

    settings = settings or _load_settings()
    _init_sentry(settings)
    auth = MCPAuth(settings)
    client = InstaInstruClient(settings, auth)
    grafana = GrafanaCloudClient(settings)
    sentry_client = SentryClient(settings.sentry_api_token, settings.sentry_org)

    mcp = FastMCP("iNSTAiNSTRU Admin")

    celery.register_tools(mcp, client)
    founding.register_tools(mcp, client)
    instructors.register_tools(mcp, client)
    invites.register_tools(mcp, client)
    operations.register_tools(mcp, client)
    search.register_tools(mcp, client)
    metrics.register_tools(mcp, client)
    services.register_tools(mcp, client)
    observability.register_tools(mcp, grafana)
    sentry.register_tools(mcp, sentry_client)
    sentry_debug.register_tools(mcp)

    return mcp


def _attach_health_route(app: Any) -> None:
    async def health_check(_request):
        return JSONResponse(
            {"status": "ok", "service": "instainstru-mcp", "version": "v3-json-response"}
        )

    app.routes.append(Route("/api/v1/health", health_check, methods=["GET", "HEAD"]))


def create_app(settings: Settings | None = None):
    settings = settings or _load_settings()
    mcp = create_mcp(settings=settings)
    app_instance = mcp.http_app(
        path="/mcp",
        transport="streamable-http",
        stateless_http=True,
        json_response=True,
    )
    _attach_health_route(app_instance)
    attach_oauth_routes(app_instance, settings)

    app_with_auth = DualAuthMiddleware(app_instance, settings)
    if os.getenv("ENABLE_CORS", "false").lower() == "true":
        return CORSMiddleware(
            app_with_auth,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type", "Accept"],
            expose_headers=["*"],
        )
    return app_with_auth


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
