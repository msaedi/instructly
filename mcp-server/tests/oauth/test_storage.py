"""Tests for OAuth storage implementation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from instainstru_mcp.oauth.models import (
    AuthorizationCode,
    OAuthSession,
    RefreshToken,
    RegisteredClient,
)
from instainstru_mcp.oauth.storage import InMemoryStorage


def test_save_and_get_client():
    storage = InMemoryStorage()
    client = RegisteredClient(
        client_id="client123",
        client_name="Test Client",
        redirect_uris=["https://example.com/callback"],
    )
    storage.save_client(client)
    assert storage.get_client("client123") == client


def test_session_ttl_expired():
    storage = InMemoryStorage()
    session = OAuthSession(
        session_id="session123",
        client_id="client123",
        redirect_uri="https://example.com/callback",
        code_challenge="challenge",
        code_challenge_method="S256",
        original_state="state123",
        resource=None,
        scope="openid",
        created_at=datetime.now(timezone.utc) - timedelta(minutes=11),
    )
    storage.save_session(session)
    assert storage.get_session("session123") is None


def test_auth_code_ttl_expired():
    storage = InMemoryStorage()
    code = AuthorizationCode(
        code="code123",
        user_id="user123",
        user_email="user@example.com",
        client_id="client123",
        redirect_uri="https://example.com/callback",
        code_challenge="challenge",
        resource=None,
        scope="openid",
        created_at=datetime.now(timezone.utc) - timedelta(minutes=6),
    )
    storage.save_auth_code(code)
    assert storage.get_auth_code("code123") is None


def test_refresh_token_ttl_expired():
    storage = InMemoryStorage()
    token = RefreshToken(
        token="refresh123",
        user_id="user123",
        user_email="user@example.com",
        client_id="client123",
        scope="openid",
        created_at=datetime.now(timezone.utc) - timedelta(days=8),
    )
    storage.save_refresh_token(token)
    assert storage.get_refresh_token("refresh123") is None


def test_delete_auth_code():
    storage = InMemoryStorage()
    code = AuthorizationCode(
        code="code456",
        user_id="user123",
        user_email="user@example.com",
        client_id="client123",
        redirect_uri="https://example.com/callback",
        code_challenge="challenge",
        resource=None,
        scope="openid",
    )
    storage.save_auth_code(code)
    storage.delete_auth_code("code456")
    assert storage.get_auth_code("code456") is None
