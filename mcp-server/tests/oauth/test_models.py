"""Tests for OAuth data models."""

from __future__ import annotations

from datetime import datetime

from instainstru_mcp.oauth.models import (
    AuthorizationCode,
    OAuthSession,
    RefreshToken,
    RegisteredClient,
)


def test_registered_client_defaults():
    client = RegisteredClient(
        client_id="client123",
        client_name="Test Client",
        redirect_uris=["https://example.com/callback"],
    )
    assert client.token_endpoint_auth_method == "none"
    assert "authorization_code" in client.grant_types
    assert "refresh_token" in client.grant_types
    assert client.response_types == ["code"]
    assert isinstance(client.created_at, datetime)


def test_oauth_session_fields():
    session = OAuthSession(
        session_id="session123",
        client_id="client123",
        redirect_uri="https://example.com/callback",
        code_challenge="challenge",
        code_challenge_method="S256",
        original_state="state123",
        resource=None,
        scope="openid email",
    )
    assert session.session_id == "session123"
    assert session.code_challenge_method == "S256"
    assert isinstance(session.created_at, datetime)


def test_authorization_code_fields():
    code = AuthorizationCode(
        code="code123",
        user_id="user123",
        user_email="user@example.com",
        client_id="client123",
        redirect_uri="https://example.com/callback",
        code_challenge="challenge",
        resource=None,
        scope="openid",
    )
    assert code.user_email == "user@example.com"
    assert isinstance(code.created_at, datetime)


def test_refresh_token_fields():
    token = RefreshToken(
        token="refresh123",
        user_id="user123",
        user_email="user@example.com",
        client_id="client123",
        scope="openid",
    )
    assert token.token == "refresh123"
    assert isinstance(token.created_at, datetime)
