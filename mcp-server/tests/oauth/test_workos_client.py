"""Tests for WorkOS client utilities."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest
import respx
from instainstru_mcp.oauth.workos_client import WorkOSClient


def test_authorization_url_includes_authkit_provider():
    client = WorkOSClient("workos.example", "client_123", "secret")
    url = client.get_authorization_url("https://mcp.instainstru.com/oauth2/callback", "state123")
    query = parse_qs(urlparse(url).query)

    assert query["client_id"][0] == "client_123"
    assert query["redirect_uri"][0] == "https://mcp.instainstru.com/oauth2/callback"
    assert query["response_type"][0] == "code"
    assert query["state"][0] == "state123"
    assert query["scope"][0] == "openid profile email"
    assert query["provider"][0] == "authkit"


@pytest.mark.asyncio
@respx.mock
async def test_exchange_code_posts_form_payload():
    client = WorkOSClient("workos.example", "client_123", "secret")

    route = respx.post("https://workos.example/oauth2/token").respond(
        200, json={"access_token": "token-123"}
    )

    result = await client.exchange_code("code-123", "https://mcp.instainstru.com/callback")
    assert result["access_token"] == "token-123"
    assert route.called is True


@pytest.mark.asyncio
@respx.mock
async def test_get_userinfo_fetches_profile():
    client = WorkOSClient("workos.example", "client_123", "secret")

    route = respx.get("https://workos.example/oauth2/userinfo").respond(
        200, json={"sub": "user123", "email": "admin@instainstru.com"}
    )

    result = await client.get_userinfo("access-token")
    assert result["sub"] == "user123"
    assert route.called is True


@pytest.mark.asyncio
@respx.mock
async def test_get_jwks_returns_keys():
    client = WorkOSClient("workos.example", "client_123", "secret")

    route = respx.get("https://workos.example/oauth2/jwks").respond(
        200, json={"keys": [{"kid": "kid1"}]}
    )

    result = await client.get_jwks()
    assert result["keys"][0]["kid"] == "kid1"
    assert route.called is True
