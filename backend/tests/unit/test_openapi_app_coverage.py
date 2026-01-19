"""
Tests for openapi_app.py - targeting CI coverage gaps.
Tests the OpenAPI schema generation app setup.
"""
from fastapi import FastAPI
from fastapi.routing import APIRoute


class TestBuildOpenAPIApp:
    """Tests for build_openapi_app() function."""

    def test_build_openapi_app_returns_fastapi_instance(self):
        """Test that build_openapi_app returns a FastAPI instance."""
        from app.openapi_app import build_openapi_app

        app = build_openapi_app()

        assert isinstance(app, FastAPI)

    def test_openapi_app_has_correct_title(self):
        """Test that the app has the correct title."""
        from app.openapi_app import build_openapi_app

        app = build_openapi_app()

        assert app.title == "iNSTAiNSTRU API"

    def test_openapi_app_has_correct_version(self):
        """Test that the app has the correct version."""
        from app.openapi_app import build_openapi_app

        app = build_openapi_app()

        assert app.version == "1.0.0"

    def test_openapi_app_has_correct_description(self):
        """Test that the app has the correct description."""
        from app.openapi_app import build_openapi_app

        app = build_openapi_app()

        assert "iNSTAiNSTRU" in app.description
        assert "NYC" in app.description

    def test_openapi_app_has_openapi_url(self):
        """Test that openapi_url is set correctly."""
        from app.openapi_app import build_openapi_app

        app = build_openapi_app()

        assert app.openapi_url == "/openapi.json"

    def test_openapi_app_docs_disabled(self):
        """Test that docs are disabled (not needed for schema generation)."""
        from app.openapi_app import build_openapi_app

        app = build_openapi_app()

        assert app.docs_url is None
        assert app.redoc_url is None

    def test_openapi_schema_can_be_generated(self):
        """Test that OpenAPI schema can be generated without errors."""
        from app.openapi_app import build_openapi_app

        app = build_openapi_app()

        # This should not raise
        schema = app.openapi()

        assert isinstance(schema, dict)
        assert "openapi" in schema
        assert "info" in schema
        assert "paths" in schema

    def test_openapi_schema_has_api_v1_paths(self):
        """Test that schema includes /api/v1/* paths."""
        from app.openapi_app import build_openapi_app

        app = build_openapi_app()
        schema = app.openapi()

        # At least some paths should start with /api/v1
        api_v1_paths = [p for p in schema["paths"].keys() if p.startswith("/api/v1")]
        assert len(api_v1_paths) > 0, "No /api/v1 paths found in OpenAPI schema"

    def test_openapi_schema_includes_critical_endpoints(self):
        """Test that critical endpoints are present in schema."""
        from app.openapi_app import build_openapi_app

        app = build_openapi_app()
        schema = app.openapi()

        paths = schema["paths"].keys()

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
