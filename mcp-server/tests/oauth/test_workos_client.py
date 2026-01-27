"""Tests for WorkOS client utilities."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

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
