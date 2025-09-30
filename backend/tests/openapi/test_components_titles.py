from app.main import fastapi_app as app


def test_service_area_neighborhood_component_present():
    doc = app.openapi()
    schemas = doc.get("components", {}).get("schemas", {})
    assert "ServiceAreaNeighborhood" in schemas, (
        "Missing schema: " + ", ".join(sorted(schemas.keys())[:10])
    )
