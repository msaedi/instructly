"""Tests for OAuth metadata proxy endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from instainstru_mcp.config import Settings
from instainstru_mcp.oauth.endpoints import attach_oauth_routes
from starlette.applications import Starlette
from starlette.testclient import TestClient


def _build_app(settings: Settings) -> TestClient:
    app = Starlette()
    attach_oauth_routes(app, settings)
    return TestClient(app, raise_server_exceptions=False)


def _settings(workos_domain: str | None = "workos.test") -> Settings:
    return Settings(
        api_service_token="token",
        workos_domain=workos_domain,
        workos_client_id="workos-client",
        workos_client_secret="secret",
        oauth_issuer="https://mcp.instainstru.com",
    )


def test_oauth_authorization_server_proxies_workos():
    settings = _settings()
    client = _build_app(settings)

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"issuer": "https://workos.test"}

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_response

    with patch("instainstru_mcp.oauth.endpoints.httpx.AsyncClient") as mock_async_client:
        mock_async_client.return_value.__aenter__.return_value = mock_client
        response = client.get("/.well-known/oauth-authorization-server")

    assert response.status_code == 200
    assert response.json()["issuer"] == "https://workos.test"


def test_oauth_authorization_server_503_when_not_configured():
    settings = _settings(workos_domain=None)
    client = _build_app(settings)

    response = client.get("/.well-known/oauth-authorization-server")
    assert response.status_code == 503


def test_oauth_protected_resource_points_to_workos():
    settings = _settings()
    client = _build_app(settings)

    response = client.get("/.well-known/oauth-protected-resource")
    assert response.status_code == 200
    payload = response.json()
    assert payload["resource"] == "https://mcp.instainstru.com"
    assert payload["authorization_servers"] == ["https://workos.test"]
    assert payload["bearer_methods_supported"] == ["header"]


def test_openid_configuration_proxies_workos():
    settings = _settings()
    client = _build_app(settings)

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"issuer": "https://workos.test"}

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_response

    with patch("instainstru_mcp.oauth.endpoints.httpx.AsyncClient") as mock_async_client:
        mock_async_client.return_value.__aenter__.return_value = mock_client
        response = client.get("/.well-known/openid-configuration")

    assert response.status_code == 200
    assert response.json()["issuer"] == "https://workos.test"


def test_jwks_endpoint_proxies_workos():
    settings = _settings()
    client = _build_app(settings)

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"keys": [{"kid": "workos-key"}]}

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_response

    with patch("instainstru_mcp.oauth.endpoints.httpx.AsyncClient") as mock_async_client:
        mock_async_client.return_value.__aenter__.return_value = mock_client
        response = client.get("/.well-known/jwks.json")

    assert response.status_code == 200
    assert response.json()["keys"][0]["kid"] == "workos-key"


def test_userinfo_proxies_workos():
    settings = _settings()
    client = _build_app(settings)

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"sub": "user123", "email": "admin@instainstru.com"}

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_response

    with patch("instainstru_mcp.oauth.endpoints.httpx.AsyncClient") as mock_async_client:
        mock_async_client.return_value.__aenter__.return_value = mock_client
        response = client.get(
            "/oauth2/userinfo",
            headers={"Authorization": "Bearer workos-token"},
        )

    assert response.status_code == 200
    assert response.json()["sub"] == "user123"
