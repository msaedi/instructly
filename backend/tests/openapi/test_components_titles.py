import pytest


@pytest.fixture(scope="module")
def openapi_schema():
    """Generate the OpenAPI schema from the shared lightweight OpenAPI app."""
    from app.openapi_app import openapi_app

    return openapi_app.openapi()


def test_service_area_neighborhood_component_present(openapi_schema):
    schemas = openapi_schema.get("components", {}).get("schemas", {})
    assert "ServiceAreaNeighborhood" in schemas, (
        "Missing schema: " + ", ".join(sorted(schemas.keys())[:10])
    )
