"""Tests for WorkOS auth middleware (simple Bearer + WorkOS JWT)."""

from unittest.mock import AsyncMock, MagicMock, patch

import jwt as pyjwt
import pytest
from instainstru_mcp.config import Settings
from instainstru_mcp.server import WorkOSAuthMiddleware, create_app
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

# --- Helpers ---


def get_test_settings(workos_domain: str | None = "test.authkit.app") -> Settings:
    return Settings(
        api_base_url="https://api.test.com",
        api_service_token="backend-token",
        workos_domain=workos_domain or "",
        workos_client_id="client_test123",
    )


def create_test_app(
    simple_token: str | None = None, workos_domain: str | None = "test.authkit.app"
) -> TestClient:
    env = {}
    if simple_token is not None:
        env["INSTAINSTRU_MCP_API_SERVICE_TOKEN"] = simple_token

    with patch.dict("os.environ", env, clear=True):

        async def protected_endpoint(request):
            auth_info = request.scope.get("auth", {})
            return PlainTextResponse(f"OK: {auth_info.get('method', 'unknown')}")

        async def health_endpoint(request):
            return PlainTextResponse("healthy")

        routes = [
            Route("/sse", protected_endpoint),
            Route("/messages/", protected_endpoint, methods=["POST"]),
            Route("/api/v1/health", health_endpoint),
        ]

        app = Starlette(routes=routes)
        settings = get_test_settings(workos_domain=workos_domain)
        wrapped = WorkOSAuthMiddleware(app, settings)
        return TestClient(wrapped, raise_server_exceptions=False)


# --- Fixtures ---


@pytest.fixture
def mock_jwks_client():
    """Mock PyJWKClient for WorkOS tests."""
    with patch("instainstru_mcp.server.PyJWKClient") as mock_class:
        mock_client = MagicMock()
        mock_class.return_value = mock_client
        yield mock_client


# --- Simple Token Tests ---


class TestSimpleTokenAuth:
    """Tests for simple Bearer token authentication."""

    def test_valid_simple_token(self):
        client = create_test_app(simple_token="test-token-123", workos_domain="")
        response = client.get("/sse", headers={"Authorization": "Bearer test-token-123"})
        assert response.status_code == 200
        assert "simple_token" in response.text

    def test_invalid_simple_token(self):
        client = create_test_app(simple_token="test-token-123", workos_domain="")
        response = client.get("/sse", headers={"Authorization": "Bearer wrong-token"})
        assert response.status_code == 401

    def test_missing_auth_header(self):
        client = create_test_app(simple_token="test-token-123", workos_domain="")
        response = client.get("/sse")
        assert response.status_code == 401
        assert "Missing" in response.json()["error"]

    def test_malformed_auth_header(self):
        client = create_test_app(simple_token="test-token-123", workos_domain="")
        response = client.get("/sse", headers={"Authorization": "Basic abc123"})
        assert response.status_code == 401

    def test_bearer_case_sensitive(self):
        client = create_test_app(simple_token="test-token-123", workos_domain="")
        response = client.get("/sse", headers={"Authorization": "bearer test-token-123"})
        assert response.status_code == 401


# --- WorkOS Token Tests ---


class TestWorkOSTokenAuth:
    """Tests for WorkOS JWT authentication."""

    def test_valid_workos_token(self, mock_jwks_client):
        mock_key = MagicMock()
        mock_key.key = "test-key"
        mock_jwks_client.get_signing_key_from_jwt.return_value = mock_key

        with patch("instainstru_mcp.server.pyjwt.decode") as mock_decode:
            mock_decode.return_value = {
                "sub": "user123",
                "email": "admin@instainstru.com",
            }

            client = create_test_app(workos_domain="test.authkit.app")
            response = client.get(
                "/sse",
                headers={"Authorization": "Bearer valid.jwt.token"},
            )
            assert response.status_code == 200
            assert "workos" in response.text

            _, kwargs = mock_decode.call_args
            assert kwargs["issuer"] == "https://test.authkit.app"
            assert kwargs["options"]["verify_aud"] is False

    def test_expired_workos_token(self, mock_jwks_client):
        mock_key = MagicMock()
        mock_key.key = "test-key"
        mock_jwks_client.get_signing_key_from_jwt.return_value = mock_key

        with patch("instainstru_mcp.server.pyjwt.decode") as mock_decode:
            mock_decode.side_effect = pyjwt.ExpiredSignatureError("Token expired")
            client = create_test_app(workos_domain="test.authkit.app")
            response = client.get(
                "/sse",
                headers={"Authorization": "Bearer expired.jwt"},
            )
            assert response.status_code == 401

    def test_wrong_issuer(self, mock_jwks_client):
        mock_key = MagicMock()
        mock_key.key = "test-key"
        mock_jwks_client.get_signing_key_from_jwt.return_value = mock_key

        with patch("instainstru_mcp.server.pyjwt.decode") as mock_decode:
            mock_decode.side_effect = pyjwt.InvalidIssuerError("Invalid issuer")
            client = create_test_app(workos_domain="test.authkit.app")
            response = client.get(
                "/sse",
                headers={"Authorization": "Bearer wrong-issuer.jwt"},
            )
            assert response.status_code == 401

    def test_invalid_workos_token(self, mock_jwks_client):
        mock_key = MagicMock()
        mock_key.key = "test-key"
        mock_jwks_client.get_signing_key_from_jwt.return_value = mock_key

        with patch("instainstru_mcp.server.pyjwt.decode") as mock_decode:
            mock_decode.side_effect = pyjwt.InvalidTokenError("Invalid token")
            client = create_test_app(workos_domain="test.authkit.app")
            response = client.get(
                "/sse",
                headers={"Authorization": "Bearer invalid.jwt"},
            )
            assert response.status_code == 401

    def test_email_not_in_allowlist_returns_403(self, mock_jwks_client):
        mock_key = MagicMock()
        mock_key.key = "test-key"
        mock_jwks_client.get_signing_key_from_jwt.return_value = mock_key

        with patch("instainstru_mcp.server.pyjwt.decode") as mock_decode:
            mock_decode.return_value = {
                "sub": "user123",
                "email": "not-allowed@example.com",
            }
            client = create_test_app(workos_domain="test.authkit.app")
            response = client.get(
                "/sse",
                headers={"Authorization": "Bearer valid.jwt.token"},
            )
            assert response.status_code == 403
            assert response.json()["error"] == "Access denied"

    def test_email_in_allowlist_returns_200(self, mock_jwks_client):
        mock_key = MagicMock()
        mock_key.key = "test-key"
        mock_jwks_client.get_signing_key_from_jwt.return_value = mock_key

        with patch("instainstru_mcp.server.pyjwt.decode") as mock_decode:
            mock_decode.return_value = {
                "sub": "user123",
                "email": "mehdi@instainstru.com",
            }
            client = create_test_app(workos_domain="test.authkit.app")
            response = client.get(
                "/sse",
                headers={"Authorization": "Bearer valid.jwt.token"},
            )
            assert response.status_code == 200
            assert "workos" in response.text


# --- Dual Auth Tests ---


class TestDualAuth:
    """Tests for dual auth (simple token + WorkOS)."""

    def test_simple_token_when_both_configured(self, mock_jwks_client):
        client = create_test_app(
            simple_token="test-token-123",
            workos_domain="test.authkit.app",
        )
        response = client.get("/sse", headers={"Authorization": "Bearer test-token-123"})
        assert response.status_code == 200
        assert "simple_token" in response.text
        mock_jwks_client.get_signing_key_from_jwt.assert_not_called()

    def test_workos_token_when_both_configured(self, mock_jwks_client):
        mock_key = MagicMock()
        mock_key.key = "test-key"
        mock_jwks_client.get_signing_key_from_jwt.return_value = mock_key

        with patch("instainstru_mcp.server.pyjwt.decode") as mock_decode:
            mock_decode.return_value = {
                "sub": "user123",
                "email": "admin@instainstru.com",
            }
            client = create_test_app(
                simple_token="different-token",
                workos_domain="test.authkit.app",
            )
            response = client.get(
                "/sse",
                headers={"Authorization": "Bearer valid.jwt.token"},
            )
            assert response.status_code == 200
            assert "workos" in response.text


# --- Health Endpoint Tests ---


class TestHealthEndpoint:
    """Tests for health endpoint (no auth required)."""

    def test_health_no_auth(self):
        client = create_test_app(simple_token="test-token", workos_domain="")
        response = client.get("/api/v1/health")
        assert response.status_code == 200

    def test_health_with_auth(self):
        client = create_test_app(simple_token="test-token", workos_domain="")
        response = client.get(
            "/api/v1/health",
            headers={"Authorization": "Bearer test-token"},
        )
        assert response.status_code == 200


# --- No Auth Configured Tests ---


class TestNoAuthConfigured:
    """Tests when no authentication is configured."""

    def test_rejects_all_when_no_auth_configured(self):
        client = create_test_app(workos_domain="")
        response = client.get("/sse", headers={"Authorization": "Bearer any-token"})
        assert response.status_code == 401

    def test_health_still_works_when_no_auth_configured(self):
        client = create_test_app(workos_domain="")
        response = client.get("/api/v1/health")
        assert response.status_code == 200


# --- WorkOS Not Configured Tests ---


class TestWorkOSNotConfigured:
    """Tests when only simple token is configured (no WorkOS)."""

    def test_falls_back_to_simple_token_only(self):
        client = create_test_app(simple_token="test-token-123", workos_domain="")

        response = client.get("/sse", headers={"Authorization": "Bearer test-token-123"})
        assert response.status_code == 200

        response = client.get(
            "/sse",
            headers={
                "Authorization": "Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ0ZXN0In0.fake"
            },
        )
        assert response.status_code == 401


# --- Edge Cases ---


class TestEdgeCases:
    """Edge case tests."""

    def test_empty_token(self):
        client = create_test_app(simple_token="test-token-123", workos_domain="")
        response = client.get("/sse", headers={"Authorization": "Bearer "})
        assert response.status_code == 401

    def test_whitespace_token(self):
        client = create_test_app(simple_token="test-token-123", workos_domain="")
        response = client.get("/sse", headers={"Authorization": "Bearer   "})
        assert response.status_code == 401

    def test_token_with_extra_spaces(self):
        client = create_test_app(simple_token="test-token-123", workos_domain="")
        response = client.get("/sse", headers={"Authorization": "Bearer test-token-123 "})
        assert response.status_code == 401

    def test_multiple_bearer_keywords(self):
        client = create_test_app(simple_token="test-token-123", workos_domain="")
        response = client.get(
            "/sse",
            headers={"Authorization": "Bearer Bearer test-token-123"},
        )
        assert response.status_code == 401


# --- OAuth Metadata Tests ---


class TestOAuthMetadata:
    """Tests for OAuth metadata endpoints."""

    def test_oauth_metadata_endpoint_returns_workos_info(self):
        settings = get_test_settings(workos_domain="test.authkit.app")
        client = TestClient(create_app(settings=settings), raise_server_exceptions=False)

        response = client.get("/.well-known/oauth-protected-resource")
        assert response.status_code == 200
        payload = response.json()
        assert payload["resource"] == "https://mcp.instainstru.com/sse"
        assert payload["authorization_servers"] == ["https://test.authkit.app"]
        assert payload["bearer_methods_supported"] == ["header"]
        assert payload["scopes_supported"] == ["openid", "profile", "email"]

    def test_oauth_metadata_path_inserted(self):
        settings = get_test_settings(workos_domain="test.authkit.app")
        client = TestClient(create_app(settings=settings), raise_server_exceptions=False)

        response = client.get("/.well-known/oauth-protected-resource/sse")
        assert response.status_code == 200
        payload = response.json()
        assert payload["resource"] == "https://mcp.instainstru.com/sse"

    def test_oauth_metadata_no_auth_required(self):
        settings = get_test_settings(workos_domain="test.authkit.app")
        client = TestClient(create_app(settings=settings), raise_server_exceptions=False)
        assert client.get("/.well-known/oauth-protected-resource").status_code == 200

    def test_oauth_metadata_returns_503_when_not_configured(self):
        settings = get_test_settings(workos_domain="")
        client = TestClient(create_app(settings=settings), raise_server_exceptions=False)
        assert client.get("/.well-known/oauth-protected-resource").status_code == 503

    def test_oauth_authorization_server_rewrites_endpoints(self):
        settings = get_test_settings(workos_domain="test.authkit.app")
        client = TestClient(create_app(settings=settings), raise_server_exceptions=False)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "issuer": "https://test.authkit.app",
            "registration_endpoint": "https://workos.example.com/oauth2/register",
            "token_endpoint": "https://workos.example.com/oauth2/token",
        }

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response

        with patch("instainstru_mcp.server.httpx.AsyncClient") as mock_async_client:
            mock_async_client.return_value.__aenter__.return_value = mock_client
            response = client.get("/.well-known/oauth-authorization-server")

        assert response.status_code == 200
        data = response.json()
        assert data["issuer"] == "https://test.authkit.app"
        assert data["registration_endpoint"] == "https://mcp.instainstru.com/oauth2/register"
        assert data["token_endpoint"] == "https://mcp.instainstru.com/oauth2/token"

    def test_oauth_authorization_server_503_when_not_configured(self):
        settings = get_test_settings(workos_domain="")
        client = TestClient(create_app(settings=settings), raise_server_exceptions=False)
        response = client.get("/.well-known/oauth-authorization-server")
        assert response.status_code == 503


# --- WWW-Authenticate Header Tests ---


class TestWWWAuthenticateHeader:
    """Tests RFC 9728 compliance for WWW-Authenticate header."""

    def test_401_includes_resource_metadata_header(self):
        client = create_test_app(simple_token="test-token-123", workos_domain="")
        response = client.get("/sse")
        assert response.status_code == 401
        assert (
            response.headers.get("WWW-Authenticate")
            == 'Bearer resource_metadata="https://mcp.instainstru.com/.well-known/oauth-protected-resource"'
        )


class TestCORSPreflight:
    """Test CORS preflight handling."""

    def test_options_request_returns_204_with_cors_headers(self):
        settings = get_test_settings()
        app = create_app(settings)
        client = TestClient(app, raise_server_exceptions=False)

        response = client.options(
            "/sse",
            headers={
                "Origin": "https://example.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert response.status_code in {200, 204}
        assert "Access-Control-Allow-Origin" in response.headers
        assert "Access-Control-Allow-Methods" in response.headers
        assert "Authorization" in response.headers.get("Access-Control-Allow-Headers", "")

    def test_options_request_no_auth_required(self):
        settings = get_test_settings()
        app = create_app(settings)
        client = TestClient(app, raise_server_exceptions=False)

        response = client.options(
            "/sse",
            headers={
                "Origin": "https://example.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert response.status_code in {200, 204}


class TestCORSHeaders:
    """Test CORS headers on successful responses."""

    def test_sse_response_includes_cors_headers(self):
        settings = get_test_settings()
        app = create_app(settings)
        client = TestClient(app, raise_server_exceptions=False)

        response = client.get(
            "/api/v1/health",
            headers={"Origin": "https://example.com"},
        )
        assert response.status_code == 200
        assert response.headers.get("Access-Control-Allow-Origin") == "*"


class TestGetAppSingleton:
    """Tests for get_app singleton behavior."""

    def test_get_app_returns_singleton(self):
        from instainstru_mcp import server as server_module

        server_module._app = None
        sentinel = object()

        with patch("instainstru_mcp.server.create_app", return_value=sentinel) as mock_create:
            app_first = server_module.get_app()
            app_second = server_module.get_app()

        assert app_first is sentinel
        assert app_second is sentinel
        mock_create.assert_called_once()
        server_module._app = None


class TestOAuthEndpointProxies:
    """Test OAuth endpoint proxies/redirects."""

    def test_openid_configuration_exempt_from_auth(self):
        settings = get_test_settings()
        app = create_app(settings)
        client = TestClient(app, raise_server_exceptions=False)

        response = client.get("/.well-known/openid-configuration")
        assert response.status_code != 401

    def test_register_endpoint_proxies_post(self):
        settings = get_test_settings()
        app = create_app(settings)
        client = TestClient(app, raise_server_exceptions=False)

        response = client.post("/register", json={"client_name": "test"})
        assert response.status_code != 401

    def test_openid_configuration_proxies_response(self):
        settings = get_test_settings(workos_domain="test.authkit.app")
        app = create_app(settings)
        client = TestClient(app, raise_server_exceptions=False)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"issuer": "https://test.authkit.app"}

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response

        with patch("instainstru_mcp.server.httpx.AsyncClient") as mock_async_client:
            mock_async_client.return_value.__aenter__.return_value = mock_client
            response = client.get("/.well-known/openid-configuration")

        assert response.status_code == 200
        assert response.json()["issuer"] == "https://test.authkit.app"

    def test_register_proxy_post_returns_status(self):
        settings = get_test_settings(workos_domain="test.authkit.app")
        app = create_app(settings)
        client = TestClient(app, raise_server_exceptions=False)

        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"client_id": "abc123"}

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response

        with patch("instainstru_mcp.server.httpx.AsyncClient") as mock_async_client:
            mock_async_client.return_value.__aenter__.return_value = mock_client
            response = client.post("/register", json={"client_name": "test"})

        assert response.status_code == 201
        assert response.json()["client_id"] == "abc123"

    def test_token_proxy_post_returns_status(self):
        settings = get_test_settings(workos_domain="test.authkit.app")
        app = create_app(settings)
        client = TestClient(app, raise_server_exceptions=False)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"access_token": "token123"}

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response

        with patch("instainstru_mcp.server.httpx.AsyncClient") as mock_async_client:
            mock_async_client.return_value.__aenter__.return_value = mock_client
            response = client.post("/oauth2/token", data={"grant_type": "client_credentials"})

        assert response.status_code == 200
        assert response.json()["access_token"] == "token123"
