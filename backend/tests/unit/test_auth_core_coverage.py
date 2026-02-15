# backend/tests/unit/test_auth_core_coverage.py
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re

import jwt
from jwt import InvalidIssuerError
import pytest

import app.auth as auth_module
from app.auth import (
    create_access_token,
    decode_access_token,
    get_current_user,
    get_current_user_optional,
    get_password_hash_async,
    password_needs_rehash,
    verify_password,
    verify_password_async,
)
from app.core.config import secret_or_plain, settings
from app.utils.cookies import session_cookie_candidates
from app.utils.token_utils import parse_token_iat

TEST_USER_ULID = "01ARZ3NDEKTSV4RRFFQ69G5FAV"


class _Secret:
    def __init__(self, value: str):
        self._value = value

    def get_secret_value(self) -> str:
        return self._value


class _BrokenSecret:
    def get_secret_value(self) -> str:
        raise RuntimeError("secret backend unavailable")


class _NeverRevokedService:
    async def is_revoked(self, _jti: str) -> bool:
        return False


def _make_request_with_cookie(cookie_name: str, token: str):
    cookie_header = f"{cookie_name}={token}".encode()
    return auth_module.Request(
        {
            "type": "http",
            "headers": [(b"cookie", cookie_header)],
            "client": ("127.0.0.1", 1234),
            "path": "/",
        }
    )


def test_secret_or_plain_falls_back_to_raw_string():
    assert secret_or_plain("plain") == "plain"


def test_secret_or_plain_raises_when_secret_resolution_fails():
    with pytest.raises(ValueError, match="Failed to resolve secret"):
        secret_or_plain(_BrokenSecret())


def test_verify_password_invalid_hash_logs(monkeypatch):
    from argon2.exceptions import InvalidHashError

    class _Hasher:
        def verify(self, *_args, **_kwargs):
            raise InvalidHashError("bad")

    monkeypatch.setattr(auth_module, "_password_hasher", _Hasher())
    assert verify_password("plain", "not-a-hash") is False


def test_verify_password_generic_error(monkeypatch):
    class _Hasher:
        def verify(self, *_args, **_kwargs):
            raise RuntimeError("boom")

    monkeypatch.setattr(auth_module, "_password_hasher", _Hasher())
    assert verify_password("plain", "hash") is False


@pytest.mark.asyncio
async def test_verify_password_async_handles_executor_error(monkeypatch):
    class _Loop:
        def run_in_executor(self, *_args, **_kwargs):
            raise RuntimeError("boom")

    monkeypatch.setattr(auth_module.asyncio, "get_running_loop", lambda: _Loop())
    result = await verify_password_async("plain", "hash")
    assert result is False


@pytest.mark.asyncio
async def test_get_password_hash_async_returns_hash():
    hashed = await get_password_hash_async("password")
    assert isinstance(hashed, str)
    assert hashed.startswith("$argon2id$")


def test_password_needs_rehash_error(monkeypatch):
    class _Hasher:
        def check_needs_rehash(self, *_args, **_kwargs):
            raise RuntimeError("boom")

    monkeypatch.setattr(auth_module, "_password_hasher", _Hasher())
    assert password_needs_rehash("hash") is False


def test_token_claim_requirements_preview(monkeypatch):
    monkeypatch.setenv("SITE_MODE", "preview")
    monkeypatch.setattr(settings, "is_testing", False)
    enforce, expected_aud, expected_iss = auth_module._token_claim_requirements()
    assert enforce is True
    assert expected_aud == "preview"
    assert expected_iss == f"https://{settings.preview_api_domain}"


def test_token_claim_requirements_env_error(monkeypatch):
    def _boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(auth_module.os, "getenv", _boom)
    enforce, expected_aud, expected_iss = auth_module._token_claim_requirements()
    assert enforce is False
    assert expected_aud is None
    assert expected_iss is None


def test_token_claim_requirements_prod(monkeypatch):
    monkeypatch.setenv("SITE_MODE", "prod")
    monkeypatch.setattr(settings, "is_testing", False, raising=False)
    enforce, expected_aud, expected_iss = auth_module._token_claim_requirements()
    assert enforce is True
    assert expected_aud == "prod"
    assert expected_iss == f"https://{settings.prod_api_domain}"


def test_decode_access_token_invalid_issuer(monkeypatch):
    monkeypatch.setenv("SITE_MODE", "preview")
    monkeypatch.setattr(settings, "is_testing", False, raising=False)
    token = jwt.encode(
        {
            "sub": "user@example.com",
            "aud": "preview",
            "iss": "https://wrong.example.com",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        },
        secret_or_plain(settings.secret_key),
        algorithm=settings.algorithm,
    )
    with pytest.raises(InvalidIssuerError):
        decode_access_token(token, enforce_audience=True)


def test_decode_access_token_enforce_success(monkeypatch):
    monkeypatch.setenv("SITE_MODE", "preview")
    monkeypatch.setattr(settings, "is_testing", False, raising=False)
    token = jwt.encode(
        {
            "sub": "user@example.com",
            "aud": "preview",
            "iss": f"https://{settings.preview_api_domain}",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        },
        secret_or_plain(settings.secret_key),
        algorithm=settings.algorithm,
    )
    payload = decode_access_token(token, enforce_audience=True)
    assert payload["sub"] == "user@example.com"


def test_create_access_token_includes_env_claims(monkeypatch):
    monkeypatch.setenv("SITE_MODE", "preview")
    token = create_access_token({"sub": TEST_USER_ULID, "email": "user@example.com"})
    decoded = jwt.decode(
        token,
        secret_or_plain(settings.secret_key),
        algorithms=[settings.algorithm],
        audience="preview",
    )
    assert decoded["iss"] == f"https://{settings.preview_api_domain}"
    assert decoded["sub"] == TEST_USER_ULID
    assert decoded["email"] == "user@example.com"
    assert isinstance(decoded.get("iat"), int)
    assert re.fullmatch(r"[0-9A-HJKMNP-TV-Z]{26}", decoded.get("jti", ""))

    monkeypatch.setenv("SITE_MODE", "prod")
    token = create_access_token({"sub": TEST_USER_ULID, "email": "user@example.com"})
    decoded = jwt.decode(
        token,
        secret_or_plain(settings.secret_key),
        algorithms=[settings.algorithm],
        audience="prod",
    )
    assert decoded["iss"] == f"https://{settings.prod_api_domain}"


def test_create_access_token_with_expiry_and_beta_claims(monkeypatch):
    monkeypatch.setenv("SITE_MODE", "prod")
    token = create_access_token(
        {"sub": TEST_USER_ULID, "email": "user@example.com"},
        expires_delta=timedelta(minutes=5),
        beta_claims={"beta_access": True},
    )
    decoded = jwt.decode(
        token,
        secret_or_plain(settings.secret_key),
        algorithms=[settings.algorithm],
        audience="prod",
    )
    assert decoded["beta_access"] is True
    assert decoded["iss"] == f"https://{settings.prod_api_domain}"


def test_create_access_token_handles_env_error(monkeypatch):
    def _boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(auth_module.os, "getenv", _boom)
    token = create_access_token({"sub": TEST_USER_ULID, "email": "user@example.com"})
    decoded = jwt.decode(
        token,
        secret_or_plain(settings.secret_key),
        algorithms=[settings.algorithm],
        options={"verify_aud": False},
    )
    assert decoded.get("iss") is None
    assert decoded.get("aud") is None


def test_create_access_token_jti_is_unique():
    token_1 = create_access_token({"sub": TEST_USER_ULID, "email": "user@example.com"})
    token_2 = create_access_token({"sub": TEST_USER_ULID, "email": "user@example.com"})
    decoded_1 = jwt.decode(
        token_1,
        secret_or_plain(settings.secret_key),
        algorithms=[settings.algorithm],
        options={"verify_aud": False},
    )
    decoded_2 = jwt.decode(
        token_2,
        secret_or_plain(settings.secret_key),
        algorithms=[settings.algorithm],
        options={"verify_aud": False},
    )
    assert decoded_1["jti"] != decoded_2["jti"]


def test_create_temp_token_uses_temp_secret(monkeypatch):
    monkeypatch.setattr(
        settings,
        "temp_token_secret",
        _Secret("temp-secret-key-for-testing-32bytes!"),
        raising=False,
    )
    token = auth_module.create_temp_token({"sub": "user@example.com"})
    decoded = jwt.decode(
        token,
        "temp-secret-key-for-testing-32bytes!",
        algorithms=[settings.algorithm],
        audience=settings.temp_token_aud,
    )
    assert decoded["iss"] == settings.temp_token_iss


@pytest.mark.asyncio
async def test_get_current_user_cookie_fallback(monkeypatch):
    monkeypatch.setenv("SITE_MODE", "preview")
    monkeypatch.setattr(auth_module, "TokenBlacklistService", lambda: _NeverRevokedService())

    async def _lookup_none(_user_id):
        return None

    monkeypatch.setattr(auth_module, "lookup_user_by_id_nonblocking", _lookup_none)
    token = create_access_token({"sub": TEST_USER_ULID, "email": "user@example.com"})
    cookie_name = session_cookie_candidates("preview")[0]
    request = _make_request_with_cookie(cookie_name, token)
    result = await get_current_user(request, token=None)
    assert result == TEST_USER_ULID


@pytest.mark.asyncio
async def test_get_current_user_missing_token_raises():
    request = auth_module.Request({"type": "http", "headers": [], "client": ("1.1.1.1", 1234), "path": "/"})
    with pytest.raises(auth_module.HTTPException) as exc:
        await get_current_user(request, token=None)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_invalid_token_raises():
    request = auth_module.Request({"type": "http", "headers": [], "client": ("1.1.1.1", 1234), "path": "/"})
    with pytest.raises(auth_module.HTTPException):
        await get_current_user(request, token="bad-token")


@pytest.mark.asyncio
async def test_get_current_user_unexpected_error(monkeypatch):
    request = auth_module.Request({"type": "http", "headers": [], "client": ("1.1.1.1", 1234), "path": "/"})
    monkeypatch.setattr(auth_module, "decode_access_token", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")))
    with pytest.raises(auth_module.HTTPException):
        await get_current_user(request, token="token")


@pytest.mark.asyncio
async def test_get_current_user_missing_sub_raises(monkeypatch):
    monkeypatch.setenv("SITE_MODE", "local")
    token = jwt.encode(
        {
            "sub": 123,
            "jti": "legacy-test-jti",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        },
        secret_or_plain(settings.secret_key),
        algorithm=settings.algorithm,
    )
    request = auth_module.Request({"type": "http", "headers": [], "client": ("1.1.1.1", 1234), "path": "/"})
    with pytest.raises(auth_module.HTTPException):
        await get_current_user(request, token=token)


@pytest.mark.asyncio
async def test_get_current_user_rejects_token_without_jti(monkeypatch):
    monkeypatch.setenv("SITE_MODE", "local")
    rejection_calls: list[str] = []
    monkeypatch.setattr(
        auth_module.prometheus_metrics,
        "record_token_rejection",
        lambda reason: rejection_calls.append(reason),
    )
    token = jwt.encode(
        {"sub": TEST_USER_ULID, "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
        secret_or_plain(settings.secret_key),
        algorithm=settings.algorithm,
    )
    request = auth_module.Request({"type": "http", "headers": [], "client": ("1.1.1.1", 1234), "path": "/"})
    with pytest.raises(auth_module.HTTPException) as exc:
        await get_current_user(request, token=token)
    assert exc.value.status_code == 401
    assert exc.value.detail == "Token format outdated, please re-login"
    assert rejection_calls == ["format_outdated"]


@pytest.mark.asyncio
async def test_get_current_user_rejects_revoked_token(monkeypatch):
    monkeypatch.setenv("SITE_MODE", "local")
    rejection_calls: list[str] = []
    monkeypatch.setattr(
        auth_module.prometheus_metrics,
        "record_token_rejection",
        lambda reason: rejection_calls.append(reason),
    )

    class _RevokedService:
        async def is_revoked(self, _jti: str) -> bool:
            return True

    monkeypatch.setattr(auth_module, "TokenBlacklistService", lambda: _RevokedService())
    token = create_access_token({"sub": TEST_USER_ULID, "email": "user@example.com"})
    request = auth_module.Request({"type": "http", "headers": [], "client": ("1.1.1.1", 1234), "path": "/"})

    with pytest.raises(auth_module.HTTPException) as exc:
        await get_current_user(request, token=token)

    assert exc.value.status_code == 401
    assert exc.value.detail == "Token has been revoked"
    assert rejection_calls == ["revoked"]


@pytest.mark.asyncio
async def test_get_current_user_fail_closed_when_blacklist_check_errors(monkeypatch):
    monkeypatch.setenv("SITE_MODE", "local")

    class _ErrorService:
        async def is_revoked(self, _jti: str) -> bool:
            raise RuntimeError("redis down")

    monkeypatch.setattr(auth_module, "TokenBlacklistService", lambda: _ErrorService())
    token = create_access_token({"sub": TEST_USER_ULID, "email": "user@example.com"})
    request = auth_module.Request({"type": "http", "headers": [], "client": ("1.1.1.1", 1234), "path": "/"})

    with pytest.raises(auth_module.HTTPException) as exc:
        await get_current_user(request, token=token)

    assert exc.value.status_code == 401
    assert exc.value.detail == "Token has been revoked"


@pytest.mark.asyncio
async def test_get_current_user_rejects_token_invalidated_by_user_timestamp(monkeypatch):
    monkeypatch.setenv("SITE_MODE", "local")
    monkeypatch.setattr(auth_module, "TokenBlacklistService", lambda: _NeverRevokedService())
    rejection_calls: list[str] = []
    monkeypatch.setattr(
        auth_module.prometheus_metrics,
        "record_token_rejection",
        lambda reason: rejection_calls.append(reason),
    )

    token = create_access_token({"sub": TEST_USER_ULID, "email": "user@example.com"})
    decoded = jwt.decode(
        token,
        secret_or_plain(settings.secret_key),
        algorithms=[settings.algorithm],
        options={"verify_aud": False},
    )
    iat_ts = int(decoded["iat"])

    async def _lookup_by_id(_user_id):
        return {"id": TEST_USER_ULID, "tokens_valid_after_ts": iat_ts + 10}

    monkeypatch.setattr(auth_module, "lookup_user_by_id_nonblocking", _lookup_by_id)
    request = auth_module.Request({"type": "http", "headers": [], "client": ("1.1.1.1", 1234), "path": "/"})

    with pytest.raises(auth_module.HTTPException) as exc:
        await get_current_user(request, token=token)

    assert exc.value.status_code == 401
    assert exc.value.detail == "Token has been invalidated"
    assert rejection_calls == ["invalidated"]


@pytest.mark.asyncio
async def test_get_current_user_allows_token_when_user_timestamp_is_before_iat(monkeypatch):
    monkeypatch.setenv("SITE_MODE", "local")
    monkeypatch.setattr(auth_module, "TokenBlacklistService", lambda: _NeverRevokedService())

    token = create_access_token({"sub": TEST_USER_ULID, "email": "user@example.com"})
    decoded = jwt.decode(
        token,
        secret_or_plain(settings.secret_key),
        algorithms=[settings.algorithm],
        options={"verify_aud": False},
    )
    iat_ts = int(decoded["iat"])

    async def _lookup_by_id(_user_id):
        return {"id": TEST_USER_ULID, "tokens_valid_after_ts": iat_ts - 10}

    monkeypatch.setattr(auth_module, "lookup_user_by_id_nonblocking", _lookup_by_id)
    request = auth_module.Request({"type": "http", "headers": [], "client": ("1.1.1.1", 1234), "path": "/"})

    assert await get_current_user(request, token=token) == TEST_USER_ULID


@pytest.mark.asyncio
async def test_get_current_user_allows_token_when_tokens_valid_after_missing(monkeypatch):
    monkeypatch.setenv("SITE_MODE", "local")
    monkeypatch.setattr(auth_module, "TokenBlacklistService", lambda: _NeverRevokedService())

    async def _lookup_by_id(_user_id):
        return {"id": TEST_USER_ULID, "tokens_valid_after_ts": None}

    monkeypatch.setattr(auth_module, "lookup_user_by_id_nonblocking", _lookup_by_id)

    token = create_access_token({"sub": TEST_USER_ULID, "email": "user@example.com"})
    request = auth_module.Request({"type": "http", "headers": [], "client": ("1.1.1.1", 1234), "path": "/"})
    assert await get_current_user(request, token=token) == TEST_USER_ULID


@pytest.mark.asyncio
async def test_get_current_user_optional_invalid_token():
    request = auth_module.Request({"type": "http", "headers": [], "client": ("1.1.1.1", 1234), "path": "/"})
    result = await get_current_user_optional(request, token="bad-token")
    assert result is None


@pytest.mark.asyncio
async def test_get_current_user_optional_cookie_fallback(monkeypatch):
    monkeypatch.setenv("SITE_MODE", "preview")
    monkeypatch.setattr(auth_module, "TokenBlacklistService", lambda: _NeverRevokedService())

    async def _lookup_none(_user_id):
        return None

    monkeypatch.setattr(auth_module, "lookup_user_by_id_nonblocking", _lookup_none)
    token = create_access_token({"sub": TEST_USER_ULID, "email": "user@example.com"})
    cookie_name = session_cookie_candidates("preview")[0]
    request = _make_request_with_cookie(cookie_name, token)
    result = await get_current_user_optional(request, token=None)
    assert result == TEST_USER_ULID


@pytest.mark.asyncio
async def test_get_current_user_optional_env_error_returns_none(monkeypatch):
    monkeypatch.setattr(auth_module.os, "getenv", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")))
    request = auth_module.Request({"type": "http", "headers": [], "client": ("1.1.1.1", 1234), "path": "/"})
    assert await get_current_user_optional(request, token=None) is None


@pytest.mark.asyncio
async def test_get_current_user_optional_returns_none_for_outdated_format_token(monkeypatch):
    monkeypatch.setenv("SITE_MODE", "local")
    token = jwt.encode(
        {"sub": TEST_USER_ULID, "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
        secret_or_plain(settings.secret_key),
        algorithm=settings.algorithm,
    )
    request = auth_module.Request({"type": "http", "headers": [], "client": ("1.1.1.1", 1234), "path": "/"})
    assert await get_current_user_optional(request, token=token) is None


@pytest.mark.asyncio
async def test_get_current_user_optional_returns_none_for_revoked_token(monkeypatch):
    monkeypatch.setenv("SITE_MODE", "local")

    class _RevokedService:
        async def is_revoked(self, _jti: str) -> bool:
            return True

    monkeypatch.setattr(auth_module, "TokenBlacklistService", lambda: _RevokedService())
    token = create_access_token({"sub": TEST_USER_ULID, "email": "user@example.com"})
    request = auth_module.Request({"type": "http", "headers": [], "client": ("1.1.1.1", 1234), "path": "/"})

    assert await get_current_user_optional(request, token=token) is None


@pytest.mark.asyncio
async def test_get_current_user_optional_returns_none_for_invalidated_token(monkeypatch):
    monkeypatch.setenv("SITE_MODE", "local")
    monkeypatch.setattr(auth_module, "TokenBlacklistService", lambda: _NeverRevokedService())

    token = create_access_token({"sub": TEST_USER_ULID, "email": "user@example.com"})
    decoded = jwt.decode(
        token,
        secret_or_plain(settings.secret_key),
        algorithms=[settings.algorithm],
        options={"verify_aud": False},
    )
    iat_ts = int(decoded["iat"])

    async def _lookup_by_id(_user_id):
        return {"id": TEST_USER_ULID, "tokens_valid_after_ts": iat_ts + 10}

    monkeypatch.setattr(auth_module, "lookup_user_by_id_nonblocking", _lookup_by_id)
    request = auth_module.Request({"type": "http", "headers": [], "client": ("1.1.1.1", 1234), "path": "/"})

    assert await get_current_user_optional(request, token=token) is None


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"iat": 123}, 123),
        ({"iat": 123.9}, 123),
        ({"iat": "456"}, 456),
        ({"iat": "bad"}, None),
        ({}, None),
    ],
)
def test_parse_iat_claim_variants(payload, expected):
    assert parse_token_iat(payload) == expected


@pytest.mark.asyncio
async def test_enforce_revocation_missing_jti_ignores_metric_failure(monkeypatch):
    monkeypatch.setattr(
        auth_module.prometheus_metrics,
        "record_token_rejection",
        lambda _reason: (_ for _ in ()).throw(RuntimeError("metrics down")),
    )

    with pytest.raises(auth_module.HTTPException) as exc:
        await auth_module._enforce_revocation_and_user_invalidation(
            payload={"sub": TEST_USER_ULID},
            user_id=TEST_USER_ULID,
        )

    assert exc.value.status_code == 401
    assert exc.value.detail == "Token format outdated, please re-login"


@pytest.mark.asyncio
async def test_enforce_revocation_revoked_ignores_metric_failure(monkeypatch):
    class _RevokedService:
        async def is_revoked(self, _jti: str) -> bool:
            return True

    monkeypatch.setattr(auth_module, "TokenBlacklistService", lambda: _RevokedService())
    monkeypatch.setattr(
        auth_module.prometheus_metrics,
        "record_token_rejection",
        lambda _reason: (_ for _ in ()).throw(RuntimeError("metrics down")),
    )

    with pytest.raises(auth_module.HTTPException) as exc:
        await auth_module._enforce_revocation_and_user_invalidation(
            payload={"sub": TEST_USER_ULID, "jti": "test-jti"},
            user_id=TEST_USER_ULID,
        )

    assert exc.value.status_code == 401
    assert exc.value.detail == "Token has been revoked"


@pytest.mark.asyncio
async def test_enforce_revocation_invalidated_ignores_metric_failure(monkeypatch):
    class _NeverRevoked:
        async def is_revoked(self, _jti: str) -> bool:
            return False

    async def _lookup_user(_user_id: str):
        return {"id": TEST_USER_ULID, "tokens_valid_after_ts": 200}

    monkeypatch.setattr(auth_module, "TokenBlacklistService", lambda: _NeverRevoked())
    monkeypatch.setattr(auth_module, "lookup_user_by_id_nonblocking", _lookup_user)
    monkeypatch.setattr(
        auth_module.prometheus_metrics,
        "record_token_rejection",
        lambda _reason: (_ for _ in ()).throw(RuntimeError("metrics down")),
    )

    with pytest.raises(auth_module.HTTPException) as exc:
        await auth_module._enforce_revocation_and_user_invalidation(
            payload={"sub": TEST_USER_ULID, "jti": "test-jti", "iat": 100},
            user_id=TEST_USER_ULID,
        )

    assert exc.value.status_code == 401
    assert exc.value.detail == "Token has been invalidated"


@pytest.mark.asyncio
async def test_get_current_user_handles_site_mode_env_error(monkeypatch):
    request = auth_module.Request({"type": "http", "headers": [], "client": ("1.1.1.1", 1234), "path": "/"})
    monkeypatch.setattr(auth_module.os, "getenv", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")))

    with pytest.raises(auth_module.HTTPException) as exc:
        await get_current_user(request, token=None)

    assert exc.value.status_code == 401
    assert exc.value.detail == "Not authenticated"


@pytest.mark.asyncio
async def test_get_current_user_optional_handles_unexpected_decode_exception(monkeypatch):
    request = auth_module.Request({"type": "http", "headers": [], "client": ("1.1.1.1", 1234), "path": "/"})
    monkeypatch.setattr(
        auth_module,
        "decode_access_token",
        lambda _token: (_ for _ in ()).throw(RuntimeError("unexpected decode failure")),
    )

    assert await get_current_user_optional(request, token="token") is None
