# backend/app/openapi_app.py
"""Lightweight FastAPI app for OpenAPI schema generation."""

from fastapi import FastAPI

from app.core.router_registry import register_openapi_routers


def build_openapi_app() -> FastAPI:
    """Build a minimal FastAPI app with all routers for OpenAPI generation."""

    app = FastAPI(
        title="iNSTAiNSTRU API",
        version="1.0.0",
        description="iNSTAiNSTRU - NYC's Premier Instructor Marketplace",
        openapi_url="/openapi.json",
        docs_url=None,
        redoc_url=None,
    )
    register_openapi_routers(app)
    return app


openapi_app = build_openapi_app()
