def test_service_area_neighborhood_component_present(openapi_schema):
    schemas = openapi_schema.get("components", {}).get("schemas", {})
    assert "ServiceAreaNeighborhood" in schemas, (
        "Missing schema: " + ", ".join(sorted(schemas.keys())[:10])
    )
