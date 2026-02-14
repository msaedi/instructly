"""
Tests for openapi_app.py - targeting CI coverage gaps.
Tests the OpenAPI schema generation app setup.
"""
from fastapi import FastAPI
from fastapi.routing import APIRoute
import pytest


@pytest.fixture(scope="module")
def openapi_app():
    """Build the OpenAPI app once for all tests in this module."""
    from app.openapi_app import build_openapi_app

    return build_openapi_app()


@pytest.fixture(scope="module")
def openapi_schema(openapi_app):
    """Generate the OpenAPI schema once for all tests in this module."""
    return openapi_app.openapi()


class TestBuildOpenAPIApp:
    """Tests for build_openapi_app() function."""

    def test_build_openapi_app_returns_fastapi_instance(self, openapi_app):
        """Test that build_openapi_app returns a FastAPI instance."""
        assert isinstance(openapi_app, FastAPI)

    def test_openapi_app_has_correct_title(self, openapi_app):
        """Test that the app has the correct title."""
        assert openapi_app.title == "iNSTAiNSTRU API"

    def test_openapi_app_has_correct_version(self, openapi_app):
        """Test that the app has the correct version."""
        assert openapi_app.version == "1.0.0"

    def test_openapi_app_has_correct_description(self, openapi_app):
        """Test that the app has the correct description."""
        assert "iNSTAiNSTRU" in openapi_app.description
        assert "NYC" in openapi_app.description

    def test_openapi_app_has_openapi_url(self, openapi_app):
        """Test that openapi_url is set correctly."""
        assert openapi_app.openapi_url == "/openapi.json"

    def test_openapi_app_docs_disabled(self, openapi_app):
        """Test that docs are disabled (not needed for schema generation)."""
        assert openapi_app.docs_url is None
        assert openapi_app.redoc_url is None

    def test_openapi_schema_can_be_generated(self, openapi_schema):
        """Test that OpenAPI schema can be generated without errors."""
        assert isinstance(openapi_schema, dict)
        assert "openapi" in openapi_schema
        assert "info" in openapi_schema
        assert "paths" in openapi_schema

    def test_openapi_schema_has_api_v1_paths(self, openapi_schema):
        """Test that schema includes /api/v1/* paths."""
        # At least some paths should start with /api/v1
        api_v1_paths = [p for p in openapi_schema["paths"].keys() if p.startswith("/api/v1")]
        assert len(api_v1_paths) > 0, "No /api/v1 paths found in OpenAPI schema"

    def test_openapi_schema_includes_critical_endpoints(self, openapi_schema):
        """Test that critical endpoints are present in schema."""
        paths = openapi_schema["paths"].keys()

        # Check for critical endpoint prefixes
        critical_prefixes = [
            "/api/v1/health",
            "/api/v1/auth",
            "/api/v1/instructors",
            "/api/v1/bookings",
        ]

        for prefix in critical_prefixes:
            matching = [p for p in paths if p.startswith(prefix)]
            assert len(matching) > 0, f"No endpoints starting with {prefix}"


class TestOpenAPIAppInstance:
    """Tests for the pre-built openapi_app instance."""

    def test_openapi_app_instance_exists(self):
        """Test that openapi_app instance is created."""
        from app.openapi_app import openapi_app

        assert openapi_app is not None
        assert isinstance(openapi_app, FastAPI)

    def test_openapi_app_instance_has_routes(self):
        """Test that the app instance has routes registered."""
        from app.openapi_app import openapi_app

        routes = list(openapi_app.routes)
        assert len(routes) > 0, "No routes registered on openapi_app"

    def test_openapi_app_routes_are_api_routes(self):
        """Test that routes are properly configured API routes."""
        from app.openapi_app import openapi_app

        # Get all routes that are APIRoutes (not default routes)
        api_routes = [r for r in openapi_app.routes if isinstance(r, APIRoute)]

        # Should have many API routes
        assert len(api_routes) > 50, f"Expected many API routes, got {len(api_routes)}"
