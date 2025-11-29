"""
SSE (Server-Sent Events) endpoint integration tests.

These tests validate SSE streaming endpoints which require special handling:
- SSE connections are long-lived and never "complete" normally
- Standard HTTP request/response testing (like Schemathesis) can't handle them
- TestClient/httpx streaming also hangs due to sse_starlette's event loop state

Tested endpoints:
- GET /api/v1/messages/stream - Per-user inbox SSE stream (Phase 2)

Note: These tests focus on:
1. Authentication requirements (401 responses are immediate)
2. OpenAPI schema verification (endpoints are properly documented)

Full SSE event streaming tests require a different testing approach
(e.g., subprocess with timeout, or dedicated async testing framework).
"""

import os

from fastapi.testclient import TestClient
import pytest

from app.database import get_db
from app.main import fastapi_app

# Only run SSE tests when explicitly requested (nightly CI or local testing)
RUN_SSE_TESTS = os.environ.get("RUN_SSE_TESTS", "0") == "1"

pytestmark = pytest.mark.skipif(
    not RUN_SSE_TESTS,
    reason="SSE tests run in nightly CI job (set RUN_SSE_TESTS=1 to run locally)",
)


@pytest.fixture
def app_with_db(db):
    """Create app instance with test database session."""

    def override_get_db():
        try:
            yield db
        finally:
            pass

    fastapi_app.dependency_overrides[get_db] = override_get_db
    yield fastapi_app
    fastapi_app.dependency_overrides.clear()


@pytest.fixture
def client(app_with_db):
    """Create sync TestClient for SSE endpoint testing."""
    return TestClient(app_with_db, raise_server_exceptions=False)


class TestSSEUserStreamAuth:
    """Authentication tests for GET /api/v1/messages/stream."""

    def test_stream_requires_authentication(self, client):
        """SSE stream endpoint requires authentication - returns 401 without auth."""
        response = client.get("/api/v1/messages/stream")
        assert response.status_code == 401


class TestSSEEndpointDiscovery:
    """Tests to verify SSE endpoints exist and are properly configured in OpenAPI."""

    def test_stream_endpoint_exists_in_openapi(self, client):
        """Verify /api/v1/messages/stream is in the OpenAPI schema."""
        response = client.get("/openapi.json")
        assert response.status_code == 200
        schema = response.json()

        paths = schema.get("paths", {})
        assert "/api/v1/messages/stream" in paths
        assert "get" in paths["/api/v1/messages/stream"]

    def test_stream_endpoint_has_correct_response_codes(self, client):
        """Verify SSE stream endpoint documents expected response codes."""
        response = client.get("/openapi.json")
        assert response.status_code == 200
        schema = response.json()

        # User stream endpoint
        user_stream = schema["paths"]["/api/v1/messages/stream"]["get"]
        responses = user_stream.get("responses", {})
        # Should have 200 and 401 documented
        assert "200" in responses
        assert "401" in responses

    def test_stream_endpoint_has_sse_description(self, client):
        """Verify SSE stream endpoint mentions SSE in description."""
        response = client.get("/openapi.json")
        assert response.status_code == 200
        schema = response.json()

        user_stream = schema["paths"]["/api/v1/messages/stream"]["get"]
        # The endpoint should mention SSE or streaming in its description
        description = user_stream.get("description", "").lower()
        summary = user_stream.get("summary", "").lower()
        responses_desc = str(user_stream.get("responses", {}).get("200", {})).lower()

        # Check if SSE is mentioned somewhere
        sse_mentioned = (
            "sse" in description
            or "stream" in description
            or "sse" in summary
            or "stream" in summary
            or "stream" in responses_desc
        )
        assert sse_mentioned, "SSE endpoint should mention 'sse' or 'stream' in docs"
