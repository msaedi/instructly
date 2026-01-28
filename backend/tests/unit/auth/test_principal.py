from app.principal import ServicePrincipal, UserPrincipal


def test_user_principal_properties():
    principal = UserPrincipal(user_id="user_123", email="user@example.com")
    assert principal.id == "user_123"
    assert principal.identifier == "user@example.com"
    assert principal.principal_type == "user"


def test_service_principal_properties_and_scope():
    principal = ServicePrincipal(client_id="client_123", org_id="org_1", scopes=("mcp:read",))
    assert principal.id == "client_123"
    assert principal.identifier == "client_123"
    assert principal.principal_type == "service"
    assert principal.has_scope("mcp:read") is True
    assert principal.has_scope("mcp:write") is False
