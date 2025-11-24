"""
Schemathesis-based API contract tests for /api/v1 endpoints.

These tests automatically validate that our FastAPI application conforms to its OpenAPI schema
by fuzzing endpoints with valid and edge-case inputs based on the schema definition.

Part of Phase 5 - Backend testing hardening.
"""
from fastapi.testclient import TestClient
from hypothesis import Phase, settings
import pytest
from schemathesis.openapi import from_asgi

from app.database import get_db
from app.main import fastapi_app

try:  # pragma: no cover - allow running from repo root or backend/
    from backend.tests.conftest import cleanup_test_database, create_test_session
except ModuleNotFoundError:  # pragma: no cover
    from tests.conftest import cleanup_test_database, create_test_session

# Use the raw FastAPI app for dependency overrides
app = fastapi_app

# Create the Schemathesis schema from the ASGI app
# This loads the OpenAPI schema directly from the /openapi.json endpoint
# Note: In Schemathesis 4.x, from_asgi is in schemathesis.openapi module
schema = from_asgi("/openapi.json", app)


# Filter to only test /api/v1/instructors/** endpoints to keep scope focused
# In Schemathesis 4.x, filtering is done via method chaining before parametrize()
filtered_schema = schema.include(path_regex="/api/v1/instructors/.*")


@filtered_schema.parametrize()
@settings(
    max_examples=5,  # Start with a small number for fast feedback
    deadline=None,    # Disable hypothesis deadline (FastAPI can be slow in tests)
    phases=[Phase.generate, Phase.target],  # Skip shrinking for faster tests
)
@pytest.mark.schemathesis
def test_api_v1_instructors_schema_compliance(case):
    """
    Test that /api/v1/instructors/** endpoints conform to OpenAPI schema.

    This test will:
    1. Generate requests based on the OpenAPI schema
    2. Call the endpoint via TestClient
    3. Validate the response matches the schema
    """
    session = create_test_session()

    def override_get_db():
        try:
            yield session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    try:
        response = case.call(session=client)
        # Validate response conforms to schema
        case.validate_response(response)
    finally:
        app.dependency_overrides.clear()
        client.close()
        session.rollback()
        session.close()
        cleanup_test_database()



# Additional test for all /api/v1/** endpoints (not just instructors)
# Can be enabled later when ready for broader testing
@pytest.mark.skip(reason="Broader API v1 testing - enable when ready")
@schema.include(path_regex="/api/v1/.*").parametrize()
@settings(max_examples=5, deadline=None)
@pytest.mark.schemathesis
def test_api_v1_all_endpoints_schema_compliance(case):
    """
    Test that all /api/v1/** endpoints conform to OpenAPI schema.

    This is a broader test that covers all v1 endpoints.
    Currently skipped to keep initial test scope focused.
    """
    response = case.call()
    case.validate_response(response)
