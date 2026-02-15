from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
import jwt
import pytest
from sqlalchemy.orm import Session
from starlette.requests import Request

from app import auth_sse
from app.auth import create_access_token, create_refresh_token
from app.auth_sse import get_current_user_sse
from app.core import auth_cache
from app.core.config import settings
from app.models.user import User
from app.utils.cookies import session_cookie_base_name


async def _empty_receive() -> dict[str, object]:
    return {"type": "http.request", "body": b"", "more_body": False}


def _build_request(cookie_header: str | None = None) -> Request:
    headers: list[tuple[bytes, bytes]] = []
    if cookie_header:
        headers.append((b"cookie", cookie_header.encode()))

    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/",
        "raw_path": b"/",
        "headers": headers,
        "query_string": b"",
        "client": ("testclient", 1234),
        "server": ("testserver", 80),
    }

    return Request(scope, _empty_receive)


def _create_user(unit_db: Session, email: str = "chat@example.com") -> User:
    user = User(
        email=email,
        hashed_password="hashed",
        first_name="Chat",
        last_name="Tester",
        zip_code="10001",
        is_active=True,
    )
    unit_db.add(user)
    unit_db.commit()
    return user


class _NeverRevokedService:
    async def is_revoked(self, _jti: str) -> bool:
        return False


@pytest.mark.asyncio
async def test_get_current_user_sse_accepts_configured_session_cookie(unit_db, monkeypatch):
    monkeypatch.setenv("SITE_MODE", "preview")
    monkeypatch.setattr(settings, "session_cookie_name", "sid", raising=False)
    monkeypatch.setattr(auth_sse, "TokenBlacklistService", lambda: _NeverRevokedService())
    # Patch SessionLocal in the shared auth_cache module to return our test db session
    monkeypatch.setattr(auth_cache, "SessionLocal", lambda: unit_db)
    # Disable Redis caching to avoid stale cache hits from previous test runs
    monkeypatch.setattr(auth_cache, "_get_auth_redis_client", lambda: None)

    # Use unique email to avoid collision with seed data
    user = _create_user(unit_db, email="sse-cookie-test@example.com")
    # Capture user attributes BEFORE calling get_current_user_sse
    # because it calls db.rollback() which expires all objects in the session
    expected_id = user.id
    token = create_access_token({"sub": expected_id, "email": user.email})

    cookie_name = session_cookie_base_name("preview")
    request = _build_request(f"{cookie_name}={token}")

    resolved = await get_current_user_sse(
        request=request,
        token_header=None,
        token_query=None,
    )

    assert resolved.id == expected_id


@pytest.mark.asyncio
async def test_get_current_user_sse_accepts_sse_query_token(unit_db, monkeypatch):
    monkeypatch.setenv("SITE_MODE", "preview")
    monkeypatch.setattr(auth_sse, "TokenBlacklistService", lambda: _NeverRevokedService())
    # Patch SessionLocal in the shared auth_cache module to return our test db session
    monkeypatch.setattr(auth_cache, "SessionLocal", lambda: unit_db)
    # Disable Redis caching to avoid stale cache hits from previous test runs
    monkeypatch.setattr(auth_cache, "_get_auth_redis_client", lambda: None)

    user = _create_user(unit_db, email="query@example.com")
    # Capture user attributes BEFORE calling get_current_user_sse
    # because it calls db.rollback() which expires all objects in the session
    expected_email = user.email

    class FakeRedis:
        def __init__(self) -> None:
            self.store: dict[str, str] = {}

        async def setex(self, key: str, _ttl: int, value: str) -> None:
            self.store[key] = value

        async def get(self, key: str) -> str | None:
            return self.store.get(key)

        async def delete(self, key: str) -> None:
            self.store.pop(key, None)

    fake_redis = FakeRedis()

    async def _get_redis():
        return fake_redis

    monkeypatch.setattr(auth_sse, "get_async_cache_redis_client", _get_redis)

    token = "sse-token-123"
    await fake_redis.setex(
        f"{auth_sse.SSE_KEY_PREFIX}{token}",
        auth_sse.SSE_TOKEN_TTL_SECONDS,
        str(user.id),
    )

    # No cookie in the request; rely on Query parameter injection
    request = _build_request()

    resolved = await get_current_user_sse(
        request=request,
        token_header=None,
        token_query=token,
    )

    assert resolved.email == expected_email


@pytest.mark.asyncio
async def test_get_current_user_sse_requires_credentials(unit_db, monkeypatch):
    monkeypatch.setenv("SITE_MODE", "preview")
    monkeypatch.setattr(auth_sse, "TokenBlacklistService", lambda: _NeverRevokedService())
    # Patch SessionLocal in the shared auth_cache module (needed if auth reaches DB lookup)
    monkeypatch.setattr(auth_cache, "SessionLocal", lambda: unit_db)

    request = _build_request()

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user_sse(
            request=request,
            token_header=None,
            token_query=None,
        )

    assert getattr(exc_info.value, "status_code", None) == 401


@pytest.mark.asyncio
async def test_get_current_user_sse_rejects_revoked_jwt(unit_db, monkeypatch):
    monkeypatch.setenv("SITE_MODE", "preview")
    monkeypatch.setattr(auth_cache, "SessionLocal", lambda: unit_db)
    monkeypatch.setattr(auth_cache, "_get_auth_redis_client", lambda: None)
    rejection_calls: list[str] = []
    monkeypatch.setattr(
        auth_sse.prometheus_metrics,
        "record_token_rejection",
        lambda reason: rejection_calls.append(reason),
    )
    user = _create_user(unit_db, email="sse-revoked@example.com")
    token = create_access_token({"sub": user.id, "email": user.email})

    class _RevokedService:
        async def is_revoked(self, _jti: str) -> bool:
            return True

    monkeypatch.setattr(auth_sse, "TokenBlacklistService", lambda: _RevokedService())
    request = _build_request()

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user_sse(request=request, token_header=token, token_query=None)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Token has been revoked"
    assert rejection_calls == ["revoked"]


@pytest.mark.asyncio
async def test_get_current_user_sse_rejects_refresh_token_type(unit_db, monkeypatch):
    monkeypatch.setenv("SITE_MODE", "preview")
    monkeypatch.setattr(auth_cache, "SessionLocal", lambda: unit_db)
    monkeypatch.setattr(auth_cache, "_get_auth_redis_client", lambda: None)

    user = _create_user(unit_db, email="sse-refresh-type@example.com")
    token = create_refresh_token({"sub": user.id, "email": user.email})
    request = _build_request()

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user_sse(request=request, token_header=token, token_query=None)

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_sse_rejects_token_invalidated_by_user_timestamp(unit_db, monkeypatch):
    monkeypatch.setenv("SITE_MODE", "preview")
    monkeypatch.setattr(auth_sse, "TokenBlacklistService", lambda: _NeverRevokedService())
    monkeypatch.setattr(auth_cache, "SessionLocal", lambda: unit_db)
    monkeypatch.setattr(auth_cache, "_get_auth_redis_client", lambda: None)
    rejection_calls: list[str] = []
    monkeypatch.setattr(
        auth_sse.prometheus_metrics,
        "record_token_rejection",
        lambda reason: rejection_calls.append(reason),
    )

    user = _create_user(unit_db, email="sse-invalidated@example.com")
    token = create_access_token({"sub": user.id, "email": user.email})
    # Ensure token iat is before tokens_valid_after.
    user.tokens_valid_after = datetime.now(timezone.utc) + timedelta(seconds=30)
    unit_db.add(user)
    unit_db.commit()

    request = _build_request()
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user_sse(request=request, token_header=token, token_query=None)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Token has been invalidated"
    assert rejection_calls == ["invalidated"]


@pytest.mark.asyncio
async def test_get_current_user_sse_rejects_token_without_jti_records_metric(unit_db, monkeypatch):
    monkeypatch.setenv("SITE_MODE", "preview")
    monkeypatch.setattr(auth_cache, "SessionLocal", lambda: unit_db)
    monkeypatch.setattr(auth_cache, "_get_auth_redis_client", lambda: None)
    rejection_calls: list[str] = []
    monkeypatch.setattr(
        auth_sse.prometheus_metrics,
        "record_token_rejection",
        lambda reason: rejection_calls.append(reason),
    )

    user = _create_user(unit_db, email="sse-no-jti@example.com")
    token = create_access_token({"sub": user.id, "email": user.email})
    payload = auth_sse.decode_access_token(token)
    payload.pop("jti", None)
    token_without_jti = jwt.encode(
        payload,
        auth_sse.settings.secret_key.get_secret_value(),
        algorithm=auth_sse.settings.algorithm,
    )

    request = _build_request()
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user_sse(request=request, token_header=token_without_jti, token_query=None)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Token format outdated, please re-login"
    assert rejection_calls == ["format_outdated"]


@pytest.mark.asyncio
async def test_get_current_user_sse_fail_closed_when_blacklist_errors(unit_db, monkeypatch):
    monkeypatch.setenv("SITE_MODE", "preview")
    monkeypatch.setattr(auth_cache, "SessionLocal", lambda: unit_db)
    monkeypatch.setattr(auth_cache, "_get_auth_redis_client", lambda: None)

    user = _create_user(unit_db, email="sse-failclosed@example.com")
    token = create_access_token({"sub": user.id, "email": user.email})

    class _BrokenService:
        async def is_revoked(self, _jti: str) -> bool:
            raise RuntimeError("redis unavailable")

    monkeypatch.setattr(auth_sse, "TokenBlacklistService", lambda: _BrokenService())
    request = _build_request()

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user_sse(request=request, token_header=token, token_query=None)

    assert exc_info.value.status_code == 401
