"""FastMCP server entry point for InstaInstru admin tools."""

from __future__ import annotations

import json
import logging
import os
import secrets
from typing import TYPE_CHECKING, Any, cast

import jwt as pyjwt
from cryptography.hazmat.primitives import serialization
from jwt import PyJWK
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
from starlette.routing import Route

from .client import InstaInstruClient
from .config import Settings
from .oauth.crypto import build_jwks, normalize_pem
from .oauth.endpoints import attach_oauth_routes
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


class DualAuthMiddleware:
    """ASGI middleware supporting simple Bearer tokens and self-issued JWTs."""

    EXEMPT_PATHS = {
        "/api/v1/health",
        "/.well-known/oauth-protected-resource",
        "/.well-known/oauth-authorization-server",
        "/.well-known/openid-configuration",
        "/.well-known/jwks.json",
        "/oauth2/register",
        "/oauth2/authorize",
        "/oauth2/callback",
        "/oauth2/token",
    }

    EXEMPT_PATH_PREFIXES = ("/.well-known/oauth-protected-resource/",)

    def __init__(self, app: Any, settings: Settings) -> None:
        self.app = app
        self.settings = settings
        self.simple_token = os.environ.get("INSTAINSTRU_MCP_API_SERVICE_TOKEN")

        self.oauth_issuer = settings.oauth_issuer
        self.jwt_key_id = settings.jwt_key_id
        self.jwt_signing_key = None
        self.jwt_public_key = None

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
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("Failed to load JWT public key: %s", exc)

        if not self.simple_token and not self.jwt_signing_key:
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
        content_type = headers.get(b"content-type", b"").decode()
        method = scope.get("method", "")
        is_json = "application/json" in content_type

        body = b""
        receive_for_app = receive
        parsed_body: dict | None = None
        if method in {"POST", "PUT", "PATCH"}:
            body = await _read_body(receive)
            receive_for_app = _replay_body(body)
            if is_json:
                parsed_body = _parse_json_body(body)

        if not auth_header.startswith("Bearer "):
            await self._send_auth_required(scope, send, body, parsed_body, is_json)
            return

        token = auth_header[7:]
        host = _host_from_scope(scope)
        issuer = (self.oauth_issuer or f"https://{host}").rstrip("/")
        auth_result = await self._authenticate(token, issuer)

        if auth_result is None:
            await self._send_auth_required(scope, send, body, parsed_body, is_json)
            return

        # Check email allowlist for JWT tokens
        if auth_result.get("method") == "jwt":
            claims = auth_result.get("claims", {})
            email = (
                claims.get("email") or claims.get("preferred_username") or claims.get("sub", "")
            ).lower()
            logger.info("Checking email allowlist for: %s", email)
            if not email or email not in ALLOWED_EMAILS:
                logger.warning(
                    "Access denied for email: %s (claims: %s)",
                    email,
                    list(claims.keys()),
                )
                await self._send_error(scope, receive, send, 403, "Access denied")
                return

        scope["auth"] = auth_result

        should_inject_tools = (
            method == "POST"
            and is_json
            and isinstance(parsed_body, dict)
            and parsed_body.get("method") == "tools/list"
        )
        if should_inject_tools:
            await self._call_with_tool_injection(scope, receive_for_app, send)
            return

        await self.app(scope, receive_for_app, send)

    async def _authenticate(self, token: str, issuer: str) -> dict | None:
        # Try simple token first
        if self.simple_token and secrets.compare_digest(token, self.simple_token):
            logger.debug("Authenticated via simple Bearer token")
            return {"method": "simple_token"}

        # Try self-issued JWT
        if self.jwt_signing_key:
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
                logger.info("Authenticated via JWT: %s", claims.get("email", claims.get("sub")))
                return {"method": "jwt", "claims": claims}
            except pyjwt.InvalidTokenError as exc:
                logger.info("JWT validation failed: %s", exc)

        return None

    async def _send_401(self, scope, receive, send, message: str):
        """Send 401 with WWW-Authenticate header per RFC 9728."""
        headers = {"WWW-Authenticate": _www_authenticate_from_scope(scope)}
        response = JSONResponse({"error": message}, status_code=401, headers=headers)
        await response(scope, receive, send)

    async def _send_error(self, scope, receive, send, status_code: int, message: str):
        response = JSONResponse({"error": message}, status_code=status_code)
        await response(scope, receive, send)

    async def _send_auth_required(
        self,
        scope,
        send,
        body: bytes,
        parsed_body: dict | None,
        is_json: bool,
    ) -> None:
        www_authenticate = _www_authenticate_from_scope(scope)
        method = scope.get("method", "")
        path = scope.get("path", "")

        if method == "POST" and is_json:
            response = _build_mcp_auth_error(body, parsed_body, www_authenticate)
            await response(scope, _noop_receive, send)
            return

        message = "Missing or invalid Authorization header"
        if method == "GET" and "/sse" in path:
            message = "Unauthorized"
        response = JSONResponse(
            {"error": message},
            status_code=401,
            headers={"WWW-Authenticate": www_authenticate},
        )
        await response(scope, _noop_receive, send)

    async def _call_with_tool_injection(self, scope, receive, send) -> None:
        start_message: dict | None = None
        body_chunks: list[bytes] = []

        async def send_wrapper(message):
            nonlocal start_message
            if message["type"] == "http.response.start":
                start_message = message
                return
            if message["type"] == "http.response.body":
                body_chunks.append(message.get("body", b""))
                if message.get("more_body", False):
                    return
                body = b"".join(body_chunks)
                new_body = _inject_security_schemes_body(body)
                headers = _replace_content_length(
                    (start_message or {}).get("headers", []),
                    len(new_body),
                )
                await send(
                    {
                        "type": "http.response.start",
                        "status": (start_message or {}).get("status", 200),
                        "headers": headers,
                    }
                )
                await send(
                    {
                        "type": "http.response.body",
                        "body": new_body,
                        "more_body": False,
                    }
                )

        await self.app(scope, receive, send_wrapper)


def _load_settings() -> Settings:
    token = os.environ.get("INSTAINSTRU_MCP_API_SERVICE_TOKEN", "")
    return Settings(api_service_token=token)


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


def _parse_json_body(body: bytes) -> dict | None:
    try:
        data = json.loads(body.decode())
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _build_mcp_auth_error(
    body: bytes, parsed_body: dict | None, www_authenticate: str
) -> JSONResponse:
    request_id = None
    data = parsed_body or _parse_json_body(body)
    if isinstance(data, dict):
        request_id = data.get("id")
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
            "_meta": {"mcp/www_authenticate": [www_authenticate]},
            "isError": True,
        },
    }
    return JSONResponse(
        mcp_error,
        status_code=200,
        headers={"WWW-Authenticate": www_authenticate},
    )


def _inject_security_schemes(payload: dict) -> dict:
    result = payload.get("result")
    if not isinstance(result, dict):
        return payload
    tools = result.get("tools")
    if not isinstance(tools, list):
        return payload
    for tool in tools:
        if isinstance(tool, dict):
            tool["securitySchemes"] = [{"type": "oauth2", "scopes": ["openid", "profile", "email"]}]
    return payload


def _inject_security_schemes_body(body: bytes) -> bytes:
    try:
        payload = json.loads(body.decode())
    except Exception:
        return body
    if not isinstance(payload, dict):
        return body
    payload = _inject_security_schemes(payload)
    return json.dumps(payload).encode()


def _replace_content_length(headers: list[tuple[bytes, bytes]], length: int):
    filtered = [(k, v) for (k, v) in headers if k.lower() != b"content-length"]
    filtered.append((b"content-length", str(length).encode()))
    return filtered


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


def create_app(settings: Settings | None = None):
    settings = settings or _load_settings()
    mcp = create_mcp(settings=settings)
    app_instance = cast(Any, mcp).http_app(transport="sse")
    _attach_health_route(app_instance)
    attach_oauth_routes(app_instance, settings)
    app_with_auth = DualAuthMiddleware(app_instance, settings)
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
