"""Storage interface for OAuth data."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Mapping, MutableMapping, Protocol, TypeVar

from .models import AuthorizationCode, OAuthSession, RefreshToken, RegisteredClient


class OAuthStorage(Protocol):
    # Clients
    def save_client(self, client: RegisteredClient) -> None:
        ...

    def get_client(self, client_id: str) -> RegisteredClient | None:
        ...

    # OAuth Sessions (TTL: 10 minutes)
    def save_session(self, session: OAuthSession) -> None:
        ...

    def get_session(self, session_id: str) -> OAuthSession | None:
        ...

    def delete_session(self, session_id: str) -> None:
        ...

    # Authorization Codes (TTL: 5 minutes)
    def save_auth_code(self, code: AuthorizationCode) -> None:
        ...

    def get_auth_code(self, code: str) -> AuthorizationCode | None:
        ...

    def delete_auth_code(self, code: str) -> None:
        ...

    # Refresh Tokens (TTL: 7 days)
    def save_refresh_token(self, token: RefreshToken) -> None:
        ...

    def get_refresh_token(self, token: str) -> RefreshToken | None:
        ...

    def delete_refresh_token(self, token: str) -> None:
        ...


class HasCreatedAt(Protocol):
    created_at: datetime


T = TypeVar("T", bound=HasCreatedAt)


class InMemoryStorage:
    """Simple in-memory implementation. Replace with Redis for production."""

    SESSION_TTL = timedelta(minutes=10)
    AUTH_CODE_TTL = timedelta(minutes=5)
    REFRESH_TOKEN_TTL = timedelta(days=7)

    def __init__(self) -> None:
        self._clients: dict[str, RegisteredClient] = {}
        self._sessions: dict[str, OAuthSession] = {}
        self._auth_codes: dict[str, AuthorizationCode] = {}
        self._refresh_tokens: dict[str, RefreshToken] = {}

    def save_client(self, client: RegisteredClient) -> None:
        self._clients[client.client_id] = client

    def get_client(self, client_id: str) -> RegisteredClient | None:
        return self._clients.get(client_id)

    def save_session(self, session: OAuthSession) -> None:
        self._sessions[session.session_id] = session

    def get_session(self, session_id: str) -> OAuthSession | None:
        return self._get_with_ttl(self._sessions, session_id, self.SESSION_TTL)

    def delete_session(self, session_id: str) -> None:
        self._delete_token(self._sessions, session_id)

    def save_auth_code(self, code: AuthorizationCode) -> None:
        self._auth_codes[code.code] = code

    def get_auth_code(self, code: str) -> AuthorizationCode | None:
        return self._get_with_ttl(self._auth_codes, code, self.AUTH_CODE_TTL)

    def delete_auth_code(self, code: str) -> None:
        self._delete_token(self._auth_codes, code)

    def save_refresh_token(self, token: RefreshToken) -> None:
        self._refresh_tokens[token.token] = token

    def get_refresh_token(self, token: str) -> RefreshToken | None:
        return self._get_with_ttl(self._refresh_tokens, token, self.REFRESH_TOKEN_TTL)

    def delete_refresh_token(self, token: str) -> None:
        self._delete_token(self._refresh_tokens, token)

    def _get_with_ttl(
        self,
        storage: MutableMapping[str, T],
        token: str,
        ttl: timedelta,
    ) -> T | None:
        key, item = self._lookup_token(storage, token)
        if item is None:
            return None
        if self._is_expired(item.created_at, ttl):
            if key is not None:
                storage.pop(key, None)
            return None
        return item

    def _delete_token(self, storage: MutableMapping[str, T], token: str) -> None:
        key, _item = self._lookup_token(storage, token)
        if key is not None:
            storage.pop(key, None)

    @staticmethod
    def _is_expired(created_at: datetime, ttl: timedelta) -> bool:
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - created_at > ttl

    @staticmethod
    def _lookup_token(storage: Mapping[str, T], token: str) -> tuple[str | None, T | None]:
        for key, value in storage.items():
            if secrets.compare_digest(key, token):
                return key, value
        return None, None
