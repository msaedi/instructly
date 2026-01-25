"""Tests for dual auth middleware (Bearer + Auth0 OAuth)."""

import time
from unittest.mock import MagicMock, patch

import jwt
import pytest
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient


# --- Fixtures ---

@pytest.fixture
def mock_jwks_client():
    """Mock PyJWKClient for Auth0 tests."""
    with patch("instainstru_mcp.auth.PyJWKClient") as mock:
        mock_client = MagicMock()
        mock.return_value = mock_client
        yield mock_client


@pytest.fixture
def valid_auth0_token():
    """Generate a valid-looking JWT for testing."""
    payload = {
        "sub": "auth0|user123",
        "email": "admin@instainstru.com",
        "aud": "https://mcp.instainstru.com",
        "iss": "https://instainstru-admin.us.auth0.com/",
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600,
    }
    return jwt.encode(payload, "test-secret", algorithm="HS256")


@pytest.fixture
def expired_auth0_token():
    """Generate an expired JWT."""
    payload = {
        "sub": "auth0|user123",
        "email": "admin@instainstru.com",
        "aud": "https://mcp.instainstru.com",
        "iss": "https://instainstru-admin.us.auth0.com/",
        "iat": int(time.time()) - 7200,
        "exp": int(time.time()) - 3600,
    }
    return jwt.encode(payload, "test-secret", algorithm="HS256")


def create_test_app(simple_token=None, auth0_domain=None, auth0_audience=None):
    """Create a test app with the middleware."""
    from instainstru_mcp.auth import get_auth0_validator

    get_auth0_validator.cache_clear()

    env = {}
    if simple_token:
        env["INSTAINSTRU_MCP_API_SERVICE_TOKEN"] = simple_token
    if auth0_domain:
        env["AUTH0_DOMAIN"] = auth0_domain
    if auth0_audience:
        env["AUTH0_AUDIENCE"] = auth0_audience

    with patch.dict("os.environ", env, clear=True):
        from instainstru_mcp.server import DualAuthMiddleware

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
        wrapped = DualAuthMiddleware(app)

        return TestClient(wrapped, raise_server_exceptions=False)


# --- Simple Token Tests ---

class TestSimpleTokenAuth:
    """Tests for simple Bearer token authentication (Claude Desktop)."""

    def test_valid_simple_token(self):
        """Should accept valid simple Bearer token."""
        client = create_test_app(simple_token="test-token-123")
        response = client.get("/sse", headers={"Authorization": "Bearer test-token-123"})
        assert response.status_code == 200
        assert "simple_token" in response.text

    def test_invalid_simple_token(self):
        """Should reject invalid simple Bearer token."""
        client = create_test_app(simple_token="test-token-123")
        response = client.get("/sse", headers={"Authorization": "Bearer wrong-token"})
        assert response.status_code == 401

    def test_missing_auth_header(self):
        """Should reject requests without Authorization header."""
        client = create_test_app(simple_token="test-token-123")
        response = client.get("/sse")
        assert response.status_code == 401
        assert "Missing" in response.json()["error"]

    def test_malformed_auth_header(self):
        """Should reject malformed Authorization header."""
        client = create_test_app(simple_token="test-token-123")
        response = client.get("/sse", headers={"Authorization": "Basic abc123"})
        assert response.status_code == 401

    def test_bearer_case_sensitive(self):
        """Bearer keyword should be case-sensitive."""
        client = create_test_app(simple_token="test-token-123")
        response = client.get("/sse", headers={"Authorization": "bearer test-token-123"})
        assert response.status_code == 401


# --- Auth0 Token Tests ---

class TestAuth0TokenAuth:
    """Tests for Auth0 JWT authentication (Claude Web)."""

    def test_valid_auth0_token(self, mock_jwks_client, valid_auth0_token):
        """Should accept valid Auth0 JWT."""
        mock_key = MagicMock()
        mock_key.key = "test-secret"
        mock_jwks_client.get_signing_key_from_jwt.return_value = mock_key

        with patch("instainstru_mcp.auth.jwt.decode") as mock_decode:
            mock_decode.return_value = {
                "sub": "auth0|user123",
                "email": "admin@instainstru.com",
            }

            client = create_test_app(
                auth0_domain="instainstru-admin.us.auth0.com",
                auth0_audience="https://mcp.instainstru.com",
            )
            response = client.get(
                "/sse",
                headers={"Authorization": f"Bearer {valid_auth0_token}"},
            )
            assert response.status_code == 200
            assert "auth0" in response.text

    def test_expired_auth0_token(self, mock_jwks_client, expired_auth0_token):
        """Should reject expired Auth0 JWT."""
        mock_key = MagicMock()
        mock_key.key = "test-secret"
        mock_jwks_client.get_signing_key_from_jwt.return_value = mock_key

        with patch("instainstru_mcp.auth.jwt.decode") as mock_decode:
            mock_decode.side_effect = jwt.ExpiredSignatureError("Token expired")

            client = create_test_app(
                auth0_domain="instainstru-admin.us.auth0.com",
                auth0_audience="https://mcp.instainstru.com",
            )
            response = client.get(
                "/sse",
                headers={"Authorization": f"Bearer {expired_auth0_token}"},
            )
            assert response.status_code == 401

    def test_wrong_audience(self, mock_jwks_client, valid_auth0_token):
        """Should reject JWT with wrong audience."""
        mock_key = MagicMock()
        mock_key.key = "test-secret"
        mock_jwks_client.get_signing_key_from_jwt.return_value = mock_key

        with patch("instainstru_mcp.auth.jwt.decode") as mock_decode:
            mock_decode.side_effect = jwt.InvalidAudienceError("Invalid audience")

            client = create_test_app(
                auth0_domain="instainstru-admin.us.auth0.com",
                auth0_audience="https://mcp.instainstru.com",
            )
            response = client.get(
                "/sse",
                headers={"Authorization": f"Bearer {valid_auth0_token}"},
            )
            assert response.status_code == 401

    def test_wrong_issuer(self, mock_jwks_client, valid_auth0_token):
        """Should reject JWT with wrong issuer."""
        mock_key = MagicMock()
        mock_key.key = "test-secret"
        mock_jwks_client.get_signing_key_from_jwt.return_value = mock_key

        with patch("instainstru_mcp.auth.jwt.decode") as mock_decode:
            mock_decode.side_effect = jwt.InvalidIssuerError("Invalid issuer")

            client = create_test_app(
                auth0_domain="instainstru-admin.us.auth0.com",
                auth0_audience="https://mcp.instainstru.com",
            )
            response = client.get(
                "/sse",
                headers={"Authorization": f"Bearer {valid_auth0_token}"},
            )
            assert response.status_code == 401


# --- Dual Auth Tests ---

class TestDualAuth:
    """Tests for dual auth (both methods configured)."""

    def test_simple_token_when_both_configured(self, mock_jwks_client):
        """Simple token should work when both auth methods configured."""
        client = create_test_app(
            simple_token="test-token-123",
            auth0_domain="instainstru-admin.us.auth0.com",
            auth0_audience="https://mcp.instainstru.com",
        )
        response = client.get("/sse", headers={"Authorization": "Bearer test-token-123"})
        assert response.status_code == 200
        assert "simple_token" in response.text

    def test_auth0_token_when_both_configured(self, mock_jwks_client, valid_auth0_token):
        """Auth0 token should work when both auth methods configured."""
        mock_key = MagicMock()
        mock_key.key = "test-secret"
        mock_jwks_client.get_signing_key_from_jwt.return_value = mock_key

        with patch("instainstru_mcp.auth.jwt.decode") as mock_decode:
            mock_decode.return_value = {
                "sub": "auth0|user123",
                "email": "admin@test.com",
            }

            client = create_test_app(
                simple_token="different-token",
                auth0_domain="instainstru-admin.us.auth0.com",
                auth0_audience="https://mcp.instainstru.com",
            )
            response = client.get(
                "/sse",
                headers={"Authorization": f"Bearer {valid_auth0_token}"},
            )
            assert response.status_code == 200
            assert "auth0" in response.text

    def test_simple_token_tried_first(self, mock_jwks_client):
        """Simple token should be tried before Auth0 (faster path)."""
        client = create_test_app(
            simple_token="test-token-123",
            auth0_domain="instainstru-admin.us.auth0.com",
            auth0_audience="https://mcp.instainstru.com",
        )
        response = client.get("/sse", headers={"Authorization": "Bearer test-token-123"})

        mock_jwks_client.get_signing_key_from_jwt.assert_not_called()
        assert response.status_code == 200


# --- Health Endpoint Tests ---

class TestHealthEndpoint:
    """Tests for health endpoint (no auth required)."""

    def test_health_no_auth(self):
        """Health endpoint should work without auth."""
        client = create_test_app(simple_token="test-token")
        response = client.get("/api/v1/health")
        assert response.status_code == 200

    def test_health_with_auth(self):
        """Health endpoint should also work with auth header."""
        client = create_test_app(simple_token="test-token")
        response = client.get(
            "/api/v1/health",
            headers={"Authorization": "Bearer test-token"},
        )
        assert response.status_code == 200


# --- No Auth Configured Tests ---

class TestNoAuthConfigured:
    """Tests when no authentication is configured."""

    def test_rejects_all_when_no_auth_configured(self):
        """Should reject all requests when no auth method configured."""
        client = create_test_app()
        response = client.get("/sse", headers={"Authorization": "Bearer any-token"})
        assert response.status_code == 401

    def test_health_still_works_when_no_auth_configured(self):
        """Health should still work even with no auth configured."""
        client = create_test_app()
        response = client.get("/api/v1/health")
        assert response.status_code == 200


# --- Auth0 Not Configured Tests ---

class TestAuth0NotConfigured:
    """Tests when only simple token is configured (no Auth0)."""

    def test_falls_back_to_simple_token_only(self):
        """Should only try simple token when Auth0 not configured."""
        client = create_test_app(simple_token="test-token-123")

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
        """Should reject empty token."""
        client = create_test_app(simple_token="test-token-123")
        response = client.get("/sse", headers={"Authorization": "Bearer "})
        assert response.status_code == 401

    def test_whitespace_token(self):
        """Should reject whitespace token."""
        client = create_test_app(simple_token="test-token-123")
        response = client.get("/sse", headers={"Authorization": "Bearer   "})
        assert response.status_code == 401

    def test_token_with_extra_spaces(self):
        """Should handle token with surrounding spaces."""
        client = create_test_app(simple_token="test-token-123")
        response = client.get("/sse", headers={"Authorization": "Bearer test-token-123 "})
        assert response.status_code == 401

    def test_multiple_bearer_keywords(self):
        """Should handle malformed 'Bearer Bearer token'."""
        client = create_test_app(simple_token="test-token-123")
        response = client.get(
            "/sse",
            headers={"Authorization": "Bearer Bearer test-token-123"},
        )
        assert response.status_code == 401
