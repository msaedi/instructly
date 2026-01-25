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
