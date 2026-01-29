import pytest
from instainstru_mcp.auth import AuthenticationError, MCPAuth, _secret_value
from instainstru_mcp.config import Settings
from pydantic import SecretStr


def test_headers_for_backend():
    settings = Settings(api_service_token="svc")
    auth = MCPAuth(settings)
    headers = auth.get_headers("req-1")
    assert headers["Authorization"] == "Bearer svc"
    assert headers["X-Request-Id"] == "req-1"


def test_headers_missing_service_token(monkeypatch):
    monkeypatch.delenv("INSTAINSTRU_MCP_WORKOS_M2M_CLIENT_ID", raising=False)
    monkeypatch.delenv("INSTAINSTRU_MCP_WORKOS_M2M_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("INSTAINSTRU_MCP_WORKOS_M2M_TOKEN_URL", raising=False)
    monkeypatch.delenv("INSTAINSTRU_MCP_WORKOS_M2M_AUDIENCE", raising=False)
    settings = Settings(
        api_service_token="",
        workos_m2m_client_id="",
        workos_m2m_client_secret="",
    )
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


def test_secret_value_handles_none_and_plain_str():
    assert _secret_value(None) == ""
    assert _secret_value("token") == "token"
    assert _secret_value(SecretStr("secret")) == "secret"
