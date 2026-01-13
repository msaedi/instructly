from types import SimpleNamespace
from unittest.mock import Mock

from jwt import PyJWTError

import app.auth_session as auth_session


def test_decode_email_returns_subject(monkeypatch):
    monkeypatch.setattr(auth_session, "decode_access_token", lambda token: {"sub": "user@example.com"})
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


def test_lookup_active_user_inactive_or_missing():
    db = Mock()
    db.query.return_value.filter.return_value.first.return_value = None
    assert auth_session._lookup_active_user("", db) is None
    assert auth_session._lookup_active_user("user@example.com", db) is None


def test_lookup_active_user_active():
    user = SimpleNamespace(is_active=True, email="user@example.com")
    db = Mock()
    db.query.return_value.filter.return_value.first.return_value = user
    assert auth_session._lookup_active_user("user@example.com", db) is user


def test_get_user_from_session_cookie_returns_user(monkeypatch):
    user = SimpleNamespace(email="user@example.com", is_active=True)
    request = SimpleNamespace(cookies={"sid": "token"})

    monkeypatch.setattr(auth_session, "session_cookie_candidates", lambda: ["sid"])
    monkeypatch.setattr(auth_session, "_decode_email", lambda token: "user@example.com")
    monkeypatch.setattr(auth_session, "_lookup_active_user", lambda email, db: user)

    result = auth_session.get_user_from_session_cookie(request, db=SimpleNamespace())

    assert result is user


def test_get_user_from_session_cookie_returns_none_when_missing():
    request = SimpleNamespace(cookies={})
    result = auth_session.get_user_from_session_cookie(request, db=SimpleNamespace())

    assert result is None


def test_get_user_from_bearer_header_returns_user(monkeypatch):
    user = SimpleNamespace(email="user@example.com", is_active=True)
    request = SimpleNamespace(headers={"authorization": "Bearer token"})

    monkeypatch.setattr(auth_session, "_decode_email", lambda token: "user@example.com")
    monkeypatch.setattr(auth_session, "_lookup_active_user", lambda email, db: user)

    result = auth_session.get_user_from_bearer_header(request, db=SimpleNamespace())

    assert result is user


def test_get_user_from_bearer_header_invalid_prefix():
    request = SimpleNamespace(headers={"authorization": "Token abc"})
    assert auth_session.get_user_from_bearer_header(request, db=SimpleNamespace()) is None


def test_get_user_from_bearer_header_missing_token():
    request = SimpleNamespace(headers={"authorization": "Bearer "})
    assert auth_session.get_user_from_bearer_header(request, db=SimpleNamespace()) is None
