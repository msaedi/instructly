"""OAuth 2.0 endpoints for self-issued authorization server."""

from __future__ import annotations

import json
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import parse_qs, parse_qsl, urlencode, urlparse, urlunparse

import jwt as pyjwt
from jwt import PyJWK
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse
from starlette.routing import Route

from ..config import Settings
from .crypto import build_jwks, generate_code, load_rsa_keys, sign_jwt, verify_pkce
from .models import AuthorizationCode, OAuthSession, RefreshToken, RegisteredClient
from .storage import InMemoryStorage, OAuthStorage
from .workos_client import WorkOSClient

logger = logging.getLogger(__name__)


def attach_oauth_routes(
    app: Any,
    settings: Settings,
    storage: OAuthStorage | None = None,
) -> None:
    storage = storage or InMemoryStorage()

    private_key = None
    public_key = None
    jwks = None
    if settings.jwt_private_key and settings.jwt_public_key:
        try:
            private_key, public_key = load_rsa_keys(
                settings.jwt_private_key,
                settings.jwt_public_key,
            )
            jwks = build_jwks(public_key, settings.jwt_key_id)
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("Failed to load JWT keys: %s", exc)
            private_key = None
            public_key = None
            jwks = None

    workos_client = None
    if settings.workos_domain and settings.workos_client_id and settings.workos_client_secret:
        workos_client = WorkOSClient(
            settings.workos_domain,
            settings.workos_client_id,
            settings.workos_client_secret,
        )

    def _base_url(request: Request) -> str:
        if settings.oauth_issuer:
            return settings.oauth_issuer.rstrip("/")
        host = request.headers.get("host", "mcp.instainstru.com")
        if host.startswith("http://") or host.startswith("https://"):
            return host.rstrip("/")
        return f"https://{host}".rstrip("/")

    def _ensure_workos() -> WorkOSClient | None:
        if not workos_client:
            return None
        return workos_client

    def _validate_redirect_uri(uri: str) -> bool:
        parsed = urlparse(uri)
        if not parsed.scheme or not parsed.netloc:
            return False
        if parsed.scheme == "https":
            return True
        if parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1"}:
            return True
        return False

    def _redirect_with_params(url: str, params: dict[str, str | None]) -> str:
        parsed = urlparse(url)
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        for key, value in params.items():
            if value is not None:
                query[key] = value
        return urlunparse(parsed._replace(query=urlencode(query)))

    async def _parse_request_data(request: Request) -> dict[str, str]:
        content_type = request.headers.get("content-type", "")
        body = await request.body()
        if "application/json" in content_type:
            try:
                data = json.loads(body.decode()) if body else {}
            except json.JSONDecodeError:
                return {}
            if isinstance(data, dict):
                return {str(k): str(v) for k, v in data.items()}
            return {}
        parsed = parse_qs(body.decode(), keep_blank_values=True)
        return {key: value[0] for key, value in parsed.items() if value}

    def _json_error(status: int, error: str, description: str | None = None) -> JSONResponse:
        payload: dict[str, str] = {"error": error}
        if description:
            payload["error_description"] = description
        return JSONResponse(payload, status_code=status)

    async def oauth_authorization_server(request: Request):
        issuer = _base_url(request)
        return JSONResponse(
            {
                "issuer": issuer,
                "authorization_endpoint": f"{issuer}/oauth2/authorize",
                "token_endpoint": f"{issuer}/oauth2/token",
                "registration_endpoint": f"{issuer}/oauth2/register",
                "jwks_uri": f"{issuer}/.well-known/jwks.json",
                "response_types_supported": ["code"],
                "grant_types_supported": ["authorization_code", "refresh_token"],
                "token_endpoint_auth_methods_supported": ["none"],
                "code_challenge_methods_supported": ["S256"],
                "scopes_supported": ["openid", "profile", "email"],
            }
        )

    async def openid_configuration(request: Request):
        issuer = _base_url(request)
        return JSONResponse(
            {
                "issuer": issuer,
                "authorization_endpoint": f"{issuer}/oauth2/authorize",
                "token_endpoint": f"{issuer}/oauth2/token",
                "userinfo_endpoint": f"{issuer}/oauth2/userinfo",
                "jwks_uri": f"{issuer}/.well-known/jwks.json",
                "registration_endpoint": f"{issuer}/oauth2/register",
                "scopes_supported": ["openid", "profile", "email"],
                "response_types_supported": ["code"],
                "grant_types_supported": ["authorization_code", "refresh_token"],
                "subject_types_supported": ["public"],
                "id_token_signing_alg_values_supported": ["RS256"],
                "token_endpoint_auth_methods_supported": ["none"],
                "code_challenge_methods_supported": ["S256"],
            }
        )

    async def oauth_protected_resource(request: Request):
        issuer = _base_url(request)
        return JSONResponse({"resource": f"{issuer}/sse", "authorization_servers": [issuer]})

    async def jwks_endpoint(_request: Request):
        if not jwks:
            return JSONResponse({"error": "JWKS not configured"}, status_code=503)
        return JSONResponse(jwks)

    async def userinfo(request: Request):
        if not public_key:
            return JSONResponse({"error": "JWT verification not configured"}, status_code=503)

        auth_header = request.headers.get("authorization", "")
        if not auth_header.startswith("Bearer "):
            return _json_error(401, "invalid_request", "Missing bearer token")

        token = auth_header[7:].strip()
        if not token:
            return _json_error(401, "invalid_request", "Missing bearer token")

        issuer = _base_url(request)
        try:
            claims = pyjwt.decode(
                token,
                public_key,
                algorithms=["RS256"],
                issuer=issuer,
                audience=issuer,
            )
        except pyjwt.InvalidTokenError:
            return _json_error(401, "invalid_token", "Token invalid")

        return JSONResponse(
            {
                "sub": claims.get("sub"),
                "email": claims.get("email"),
                "scope": claims.get("scope"),
                "name": claims.get("name"),
            }
        )

    async def register_client(request: Request):
        data: dict[str, Any] = {}
        content_type = request.headers.get("content-type", "")
        if "application/json" in content_type:
            try:
                payload = await request.json()
                if isinstance(payload, dict):
                    data = payload
            except Exception:
                data = {}
        else:
            data = await _parse_request_data(request)

        redirect_uris_raw = data.get("redirect_uris")
        client_name = data.get("client_name") or "MCP Client"

        redirect_uris: list[str]
        if isinstance(redirect_uris_raw, list):
            redirect_uris = redirect_uris_raw
        elif isinstance(redirect_uris_raw, str):
            try:
                parsed = json.loads(redirect_uris_raw)
                redirect_uris = parsed if isinstance(parsed, list) else []
            except json.JSONDecodeError:
                redirect_uris = []
        else:
            redirect_uris = []

        if not redirect_uris or not all(isinstance(uri, str) for uri in redirect_uris):
            return _json_error(400, "invalid_request", "redirect_uris required")

        for uri in redirect_uris:
            if not _validate_redirect_uri(uri):
                return _json_error(400, "invalid_redirect_uri", "redirect_uris must be HTTPS")

        client_id = f"mcp_client_{generate_code(12)}"
        client = RegisteredClient(
            client_id=client_id,
            client_name=client_name,
            redirect_uris=redirect_uris,
        )
        storage.save_client(client)
        return JSONResponse(
            {
                "client_id": client.client_id,
                "client_name": client.client_name,
                "redirect_uris": client.redirect_uris,
                "token_endpoint_auth_method": client.token_endpoint_auth_method,
                "grant_types": client.grant_types,
                "response_types": client.response_types,
            },
            status_code=201,
        )

    async def authorize(request: Request):
        params = request.query_params
        client_id = params.get("client_id")
        redirect_uri = params.get("redirect_uri")
        response_type = params.get("response_type")
        code_challenge = params.get("code_challenge")
        code_challenge_method = params.get("code_challenge_method")
        state = params.get("state", "")
        scope = params.get("scope", "")
        resource = params.get("resource")

        if not client_id or not redirect_uri:
            return _json_error(400, "invalid_request", "client_id and redirect_uri required")

        client = storage.get_client(client_id)
        if not client:
            return _json_error(400, "unauthorized_client", "client not registered")

        if response_type != "code":
            return _json_error(400, "unsupported_response_type")

        if not code_challenge or code_challenge_method != "S256":
            return _json_error(400, "invalid_request", "PKCE S256 required")

        if not any(secrets.compare_digest(redirect_uri, uri) for uri in client.redirect_uris):
            return _json_error(400, "invalid_redirect_uri")

        workos = _ensure_workos()
        if not workos:
            return JSONResponse({"error": "WorkOS not configured"}, status_code=503)

        session_id = generate_code(16)
        session = OAuthSession(
            session_id=session_id,
            client_id=client_id,
            redirect_uri=redirect_uri,
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method,
            original_state=state,
            resource=resource,
            scope=scope,
        )
        storage.save_session(session)

        callback_url = f"{_base_url(request)}/oauth2/callback"
        redirect_target = workos.get_authorization_url(callback_url, session_id)
        return RedirectResponse(url=redirect_target, status_code=302)

    async def callback(request: Request):
        params = request.query_params
        workos_code = params.get("code")
        state = params.get("state")

        if not workos_code or not state:
            return _json_error(400, "invalid_request", "code and state required")

        session = storage.get_session(state)
        if not session:
            return _json_error(400, "invalid_request", "invalid session")

        workos = _ensure_workos()
        if not workos:
            return JSONResponse({"error": "WorkOS not configured"}, status_code=503)

        callback_url = f"{_base_url(request)}/oauth2/callback"
        try:
            token_response = await workos.exchange_code(workos_code, callback_url)
        except Exception as exc:
            logger.error("WorkOS token exchange failed: %s", exc)
            return _json_error(502, "invalid_grant", "WorkOS token exchange failed")

        id_token = token_response.get("id_token")
        access_token = token_response.get("access_token")

        workos_claims = None
        if id_token:
            try:
                jwks_data = await workos.get_jwks()
                header = pyjwt.get_unverified_header(id_token)
                kid = header.get("kid")
                key_dict = None
                for jwk in jwks_data.get("keys", []):
                    if secrets.compare_digest(jwk.get("kid", ""), kid or ""):
                        key_dict = jwk
                        break
                if not key_dict:
                    raise ValueError("No matching JWK")
                signing_key = PyJWK.from_dict(key_dict).key
                workos_claims = pyjwt.decode(
                    id_token,
                    signing_key,
                    algorithms=["RS256"],
                    issuer=workos.base_url,
                    audience=workos.client_id,
                )
            except Exception as exc:
                logger.error("WorkOS token validation failed: %s", exc)
                return _json_error(401, "invalid_token", "WorkOS token invalid")

        user_id = None
        user_email = None
        if workos_claims:
            user_id = workos_claims.get("sub")
            user_email = workos_claims.get("email")

        if (not user_email or not user_id) and access_token:
            try:
                userinfo = await workos.get_userinfo(access_token)
            except Exception as exc:
                logger.error("WorkOS userinfo failed: %s", exc)
                userinfo = {}
            if not user_id:
                user_id = userinfo.get("sub") or userinfo.get("id")
            if not user_email:
                user_email = userinfo.get("email")

        if not user_id or not user_email:
            return _json_error(401, "invalid_token", "Missing user identity")

        auth_code = generate_code(32)
        storage.save_auth_code(
            AuthorizationCode(
                code=auth_code,
                user_id=user_id,
                user_email=user_email,
                client_id=session.client_id,
                redirect_uri=session.redirect_uri,
                code_challenge=session.code_challenge,
                resource=session.resource,
                scope=session.scope,
            )
        )
        storage.delete_session(state)

        redirect_target = _redirect_with_params(
            session.redirect_uri,
            {"code": auth_code, "state": session.original_state},
        )
        return RedirectResponse(url=redirect_target, status_code=302)

    async def token(request: Request):
        if not private_key:
            return JSONResponse({"error": "JWT signing not configured"}, status_code=503)

        data = await _parse_request_data(request)
        grant_type = data.get("grant_type")

        issuer = _base_url(request)
        audience = issuer

        if grant_type == "authorization_code":
            code = data.get("code")
            redirect_uri = data.get("redirect_uri")
            code_verifier = data.get("code_verifier")

            if not code or not redirect_uri or not code_verifier:
                return _json_error(400, "invalid_request")

            auth_code = storage.get_auth_code(code)
            if not auth_code:
                return _json_error(400, "invalid_grant", "authorization code invalid")

            if not secrets.compare_digest(redirect_uri, auth_code.redirect_uri):
                storage.delete_auth_code(code)
                return _json_error(400, "invalid_grant", "redirect_uri mismatch")

            try:
                pkce_valid = verify_pkce(code_verifier, auth_code.code_challenge)
            except ValueError:
                storage.delete_auth_code(code)
                return _json_error(400, "invalid_request", "PKCE method unsupported")

            if not pkce_valid:
                storage.delete_auth_code(code)
                return _json_error(400, "invalid_grant", "PKCE verification failed")

            storage.delete_auth_code(code)

            now = datetime.now(timezone.utc)
            payload = {
                "iss": issuer,
                "sub": auth_code.user_id,
                "aud": audience,
                "email": auth_code.user_email,
                "scope": auth_code.scope,
                "iat": int(now.timestamp()),
                "exp": int((now + timedelta(hours=1)).timestamp()),
                "jti": generate_code(12),
            }
            access_token = sign_jwt(payload, private_key, settings.jwt_key_id)

            refresh_token_value = generate_code(32)
            storage.save_refresh_token(
                RefreshToken(
                    token=refresh_token_value,
                    user_id=auth_code.user_id,
                    user_email=auth_code.user_email,
                    client_id=auth_code.client_id,
                    scope=auth_code.scope,
                )
            )

            return JSONResponse(
                {
                    "access_token": access_token,
                    "token_type": "Bearer",
                    "expires_in": 3600,
                    "refresh_token": refresh_token_value,
                }
            )

        if grant_type == "refresh_token":
            refresh_token_param = data.get("refresh_token")
            if not refresh_token_param:
                return _json_error(400, "invalid_request")

            refresh_token = storage.get_refresh_token(refresh_token_param)
            if not refresh_token:
                return _json_error(400, "invalid_grant", "refresh token invalid")

            now = datetime.now(timezone.utc)
            payload = {
                "iss": issuer,
                "sub": refresh_token.user_id,
                "aud": audience,
                "email": refresh_token.user_email,
                "scope": refresh_token.scope,
                "iat": int(now.timestamp()),
                "exp": int((now + timedelta(hours=1)).timestamp()),
                "jti": generate_code(12),
            }
            access_token = sign_jwt(payload, private_key, settings.jwt_key_id)

            return JSONResponse(
                {
                    "access_token": access_token,
                    "token_type": "Bearer",
                    "expires_in": 3600,
                    "refresh_token": refresh_token_param,
                }
            )

        return _json_error(400, "unsupported_grant_type")

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
    app.routes.append(Route("/oauth2/register", register_client, methods=["POST"]))
    app.routes.append(Route("/oauth2/authorize", authorize, methods=["GET"]))
    app.routes.append(Route("/oauth2/callback", callback, methods=["GET"]))
    app.routes.append(Route("/oauth2/token", token, methods=["POST"]))
