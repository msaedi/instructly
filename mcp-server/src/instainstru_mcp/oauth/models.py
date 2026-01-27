"""Data models for OAuth storage."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class RegisteredClient:
    client_id: str
    client_name: str
    redirect_uris: list[str]
    token_endpoint_auth_method: str = "none"
    grant_types: list[str] = field(default_factory=lambda: ["authorization_code", "refresh_token"])
    response_types: list[str] = field(default_factory=lambda: ["code"])
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class OAuthSession:
    """Temporary session during OAuth flow (before user authenticates)."""

    session_id: str
    client_id: str
    redirect_uri: str
    code_challenge: str
    code_challenge_method: str
    original_state: str
    resource: str | None
    scope: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class AuthorizationCode:
    """Authorization code after successful authentication."""

    code: str
    user_id: str
    user_email: str
    client_id: str
    redirect_uri: str
    code_challenge: str
    resource: str | None
    scope: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class RefreshToken:
    """Long-lived refresh token."""

    token: str
    user_id: str
    user_email: str
    client_id: str
    scope: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
