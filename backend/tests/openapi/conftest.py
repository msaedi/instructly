import pytest


@pytest.fixture(scope="session")
def openapi_schema():
    """Generate the OpenAPI schema once per test session."""
    from app.openapi_app import openapi_app

    return openapi_app.openapi()
