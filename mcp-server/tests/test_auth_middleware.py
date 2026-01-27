"""Tests for dual auth middleware (simple Bearer + self-issued JWT)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from instainstru_mcp.config import Settings
from instainstru_mcp.oauth.crypto import sign_jwt
from instainstru_mcp.server import DualAuthMiddleware, create_app
from starlette.applications import Starlette
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient


def _generate_test_keys() -> tuple[str, str]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = (
        private_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    return private_pem, public_pem


@pytest.fixture(scope="session")
def jwt_keys() -> dict[str, str]:
    private_pem, public_pem = _generate_test_keys()
    return {"private": private_pem, "public": public_pem}


def get_test_settings(
    *,
    jwt_keys: dict[str, str] | None = None,
    issuer: str | None = "https://mcp.instainstru.com",
) -> Settings:
    return Settings(
        api_base_url="https://api.test.com",
        api_service_token="backend-token",
        jwt_private_key=(jwt_keys or {}).get("private"),
        jwt_public_key=(jwt_keys or {}).get("public"),
        jwt_key_id="test-key",
        oauth_issuer=issuer,
    )


def create_test_app(
    *,
    simple_token: str | None = None,
    settings: Settings | None = None,
) -> TestClient:
    with pytest.MonkeyPatch().context() as mp:
        mp.setenv("INSTAINSTRU_MCP_API_SERVICE_TOKEN", simple_token or "")

        async def protected_endpoint(request):
            auth_info = request.scope.get("auth", {})
            return PlainTextResponse(f"OK: {auth_info.get('method', 'unknown')}")

        async def health_endpoint(_request):
            return PlainTextResponse("healthy")

        routes = [
            Route("/sse", protected_endpoint, methods=["GET", "POST"]),
            Route("/messages/", protected_endpoint, methods=["POST"]),
            Route("/api/v1/health", health_endpoint),
        ]

        app = Starlette(routes=routes)
        wrapped = DualAuthMiddleware(app, settings or get_test_settings())
        return TestClient(wrapped, raise_server_exceptions=False)


# --- Simple Token Tests ---


class TestSimpleTokenAuth:
    def test_valid_simple_token(self):
        client = create_test_app(simple_token="test-token-123")
        response = client.get("/sse", headers={"Authorization": "Bearer test-token-123"})
        assert response.status_code == 200
        assert "simple_token" in response.text

    def test_invalid_simple_token(self):
        client = create_test_app(simple_token="test-token-123")
        response = client.get("/sse", headers={"Authorization": "Bearer wrong-token"})
        assert response.status_code == 401

    def test_missing_auth_header(self):
        client = create_test_app(simple_token="test-token-123")
        response = client.get("/sse")
        assert response.status_code == 401
        assert response.json()["error"] in {
            "Missing or invalid Authorization header",
            "Unauthorized",
            "Authentication required",
        }

    def test_malformed_auth_header(self):
        client = create_test_app(simple_token="test-token-123")
        response = client.get("/sse", headers={"Authorization": "Basic abc123"})
        assert response.status_code == 401


# --- JWT Token Tests ---


class TestJWTAuth:
    def _mint_token(self, jwt_keys: dict[str, str], issuer: str, email: str) -> str:
        now = datetime.now(timezone.utc)
        payload = {
            "iss": issuer,
            "sub": "user123",
            "aud": issuer,
            "email": email,
            "scope": "openid profile email",
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(hours=1)).timestamp()),
        }
        private_key = serialization.load_pem_private_key(
            jwt_keys["private"].encode(), password=None
        )
        return sign_jwt(payload, private_key, "test-key")

    def test_valid_jwt_token(self, jwt_keys: dict[str, str]):
        issuer = "https://mcp.instainstru.com"
        settings = get_test_settings(jwt_keys=jwt_keys, issuer=issuer)
        client = create_test_app(settings=settings)
        token = self._mint_token(jwt_keys, issuer, "admin@instainstru.com")

        response = client.get("/sse", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        assert "jwt" in response.text

    def test_jwt_invalid_issuer(self, jwt_keys: dict[str, str]):
        settings = get_test_settings(jwt_keys=jwt_keys, issuer="https://mcp.instainstru.com")
        client = create_test_app(settings=settings)
        token = self._mint_token(jwt_keys, "https://wrong-issuer.example", "admin@instainstru.com")

        response = client.get("/sse", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401

    def test_jwt_invalid_audience(self, jwt_keys: dict[str, str]):
        issuer = "https://mcp.instainstru.com"
        settings = get_test_settings(jwt_keys=jwt_keys, issuer=issuer)
        client = create_test_app(settings=settings)

        now = datetime.now(timezone.utc)
        payload = {
            "iss": issuer,
            "sub": "user123",
            "aud": "https://other.example",
            "email": "admin@instainstru.com",
            "scope": "openid profile email",
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(hours=1)).timestamp()),
        }
        private_key = serialization.load_pem_private_key(
            jwt_keys["private"].encode(), password=None
        )
        token = sign_jwt(payload, private_key, "test-key")

        response = client.get("/sse", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401

    def test_jwt_email_not_allowlisted(self, jwt_keys: dict[str, str]):
        issuer = "https://mcp.instainstru.com"
        settings = get_test_settings(jwt_keys=jwt_keys, issuer=issuer)
        client = create_test_app(settings=settings)
        token = self._mint_token(jwt_keys, issuer, "not-allowed@example.com")

        response = client.get("/sse", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 403
        assert response.json()["error"] == "Access denied"


# --- Dual Auth Tests ---


class TestDualAuth:
    def test_simple_token_when_both_configured(self, jwt_keys: dict[str, str]):
        settings = get_test_settings(jwt_keys=jwt_keys)
        client = create_test_app(simple_token="test-token-123", settings=settings)

        response = client.get("/sse", headers={"Authorization": "Bearer test-token-123"})
        assert response.status_code == 200
        assert "simple_token" in response.text


# --- Health Endpoint Tests ---


class TestHealthEndpoint:
    def test_health_no_auth(self, jwt_keys: dict[str, str]):
        settings = get_test_settings(jwt_keys=jwt_keys)
        client = create_test_app(settings=settings)
        response = client.get("/api/v1/health")
        assert response.status_code == 200


# --- WWW-Authenticate Header Tests ---


class TestWWWAuthenticateHeader:
    def test_401_includes_resource_metadata_header(self):
        client = create_test_app(simple_token="test-token-123")
        response = client.get("/sse")
        assert response.status_code == 401
        www_authenticate = response.headers.get("WWW-Authenticate", "")
        assert (
            'resource_metadata="https://testserver/.well-known/oauth-protected-resource"'
            in www_authenticate
        )
        assert 'error="unauthorized"' in www_authenticate
        assert "Authentication required" in www_authenticate


class TestCORSHeaders:
    def test_sse_response_includes_cors_headers(self, jwt_keys: dict[str, str]):
        settings = get_test_settings(jwt_keys=jwt_keys)
        with pytest.MonkeyPatch().context() as mp:
            mp.setenv("ENABLE_CORS", "true")
            app = create_app(settings)
            client = TestClient(app, raise_server_exceptions=False)

            response = client.get(
                "/api/v1/health",
                headers={"Origin": "https://example.com"},
            )
        assert response.status_code == 200
        assert response.headers.get("Access-Control-Allow-Origin") == "*"


class TestChatGPTOAuthSupport:
    def test_post_returns_mcp_error_with_www_authenticate_meta(self):
        client = create_test_app()

        response = client.post(
            "/sse",
            json={"jsonrpc": "2.0", "method": "tools/call", "id": 1},
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data.get("result", {}).get("isError") is True
        assert "mcp/www_authenticate" in data.get("result", {}).get("_meta", {})

    def test_initialize_allows_unauthenticated(self):
        client = create_test_app()

        response = client.post(
            "/sse",
            json={"jsonrpc": "2.0", "method": "initialize", "id": 1},
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 200


class TestMcpRoute:
    def test_initialize_on_mcp_root(self, jwt_keys: dict[str, str]):
        settings = get_test_settings(jwt_keys=jwt_keys)
        app = create_app(settings)
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "method": "initialize",
                    "id": 1,
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": "tests", "version": "0.0.0"},
                    },
                },
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
            )

            assert response.status_code == 200
            payload = response.json()
            assert payload.get("jsonrpc") == "2.0"
            assert "result" in payload

    def test_double_mcp_path_returns_404(self, jwt_keys: dict[str, str]):
        settings = get_test_settings(jwt_keys=jwt_keys)
        app = create_app(settings)
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.post(
                "/mcp/mcp",
                json={
                    "jsonrpc": "2.0",
                    "method": "initialize",
                    "id": 1,
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": "tests", "version": "0.0.0"},
                    },
                },
                headers={"Content-Type": "application/json"},
            )

            assert response.status_code == 404


class TestGetAppSingleton:
    def test_get_app_returns_singleton(self):
        from instainstru_mcp import server as server_module

        server_module._app = None
        sentinel = object()

        with pytest.MonkeyPatch().context() as mp:
            mp.setattr(server_module, "create_app", lambda *args, **kwargs: sentinel)
            app_first = server_module.get_app()
            app_second = server_module.get_app()

        assert app_first is sentinel
        assert app_second is sentinel
        server_module._app = None


class TestSessionIdNormalization:
    def test_messages_session_id_normalized(self, jwt_keys: dict[str, str]):
        async def messages(request):
            return JSONResponse({"session_id": request.query_params.get("session_id")})

        app = Starlette(routes=[Route("/messages/", messages, methods=["POST"])])
        settings = get_test_settings(jwt_keys=jwt_keys)

        with pytest.MonkeyPatch().context() as mp:
            mp.setenv("INSTAINSTRU_MCP_API_SERVICE_TOKEN", "test-token")
            wrapped = DualAuthMiddleware(app, settings)
            client = TestClient(wrapped, raise_server_exceptions=False)
            response = client.post(
                "/messages/?session_id=21920ee01ade40bb9477016c8719f49b",
                headers={"Authorization": "Bearer test-token"},
            )

        assert response.status_code == 200
        assert response.json()["session_id"] == "21920ee0-1ade-40bb-9477-016c8719f49b"
