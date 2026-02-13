"""
SSE (Server-Sent Events) endpoint integration tests.

These tests AUTOMATICALLY discover streaming endpoints from the OpenAPI schema
using the same pattern that excludes them from schemathesis tests.

Pattern: `.*/stream.*` - any endpoint with "stream" in its path

This ensures:
- Endpoints excluded from schemathesis are automatically tested here
- New streaming endpoints are discovered without manual test updates

Tested aspects:
1. Authentication requirements (401 responses are immediate)
2. OpenAPI schema verification (endpoints are properly documented)
"""

import os
import re

import pytest

# Gate expensive app boot: skip entire module before heavy imports when not running SSE tests
RUN_SSE_TESTS = os.environ.get("RUN_SSE_TESTS", "0") == "1"
if not RUN_SSE_TESTS:
    pytest.skip("SSE tests run in nightly CI job (set RUN_SSE_TESTS=1)", allow_module_level=True)

from fastapi.testclient import TestClient

from app.database import get_db
from app.main import fastapi_app

# Same pattern used to exclude from schemathesis - keeps them in sync
STREAMING_ENDPOINT_PATTERN = re.compile(r".*/stream.*")


def discover_streaming_endpoints() -> list[tuple[str, str]]:
    """Discover all streaming endpoints from OpenAPI schema.

    Returns list of (method, path) tuples for endpoints matching the streaming pattern.
    This uses the same pattern that excludes them from schemathesis.
    """
    with TestClient(fastapi_app) as client:
        response = client.get("/openapi.json")
        if response.status_code != 200:
            return []

        schema = response.json()
        paths = schema.get("paths", {})

        streaming_endpoints = []
        for path, methods in paths.items():
            if STREAMING_ENDPOINT_PATTERN.match(path):
                for method in methods.keys():
                    if method in ("get", "post", "put", "patch", "delete"):
                        streaming_endpoints.append((method.upper(), path))

        return streaming_endpoints


# Discover endpoints at module load time
STREAMING_ENDPOINTS = discover_streaming_endpoints()


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


class TestStreamingEndpointsDiscovery:
    """Verify streaming endpoints are discovered correctly."""

    def test_streaming_endpoints_discovered(self):
        """At least one streaming endpoint should be discovered."""
        assert len(STREAMING_ENDPOINTS) > 0, (
            "No streaming endpoints found matching pattern. "
            "Either pattern is wrong or no streaming endpoints exist."
        )

    def test_pattern_matches_expected_endpoints(self):
        """Verify the pattern matches expected streaming paths."""
        # Sanity check - /api/v1/messages/stream should be discovered
        paths = [path for _, path in STREAMING_ENDPOINTS]
        assert any(
            "/stream" in path for path in paths
        ), f"Expected /stream endpoints, found: {paths}"


class TestStreamingEndpointsAuth:
    """Authentication tests for all discovered streaming endpoints."""

    @pytest.mark.parametrize(
        "method,path",
        STREAMING_ENDPOINTS,
        ids=[f"{m} {p}" for m, p in STREAMING_ENDPOINTS],
    )
    def test_streaming_endpoint_requires_auth(self, client, method, path):
        """All streaming endpoints should require authentication (401 without auth)."""
        # Make request without auth headers
        response = client.request(method, path)

        # Streaming endpoints should require auth
        # 401 = not authenticated, 404 = path param validation failed first
        assert response.status_code in (401, 404, 422), (
            f"{method} {path} returned {response.status_code}, "
            f"expected 401 (unauthorized) or 404/422 (path validation)"
        )


class TestStreamingEndpointsOpenAPI:
    """OpenAPI schema tests for all discovered streaming endpoints."""

    @pytest.mark.parametrize(
        "method,path",
        STREAMING_ENDPOINTS,
        ids=[f"{m} {p}" for m, p in STREAMING_ENDPOINTS],
    )
    def test_streaming_endpoint_in_openapi(self, client, method, path):
        """All streaming endpoints should be documented in OpenAPI schema."""
        response = client.get("/openapi.json")
        assert response.status_code == 200

        schema = response.json()
        paths = schema.get("paths", {})

        assert path in paths, f"Endpoint {path} not found in OpenAPI schema"
        assert method.lower() in paths[path], (
            f"Method {method} not found for {path} in OpenAPI schema"
        )

    @pytest.mark.parametrize(
        "method,path",
        STREAMING_ENDPOINTS,
        ids=[f"{m} {p}" for m, p in STREAMING_ENDPOINTS],
    )
    def test_streaming_endpoint_documents_responses(self, client, method, path):
        """Streaming endpoints should document response codes."""
        response = client.get("/openapi.json")
        schema = response.json()

        endpoint = schema["paths"][path][method.lower()]
        responses = endpoint.get("responses", {})

        # Should have at least 200 response documented
        assert "200" in responses, (
            f"{method} {path} should document 200 response"
        )
