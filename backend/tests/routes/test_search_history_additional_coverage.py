from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi import HTTPException
import pytest
from starlette.requests import Request

from app.routes.v1 import search_history as routes
from app.schemas.search_context import SearchUserContext
from app.schemas.search_history import GuestSearchHistoryCreate, SearchHistoryCreate


class _SearchServiceStub:
    def __init__(self, *, record_exc=None, delete_result=True, track_exc=None):
        self.record_exc = record_exc
        self.delete_result = delete_result
        self.track_exc = track_exc
        self.record_context = None

    async def record_search(
        self,
        *,
        context,
        search_data,
        request_ip,
        user_agent,
        device_context,
        observability_candidates,
    ):
        if self.record_exc:
            raise self.record_exc
        self.record_context = context
        return SimpleNamespace(
            id="search-1",
            search_query=search_data["search_query"],
            search_type=search_data["search_type"],
            results_count=search_data["results_count"],
            first_searched_at=datetime.now(timezone.utc),
            last_searched_at=datetime.now(timezone.utc),
            search_count=1,
            guest_session_id=context.guest_session_id,
            search_event_id=None,
        )

    def delete_search(self, **_kwargs):
        return self.delete_result

    def track_interaction(self, **_kwargs):
        if self.track_exc:
            raise self.track_exc
        return SimpleNamespace(id="interaction-1")


def _make_request(headers: dict | None = None, cookies: dict | None = None) -> Request:
    raw_headers = []
    for key, value in (headers or {}).items():
        raw_headers.append((key.encode(), value.encode()))
    if cookies:
        cookie_str = "; ".join([f"{k}={v}" for k, v in cookies.items()])
        raw_headers.append((b"cookie", cookie_str.encode()))
    scope = {
        "type": "http",
        "headers": raw_headers,
        "path": "/api/v1/search-history",
        "query_string": b"",
        "client": ("127.0.0.1", 1234),
    }

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    return Request(scope, receive)


@pytest.mark.asyncio
async def test_get_search_context_requires_identity():
    request = _make_request()

    with pytest.raises(HTTPException) as exc:
        await routes.get_search_context(
            request,
            current_user=None,
            x_guest_session_id=None,
            x_session_id=None,
            x_search_origin=None,
        )

    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_get_search_context_uses_guest_cookie():
    request = _make_request(cookies={"guest_id": "guest-cookie"})

    context = await routes.get_search_context(
        request,
        current_user=None,
        x_guest_session_id=None,
        x_session_id="sess",
        x_search_origin="origin",
    )

    assert context.guest_session_id == "guest-cookie"
    assert context.session_id == "sess"
    assert context.search_origin == "origin"


@pytest.mark.asyncio
async def test_record_guest_search_rejects_user_context():
    request = _make_request()
    payload = GuestSearchHistoryCreate(
        search_query="test",
        search_type="natural_language",
        results_count=1,
        guest_session_id="guest-1",
    )
    context = SearchUserContext.from_user("user-1")

    with pytest.raises(HTTPException) as exc:
        await routes.record_guest_search(payload=payload, request=request, context=context, db=None)

    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_record_guest_search_adjusts_context(monkeypatch):
    stub = _SearchServiceStub()
    monkeypatch.setattr(routes, "SearchHistoryService", lambda _db: stub)

    request = _make_request()
    payload = GuestSearchHistoryCreate(
        search_query="test",
        search_type="natural_language",
        results_count=1,
        guest_session_id="payload-guest",
    )
    context = SearchUserContext.from_guest("header-guest")

    response = await routes.record_guest_search(payload=payload, request=request, context=context, db=None)

    assert response.guest_session_id == "payload-guest"
    assert stub.record_context.guest_session_id == "payload-guest"


@pytest.mark.asyncio
async def test_record_search_entry_value_error(monkeypatch):
    stub = _SearchServiceStub(record_exc=ValueError("bad"))
    monkeypatch.setattr(routes, "SearchHistoryService", lambda _db: stub)

    request = _make_request()
    payload = SearchHistoryCreate(
        search_query="test",
        search_type="natural_language",
        results_count=1,
    )
    context = SearchUserContext.from_guest("guest-1")

    with pytest.raises(HTTPException) as exc:
        await routes._record_search_entry(payload=payload, request=request, context=context, db=None)

    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_record_search_entry_unexpected_error(monkeypatch):
    stub = _SearchServiceStub(record_exc=RuntimeError("boom"))
    monkeypatch.setattr(routes, "SearchHistoryService", lambda _db: stub)

    request = _make_request()
    payload = SearchHistoryCreate(
        search_query="test",
        search_type="natural_language",
        results_count=1,
    )
    context = SearchUserContext.from_guest("guest-1")

    with pytest.raises(HTTPException) as exc:
        await routes._record_search_entry(payload=payload, request=request, context=context, db=None)

    assert exc.value.status_code == 500


@pytest.mark.asyncio
async def test_delete_search_requires_identity():
    with pytest.raises(HTTPException) as exc:
        await routes.delete_search(search_id="01H8AN4ZV7S000000000000000", current_user=None, x_guest_session_id=None, db=None)

    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_delete_search_not_found(monkeypatch):
    stub = _SearchServiceStub(delete_result=False)
    monkeypatch.setattr(routes, "SearchHistoryService", lambda _db: stub)

    with pytest.raises(HTTPException) as exc:
        await routes.delete_search(
            search_id="01H8AN4ZV7S000000000000000",
            current_user=SimpleNamespace(id="user-1"),
            x_guest_session_id=None,
            db=None,
        )

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_track_interaction_requires_fields():
    request = _make_request()
    context = SearchUserContext.from_guest("guest-1")

    with pytest.raises(HTTPException) as exc:
        await routes.track_interaction({}, request=request, context=context, db=None)

    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_track_interaction_value_error(monkeypatch):
    stub = _SearchServiceStub(track_exc=ValueError("bad"))
    monkeypatch.setattr(routes, "SearchHistoryService", lambda _db: stub)
    async def _to_thread(func, **kwargs):
        return func(**kwargs)

    monkeypatch.setattr(routes.asyncio, "to_thread", _to_thread)

    request = _make_request()
    context = SearchUserContext.from_guest("guest-1")

    with pytest.raises(HTTPException) as exc:
        await routes.track_interaction(
            {"search_event_id": "evt", "interaction_type": "click"},
            request=request,
            context=context,
            db=None,
        )

    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_get_search_context_handles_cookie_access_error():
    class _CookieRaiser:
        def get(self, _key):
            raise RuntimeError("cookie-boom")

    request = _make_request()
    request._cookies = _CookieRaiser()  # type: ignore[attr-defined]

    with pytest.raises(HTTPException) as exc:
        await routes.get_search_context(
            request,
            current_user=None,
            x_guest_session_id=None,
            x_session_id=None,
            x_search_origin=None,
        )

    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_record_search_entry_reraises_http_exception(monkeypatch):
    class _Service:
        async def record_search(self, **_kwargs):
            raise HTTPException(status_code=418, detail="teapot")

    monkeypatch.setattr(routes, "SearchHistoryService", lambda _db: _Service())

    request = _make_request()
    payload = SearchHistoryCreate(
        search_query="test",
        search_type="natural_language",
        results_count=1,
    )
    context = SearchUserContext.from_guest("guest-1")

    with pytest.raises(HTTPException) as exc:
        await routes._record_search_entry(payload=payload, request=request, context=context, db=None)

    assert exc.value.status_code == 418


@pytest.mark.asyncio
async def test_track_interaction_unexpected_error_in_production(monkeypatch):
    stub = _SearchServiceStub(track_exc=RuntimeError("boom"))
    monkeypatch.setattr(routes, "SearchHistoryService", lambda _db: stub)

    async def _to_thread(func, **kwargs):
        return func(**kwargs)

    monkeypatch.setattr(routes.asyncio, "to_thread", _to_thread)
    monkeypatch.setenv("ENV", "production")

    request = _make_request()
    context = SearchUserContext.from_guest("guest-1")

    with pytest.raises(HTTPException) as exc:
        await routes.track_interaction(
            {"search_event_id": "evt", "interaction_type": "click"},
            request=request,
            context=context,
            db=None,
        )

    assert exc.value.status_code == 500
    assert exc.value.detail == "Failed to track interaction"
