from fastapi import HTTPException
import pytest
from sqlalchemy.orm import Session
from starlette.requests import Request

from app.auth import create_access_token
from app.auth_sse import get_current_user_sse
from app.core.config import settings
from app.models.user import User


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


@pytest.mark.asyncio
async def test_get_current_user_sse_accepts_configured_session_cookie(unit_db, monkeypatch):
    monkeypatch.setenv("SITE_MODE", "preview")
    monkeypatch.setattr(settings, "session_cookie_name", "sid", raising=False)

    user = _create_user(unit_db)
    token = create_access_token({"sub": user.email})

    request = _build_request(f"sid={token}")

    resolved = await get_current_user_sse(
        request=request,
        token_header=None,
        token_query=None,
        db=unit_db,
    )

    assert resolved.id == user.id


@pytest.mark.asyncio
async def test_get_current_user_sse_falls_back_to_query_param(unit_db, monkeypatch):
    monkeypatch.setenv("SITE_MODE", "preview")

    user = _create_user(unit_db, email="query@example.com")
    token = create_access_token({"sub": user.email})

    # No cookie in the request; rely on Query parameter injection
    request = _build_request()

    resolved = await get_current_user_sse(
        request=request,
        token_header=None,
        token_query=token,
        db=unit_db,
    )

    assert resolved.email == user.email


@pytest.mark.asyncio
async def test_get_current_user_sse_requires_credentials(unit_db, monkeypatch):
    monkeypatch.setenv("SITE_MODE", "preview")

    request = _build_request()

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user_sse(
            request=request,
            token_header=None,
            token_query=None,
            db=unit_db,
        )

    assert getattr(exc_info.value, "status_code", None) == 401
