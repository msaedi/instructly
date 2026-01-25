from unittest.mock import patch

import pytest
from starlette.responses import JSONResponse
from starlette.testclient import TestClient

from instainstru_mcp.server import BearerAuthMiddleware, create_app


class TestBearerAuthMiddleware:
    """Test auth middleware for MCP server."""

    @pytest.fixture
    def client_with_auth(self):
        """Client with valid auth token configured."""
        with patch.dict(
            "os.environ",
            {"INSTAINSTRU_MCP_API_SERVICE_TOKEN": "test-token-123"},
        ):
            app = create_app()
            with TestClient(app, raise_server_exceptions=False) as client:
                yield client

    @pytest.fixture
    def client_no_token_configured(self):
        """Client with no auth token in env (misconfigured server)."""
        with patch.dict("os.environ", {}, clear=True):
            app = create_app()
            with TestClient(app, raise_server_exceptions=False) as client:
                yield client

    def test_health_endpoint_no_auth_required(self, client_with_auth):
        """Health check should work without auth header."""
        response = client_with_auth.get("/api/v1/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        assert response.json()["service"] == "instainstru-mcp"

    def test_sse_endpoint_requires_auth(self, client_with_auth):
        """SSE endpoint should reject requests without auth."""
        response = client_with_auth.get("/sse")
        assert response.status_code == 401
        assert "Missing or invalid Authorization header" in response.json()["error"]

    def test_sse_endpoint_rejects_wrong_token(self, client_with_auth):
        """SSE endpoint should reject requests with wrong token."""
        response = client_with_auth.get(
            "/sse",
            headers={"Authorization": "Bearer wrong-token"},
        )
        assert response.status_code == 401
        assert "Invalid token" in response.json()["error"]

    def test_sse_endpoint_accepts_valid_token(self):
        """Auth middleware should allow requests with correct token."""
        async def app(scope, receive, send):
            response = JSONResponse({"ok": True})
            await response(scope, receive, send)

        with patch.dict(
            "os.environ",
            {"INSTAINSTRU_MCP_API_SERVICE_TOKEN": "test-token-123"},
        ):
            client = TestClient(BearerAuthMiddleware(app), raise_server_exceptions=False)
            response = client.get(
                "/sse",
                headers={"Authorization": "Bearer test-token-123"},
            )
            assert response.status_code == 200
            assert response.json()["ok"] is True

    def test_sse_endpoint_rejects_bearer_typo(self, client_with_auth):
        """Should reject 'bearer' (lowercase) or other typos."""
        response = client_with_auth.get(
            "/sse",
            headers={"Authorization": "bearer test-token-123"},
        )
        assert response.status_code == 401

    def test_server_500_when_token_not_configured(self, client_no_token_configured):
        """Server should fail closed when token env var missing."""
        response = client_no_token_configured.get(
            "/sse",
            headers={"Authorization": "Bearer any-token"},
        )
        assert response.status_code == 500
        assert "not configured" in response.json()["error"]

    def test_messages_endpoint_requires_auth(self, client_with_auth):
        """Messages endpoint should also require auth."""
        response = client_with_auth.post("/messages/")
        assert response.status_code == 401
