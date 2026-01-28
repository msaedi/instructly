import pytest
from instainstru_mcp.auth import AuthenticationError, MCPAuth
from instainstru_mcp.config import Settings


def test_headers_for_backend():
    settings = Settings(api_service_token="svc")
    auth = MCPAuth(settings)
    headers = auth.get_headers("req-1")
    assert headers["Authorization"] == "Bearer svc"
    assert headers["X-Request-Id"] == "req-1"


def test_headers_missing_service_token():
    settings = Settings(api_service_token="")
    auth = MCPAuth(settings)
    with pytest.raises(AuthenticationError):
        auth.get_headers("req-1")


def test_headers_allow_m2m_without_static_token():
    settings = Settings(
        api_service_token="",
        workos_m2m_client_id="client_123",
        workos_m2m_client_secret="secret",
        workos_m2m_token_url="https://api.workos.com/oauth/token",
        workos_m2m_audience="https://api.instainstru.com",
    )
    auth = MCPAuth(settings)
    headers = auth.get_headers("req-1")
    assert headers == {"X-Request-Id": "req-1"}
