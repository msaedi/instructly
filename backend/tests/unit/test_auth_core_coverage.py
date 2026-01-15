# backend/tests/unit/test_auth_core_coverage.py
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
from jwt import InvalidIssuerError
import pytest

import app.auth as auth_module
from app.auth import (
    _secret_value,
    create_access_token,
    decode_access_token,
    get_current_user,
    get_current_user_optional,
    get_password_hash_async,
    password_needs_rehash,
    verify_password,
    verify_password_async,
)
from app.core.config import settings
from app.utils.cookies import session_cookie_candidates


class _Secret:
    def __init__(self, value: str):
        self._value = value

    def get_secret_value(self) -> str:
        return self._value


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


def test_secret_value_falls_back_to_raw_string():
    assert _secret_value("plain") == "plain"


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
        _secret_value(settings.secret_key),
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
        _secret_value(settings.secret_key),
        algorithm=settings.algorithm,
    )
    payload = decode_access_token(token, enforce_audience=True)
    assert payload["sub"] == "user@example.com"


def test_create_access_token_includes_env_claims(monkeypatch):
    monkeypatch.setenv("SITE_MODE", "preview")
    token = create_access_token({"sub": "user@example.com"})
    decoded = jwt.decode(
        token,
        _secret_value(settings.secret_key),
        algorithms=[settings.algorithm],
        audience="preview",
    )
    assert decoded["iss"] == f"https://{settings.preview_api_domain}"

    monkeypatch.setenv("SITE_MODE", "prod")
    token = create_access_token({"sub": "user@example.com"})
    decoded = jwt.decode(
        token,
        _secret_value(settings.secret_key),
        algorithms=[settings.algorithm],
        audience="prod",
    )
    assert decoded["iss"] == f"https://{settings.prod_api_domain}"


def test_create_access_token_with_expiry_and_beta_claims(monkeypatch):
    monkeypatch.setenv("SITE_MODE", "prod")
    token = create_access_token(
        {"sub": "user@example.com"},
        expires_delta=timedelta(minutes=5),
        beta_claims={"beta_access": True},
    )
    decoded = jwt.decode(
        token,
        _secret_value(settings.secret_key),
        algorithms=[settings.algorithm],
        audience="prod",
    )
    assert decoded["beta_access"] is True
    assert decoded["iss"] == f"https://{settings.prod_api_domain}"


def test_create_access_token_handles_env_error(monkeypatch):
    def _boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(auth_module.os, "getenv", _boom)
    token = create_access_token({"sub": "user@example.com"})
    decoded = jwt.decode(
        token,
        _secret_value(settings.secret_key),
        algorithms=[settings.algorithm],
        options={"verify_aud": False},
    )
    assert decoded.get("iss") is None
    assert decoded.get("aud") is None


def test_create_temp_token_uses_temp_secret(monkeypatch):
    monkeypatch.setattr(settings, "temp_token_secret", _Secret("temp-secret"), raising=False)
    token = auth_module.create_temp_token({"sub": "user@example.com"})
    decoded = jwt.decode(
        token,
        "temp-secret",
        algorithms=[settings.algorithm],
        audience=settings.temp_token_aud,
    )
    assert decoded["iss"] == settings.temp_token_iss


@pytest.mark.asyncio
async def test_get_current_user_cookie_fallback(monkeypatch):
    monkeypatch.setenv("SITE_MODE", "preview")
    token = create_access_token({"sub": "user@example.com"})
    cookie_name = session_cookie_candidates("preview")[0]
    request = _make_request_with_cookie(cookie_name, token)
    result = await get_current_user(request, token=None)
    assert result == "user@example.com"


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
        {"sub": 123, "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
        _secret_value(settings.secret_key),
        algorithm=settings.algorithm,
    )
    request = auth_module.Request({"type": "http", "headers": [], "client": ("1.1.1.1", 1234), "path": "/"})
    with pytest.raises(auth_module.HTTPException):
        await get_current_user(request, token=token)


@pytest.mark.asyncio
async def test_get_current_user_optional_invalid_token():
    request = auth_module.Request({"type": "http", "headers": [], "client": ("1.1.1.1", 1234), "path": "/"})
    result = await get_current_user_optional(request, token="bad-token")
    assert result is None


@pytest.mark.asyncio
async def test_get_current_user_optional_cookie_fallback(monkeypatch):
    monkeypatch.setenv("SITE_MODE", "preview")
    token = create_access_token({"sub": "user@example.com"})
    cookie_name = session_cookie_candidates("preview")[0]
    request = _make_request_with_cookie(cookie_name, token)
    result = await get_current_user_optional(request, token=None)
    assert result == "user@example.com"


@pytest.mark.asyncio
async def test_get_current_user_optional_env_error_returns_none(monkeypatch):
    monkeypatch.setattr(auth_module.os, "getenv", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")))
    request = auth_module.Request({"type": "http", "headers": [], "client": ("1.1.1.1", 1234), "path": "/"})
    assert await get_current_user_optional(request, token=None) is None
