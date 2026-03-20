def test_public_config_response_requires_student_launch_enabled(openapi_schema):
    schemas = openapi_schema.get("components", {}).get("schemas", {})
    public_config_response = schemas["PublicConfigResponse"]

    assert "student_launch_enabled" in public_config_response.get("required", [])
    assert public_config_response["properties"]["student_launch_enabled"]["type"] == "boolean"
