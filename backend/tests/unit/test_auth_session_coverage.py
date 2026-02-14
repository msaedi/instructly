from types import SimpleNamespace
from unittest.mock import Mock

from jwt import PyJWTError

import app.auth_session as auth_session


def test_decode_email_returns_subject(monkeypatch):
    monkeypatch.setattr(
        auth_session,
        "decode_access_token",
        lambda token: {"sub": "user@example.com", "jti": "test-jti", "iat": 123},
    )
    monkeypatch.setattr(
        auth_session.TokenBlacklistService,
        "is_revoked_sync",
        lambda self, _jti: False,
    )
    assert auth_session._decode_email("token") == "user@example.com"


def test_decode_email_handles_pyjwt_error(monkeypatch):
    def _raise(_token):
        raise PyJWTError("bad")

    monkeypatch.setattr(auth_session, "decode_access_token", _raise)
    assert auth_session._decode_email("token") is None


def test_decode_email_handles_empty_token():
    assert auth_session._decode_email("") is None


def test_decode_email_handles_generic_exception(monkeypatch):
    def _raise(_token):
        raise RuntimeError("boom")

    monkeypatch.setattr(auth_session, "decode_access_token", _raise)
    assert auth_session._decode_email("token") is None


def test_decode_email_rejects_revoked_token(monkeypatch):
    monkeypatch.setattr(
        auth_session,
        "decode_access_token",
        lambda token: {"sub": "user@example.com", "jti": "test-jti", "iat": 123},
    )
    monkeypatch.setattr(
        auth_session.TokenBlacklistService,
        "is_revoked_sync",
        lambda self, _jti: True,
    )
    assert auth_session._decode_email("token") is None


def test_lookup_active_user_inactive_or_missing(monkeypatch):
    db = Mock()

    class StubRepo:
        def __init__(self, _db):
            pass

        def get_by_id(self, _identifier, use_retry=False):
            return None

        def get_by_email(self, _identifier):
            return None

    monkeypatch.setattr(auth_session, "UserRepository", StubRepo)
    assert auth_session._lookup_active_user("", db) is None
    assert auth_session._lookup_active_user("user@example.com", db) is None


def test_lookup_active_user_active(monkeypatch):
    user = SimpleNamespace(is_active=True, email="user@example.com")
    db = Mock()

    class StubRepo:
        def __init__(self, _db):
            pass

        def get_by_id(self, _identifier, use_retry=False):
            return None

        def get_by_email(self, _identifier):
            return user

    monkeypatch.setattr(auth_session, "UserRepository", StubRepo)
    assert auth_session._lookup_active_user("user@example.com", db) is user


def test_lookup_active_user_rejects_invalidated_token(monkeypatch):
    user = SimpleNamespace(
        is_active=True,
        email="user@example.com",
        tokens_valid_after=SimpleNamespace(timestamp=lambda: 200),
    )
    db = Mock()

    class StubRepo:
        def __init__(self, _db):
            pass

        def get_by_id(self, _identifier, use_retry=False):
            return user

        def get_by_email(self, _identifier):
            return user

    monkeypatch.setattr(auth_session, "UserRepository", StubRepo)
    assert auth_session._lookup_active_user("user@example.com", db, token_iat=100) is None


def test_get_user_from_session_cookie_returns_user(monkeypatch):
    user = SimpleNamespace(email="user@example.com", is_active=True)
    request = SimpleNamespace(cookies={"sid": "token"})

    monkeypatch.setattr(auth_session, "session_cookie_candidates", lambda: ["sid"])
    monkeypatch.setattr(
        auth_session,
        "_decode_token_claims",
        lambda token: ("user@example.com", 123),
    )
    monkeypatch.setattr(auth_session, "_lookup_active_user", lambda email, db, token_iat=None: user)

    result = auth_session.get_user_from_session_cookie(request, db=SimpleNamespace())

    assert result is user


def test_get_user_from_session_cookie_returns_none_when_missing():
    request = SimpleNamespace(cookies={})
    result = auth_session.get_user_from_session_cookie(request, db=SimpleNamespace())

    assert result is None


def test_get_user_from_bearer_header_returns_user(monkeypatch):
    user = SimpleNamespace(email="user@example.com", is_active=True)
    request = SimpleNamespace(headers={"authorization": "Bearer token"})

    monkeypatch.setattr(
        auth_session,
        "_decode_token_claims",
        lambda token: ("user@example.com", 123),
    )
    monkeypatch.setattr(auth_session, "_lookup_active_user", lambda email, db, token_iat=None: user)

    result = auth_session.get_user_from_bearer_header(request, db=SimpleNamespace())

    assert result is user


def test_get_user_from_bearer_header_invalid_prefix():
    request = SimpleNamespace(headers={"authorization": "Token abc"})
    assert auth_session.get_user_from_bearer_header(request, db=SimpleNamespace()) is None


def test_get_user_from_bearer_header_missing_token():
    request = SimpleNamespace(headers={"authorization": "Bearer "})
    assert auth_session.get_user_from_bearer_header(request, db=SimpleNamespace()) is None
