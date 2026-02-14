from types import SimpleNamespace
from unittest.mock import Mock

from jwt import PyJWTError
import pytest

import app.auth_session as auth_session


def test_decode_subject_returns_subject(monkeypatch):
    user_id = "01ARZ3NDEKTSV4RRFFQ69G5FAV"
    monkeypatch.setattr(
        auth_session,
        "decode_access_token",
        lambda token: {"sub": user_id, "jti": "test-jti", "iat": 123},
    )
    monkeypatch.setattr(
        auth_session.TokenBlacklistService,
        "is_revoked_sync",
        lambda self, _jti: False,
    )
    assert auth_session._decode_subject("token") == user_id


def test_decode_subject_handles_pyjwt_error(monkeypatch):
    def _raise(_token):
        raise PyJWTError("bad")

    monkeypatch.setattr(auth_session, "decode_access_token", _raise)
    assert auth_session._decode_subject("token") is None


def test_decode_subject_handles_empty_token():
    assert auth_session._decode_subject("") is None


def test_decode_subject_handles_generic_exception(monkeypatch):
    def _raise(_token):
        raise RuntimeError("boom")

    monkeypatch.setattr(auth_session, "decode_access_token", _raise)
    assert auth_session._decode_subject("token") is None


def test_decode_subject_rejects_revoked_token(monkeypatch):
    rejection_calls = []
    monkeypatch.setattr(
        auth_session,
        "decode_access_token",
        lambda token: {"sub": "01ARZ3NDEKTSV4RRFFQ69G5FAV", "jti": "test-jti", "iat": 123},
    )
    monkeypatch.setattr(
        auth_session.TokenBlacklistService,
        "is_revoked_sync",
        lambda self, _jti: True,
    )
    monkeypatch.setattr(
        auth_session.prometheus_metrics,
        "record_token_rejection",
        lambda reason: rejection_calls.append(reason),
    )
    assert auth_session._decode_subject("token") is None
    assert rejection_calls == ["revoked"]


def test_decode_subject_rejects_missing_jti_records_metric(monkeypatch):
    rejection_calls = []
    monkeypatch.setattr(
        auth_session,
        "decode_access_token",
        lambda token: {"sub": "01ARZ3NDEKTSV4RRFFQ69G5FAV"},
    )
    monkeypatch.setattr(
        auth_session.prometheus_metrics,
        "record_token_rejection",
        lambda reason: rejection_calls.append(reason),
    )

    assert auth_session._decode_subject("token") is None
    assert rejection_calls == ["format_outdated"]


def test_decode_subject_missing_jti_metric_error_is_non_fatal(monkeypatch):
    monkeypatch.setattr(
        auth_session,
        "decode_access_token",
        lambda token: {"sub": "01ARZ3NDEKTSV4RRFFQ69G5FAV"},
    )
    monkeypatch.setattr(
        auth_session.prometheus_metrics,
        "record_token_rejection",
        lambda _reason: (_ for _ in ()).throw(RuntimeError("metrics down")),
    )

    assert auth_session._decode_subject("token") is None


def test_decode_subject_blacklist_metric_error_is_non_fatal(monkeypatch):
    monkeypatch.setattr(
        auth_session,
        "decode_access_token",
        lambda token: {"sub": "01ARZ3NDEKTSV4RRFFQ69G5FAV", "jti": "test-jti"},
    )
    monkeypatch.setattr(
        auth_session.TokenBlacklistService,
        "is_revoked_sync",
        lambda self, _jti: True,
    )
    monkeypatch.setattr(
        auth_session.prometheus_metrics,
        "record_token_rejection",
        lambda _reason: (_ for _ in ()).throw(RuntimeError("metrics down")),
    )

    assert auth_session._decode_subject("token") is None


def test_decode_subject_blacklist_exception_fail_closed(monkeypatch):
    monkeypatch.setattr(
        auth_session,
        "decode_access_token",
        lambda token: {"sub": "01ARZ3NDEKTSV4RRFFQ69G5FAV", "jti": "test-jti"},
    )

    def _boom(_self, _jti):
        raise RuntimeError("redis bridge failure")

    monkeypatch.setattr(auth_session.TokenBlacklistService, "is_revoked_sync", _boom)

    assert auth_session._decode_subject("token") is None


def test_decode_subject_rejects_non_string_subject(monkeypatch):
    monkeypatch.setattr(
        auth_session,
        "decode_access_token",
        lambda token: {"sub": 123, "jti": "test-jti"},
    )
    monkeypatch.setattr(
        auth_session.TokenBlacklistService,
        "is_revoked_sync",
        lambda self, _jti: False,
    )

    assert auth_session._decode_subject("token") is None


@pytest.mark.parametrize(
    ("iat_value", "expected_iat"),
    [
        (12.9, 12),
        ("123", 123),
        ("bad-int", None),
        (None, None),
    ],
)
def test_decode_subject_parses_iat_variants(monkeypatch, iat_value, expected_iat):
    monkeypatch.setattr(
        auth_session,
        "decode_access_token",
        lambda token: {"sub": "01ARZ3NDEKTSV4RRFFQ69G5FAV", "jti": "test-jti", "iat": iat_value},
    )
    monkeypatch.setattr(
        auth_session.TokenBlacklistService,
        "is_revoked_sync",
        lambda self, _jti: False,
    )

    assert auth_session._decode_token_claims("token") == ("01ARZ3NDEKTSV4RRFFQ69G5FAV", expected_iat)


def test_lookup_active_user_inactive_or_missing(monkeypatch):
    db = Mock()

    class StubRepo:
        def __init__(self, _db):
            pass

        def get_by_id(self, _identifier, use_retry=False):
            return None

    monkeypatch.setattr(auth_session, "UserRepository", StubRepo)
    assert auth_session._lookup_active_user("", db) is None
    assert auth_session._lookup_active_user("01ARZ3NDEKTSV4RRFFQ69G5FAV", db) is None


def test_lookup_active_user_active(monkeypatch):
    user = SimpleNamespace(is_active=True, id="01ARZ3NDEKTSV4RRFFQ69G5FAV")
    db = Mock()

    class StubRepo:
        def __init__(self, _db):
            pass

        def get_by_id(self, _identifier, use_retry=False):
            return user

    monkeypatch.setattr(auth_session, "UserRepository", StubRepo)
    assert auth_session._lookup_active_user("01ARZ3NDEKTSV4RRFFQ69G5FAV", db) is user


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

    monkeypatch.setattr(auth_session, "UserRepository", StubRepo)
    rejection_calls = []
    monkeypatch.setattr(
        auth_session.prometheus_metrics,
        "record_token_rejection",
        lambda reason: rejection_calls.append(reason),
    )
    assert (
        auth_session._lookup_active_user("01ARZ3NDEKTSV4RRFFQ69G5FAV", db, token_iat=100)
        is None
    )
    assert rejection_calls == ["invalidated"]


def test_get_user_from_session_cookie_returns_user(monkeypatch):
    user_id = "01ARZ3NDEKTSV4RRFFQ69G5FAV"
    user = SimpleNamespace(id=user_id, is_active=True)
    request = SimpleNamespace(cookies={"sid": "token"})

    monkeypatch.setattr(auth_session, "session_cookie_candidates", lambda: ["sid"])
    monkeypatch.setattr(
        auth_session,
        "_decode_token_claims",
        lambda token: (user_id, 123),
    )
    monkeypatch.setattr(auth_session, "_lookup_active_user", lambda identifier, db, token_iat=None: user)

    result = auth_session.get_user_from_session_cookie(request, db=SimpleNamespace())

    assert result is user


def test_get_user_from_session_cookie_returns_none_when_missing():
    request = SimpleNamespace(cookies={})
    result = auth_session.get_user_from_session_cookie(request, db=SimpleNamespace())

    assert result is None


def test_get_user_from_session_cookie_skips_invalid_cookie_and_uses_next(monkeypatch):
    request = SimpleNamespace(cookies={"sid": "bad", "__Host-session": "good"})
    user = SimpleNamespace(id="01ARZ3NDEKTSV4RRFFQ69G5FAV", is_active=True)

    monkeypatch.setattr(auth_session, "session_cookie_candidates", lambda: ["sid", "__Host-session"])
    monkeypatch.setattr(
        auth_session,
        "_decode_token_claims",
        lambda token: None if token == "bad" else ("01ARZ3NDEKTSV4RRFFQ69G5FAV", 123),
    )
    monkeypatch.setattr(auth_session, "_lookup_active_user", lambda identifier, db, token_iat=None: user)

    result = auth_session.get_user_from_session_cookie(request, db=SimpleNamespace())
    assert result is user


def test_get_user_from_bearer_header_returns_user(monkeypatch):
    user_id = "01ARZ3NDEKTSV4RRFFQ69G5FAV"
    user = SimpleNamespace(id=user_id, is_active=True)
    request = SimpleNamespace(headers={"authorization": "Bearer token"})

    monkeypatch.setattr(
        auth_session,
        "_decode_token_claims",
        lambda token: (user_id, 123),
    )
    monkeypatch.setattr(auth_session, "_lookup_active_user", lambda identifier, db, token_iat=None: user)

    result = auth_session.get_user_from_bearer_header(request, db=SimpleNamespace())

    assert result is user


def test_get_user_from_bearer_header_invalid_prefix():
    request = SimpleNamespace(headers={"authorization": "Token abc"})
    assert auth_session.get_user_from_bearer_header(request, db=SimpleNamespace()) is None


def test_get_user_from_bearer_header_missing_token():
    request = SimpleNamespace(headers={"authorization": "Bearer "})
    assert auth_session.get_user_from_bearer_header(request, db=SimpleNamespace()) is None


def test_get_user_from_bearer_header_returns_none_when_claims_invalid(monkeypatch):
    request = SimpleNamespace(headers={"authorization": "Bearer token"})
    monkeypatch.setattr(auth_session, "_decode_token_claims", lambda _token: None)

    assert auth_session.get_user_from_bearer_header(request, db=SimpleNamespace()) is None
