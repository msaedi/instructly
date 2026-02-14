from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import HTTPException
from jwt import PyJWTError
import pytest
from starlette.requests import Request

from app import auth_sse


def _make_request(cookie: str | None = None) -> Request:
    headers = []
    if cookie:
        headers = [(b"cookie", cookie.encode())]
    scope = {"type": "http", "headers": headers, "path": "/"}
    return Request(scope)


@pytest.mark.asyncio
async def test_get_user_from_sse_token_missing_redis(monkeypatch) -> None:
    async def _none():
        return None

    monkeypatch.setattr(auth_sse, "get_async_cache_redis_client", _none)
    result = await auth_sse._get_user_from_sse_token("tok")
    assert result is None


@pytest.mark.asyncio
async def test_get_user_from_sse_token_inactive(monkeypatch) -> None:
    class DummyRedis:
        async def get(self, _key):
            return "user-1"

        async def delete(self, _key):
            return None

    monkeypatch.setattr(auth_sse, "get_async_cache_redis_client", AsyncMock(return_value=DummyRedis()))
    monkeypatch.setattr(auth_sse, "lookup_user_by_id_nonblocking", AsyncMock(return_value={"id": "u1", "is_active": False}))

    result = await auth_sse._get_user_from_sse_token("tok")
    assert result is None


@pytest.mark.asyncio
async def test_get_user_from_sse_token_success(monkeypatch) -> None:
    class DummyRedis:
        async def get(self, _key):
            return b"user-1"

        async def delete(self, _key):
            return None

    monkeypatch.setattr(auth_sse, "get_async_cache_redis_client", AsyncMock(return_value=DummyRedis()))
    monkeypatch.setattr(
        auth_sse,
        "lookup_user_by_id_nonblocking",
        AsyncMock(return_value={"id": "u1", "email": "a@b.com", "is_active": True}),
    )
    monkeypatch.setattr(auth_sse, "create_transient_user", lambda data: data)

    result = await auth_sse._get_user_from_sse_token("tok")
    assert result["id"] == "u1"


@pytest.mark.asyncio
async def test_get_current_user_sse_with_invalid_token_query(monkeypatch) -> None:
    request = _make_request()
    monkeypatch.setattr(auth_sse, "_get_user_from_sse_token", AsyncMock(return_value=None))

    with pytest.raises(HTTPException) as exc:
        await auth_sse.get_current_user_sse(request, token_header=None, token_query="tok")

    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_sse_with_token_query(monkeypatch) -> None:
    user = SimpleNamespace(id="u1")
    request = _make_request()
    monkeypatch.setattr(auth_sse, "_get_user_from_sse_token", AsyncMock(return_value=user))

    result = await auth_sse.get_current_user_sse(request, token_header=None, token_query="tok")

    assert result is user


@pytest.mark.asyncio
async def test_get_current_user_sse_missing_token(monkeypatch) -> None:
    request = _make_request()

    with pytest.raises(HTTPException) as exc:
        await auth_sse.get_current_user_sse(request, token_header=None, token_query=None)

    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_sse_invalid_jwt(monkeypatch) -> None:
    request = _make_request()
    monkeypatch.setattr(auth_sse, "decode_access_token", lambda _token: (_ for _ in ()).throw(PyJWTError("bad")))

    with pytest.raises(HTTPException) as exc:
        await auth_sse.get_current_user_sse(request, token_header="token", token_query=None)

    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_sse_inactive_user(monkeypatch) -> None:
    request = _make_request()
    monkeypatch.setattr(
        auth_sse,
        "decode_access_token",
        lambda _token: {"sub": "01ARZ3NDEKTSV4RRFFQ69G5FAV", "jti": "test-jti", "iat": 123},
    )

    class _NeverRevoked:
        async def is_revoked(self, _jti: str) -> bool:
            return False

    monkeypatch.setattr(auth_sse, "TokenBlacklistService", lambda: _NeverRevoked())
    monkeypatch.setattr(
        auth_sse,
        "lookup_user_by_id_nonblocking",
        AsyncMock(return_value={"id": "u1", "is_active": False}),
    )

    with pytest.raises(HTTPException) as exc:
        await auth_sse.get_current_user_sse(request, token_header="token", token_query=None)

    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_get_current_user_sse_cookie_flow(monkeypatch) -> None:
    request = _make_request("session=token")
    monkeypatch.setattr(auth_sse, "session_cookie_candidates", lambda _mode: ["session"])
    monkeypatch.setattr(
        auth_sse,
        "decode_access_token",
        lambda _token: {"sub": "01ARZ3NDEKTSV4RRFFQ69G5FAV", "jti": "test-jti", "iat": 123},
    )

    class _NeverRevoked:
        async def is_revoked(self, _jti: str) -> bool:
            return False

    monkeypatch.setattr(auth_sse, "TokenBlacklistService", lambda: _NeverRevoked())
    monkeypatch.setattr(
        auth_sse,
        "lookup_user_by_id_nonblocking",
        AsyncMock(return_value={"id": "u1", "is_active": True}),
    )
    monkeypatch.setattr(auth_sse, "create_transient_user", lambda data: data)

    result = await auth_sse.get_current_user_sse(request, token_header=None, token_query=None)

    assert result["id"] == "u1"
