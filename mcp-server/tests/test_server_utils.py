from __future__ import annotations

import hashlib
import sys
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import parse_qs

import jwt as pyjwt
import pytest
from instainstru_mcp.config import Settings
from instainstru_mcp.server import (
    DualAuthMiddleware,
    _normalize_mcp_path,
    _normalize_session_query,
    _normalize_uuid,
    _read_body,
    _replay_body,
    _www_authenticate_from_scope,
    main,
)
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient


def test_normalize_uuid_inserts_dashes():
    value = "0123456789abcdef0123456789abcdef"
    assert _normalize_uuid(value) == "01234567-89ab-cdef-0123-456789abcdef"


def test_normalize_session_query_updates_uuid_params():
    scope = {
        "path": "/messages/1",
        "query_string": b"session_id=0123456789abcdef0123456789abcdef",
    }
    updated = _normalize_session_query(scope)
    params = parse_qs(updated["query_string"].decode())
    assert params["session_id"][0] == "01234567-89ab-cdef-0123-456789abcdef"


def test_normalize_session_query_ignores_invalid_bytes():
    scope = {"path": "/messages/1", "query_string": b"\xff"}
    assert _normalize_session_query(scope) is scope


def test_normalize_mcp_path_updates_raw_path():
    scope = {"path": "/mcp/", "raw_path": b"/mcp/"}
    updated = _normalize_mcp_path(scope)
    assert updated["path"] == "/mcp"
    assert updated["raw_path"] == b"/mcp"


@pytest.mark.asyncio
async def test_read_body_collects_chunks():
    messages = [
        {"type": "http.request", "body": b"hello ", "more_body": True},
        {"type": "http.request", "body": b"world", "more_body": False},
    ]

    async def receive():
        return messages.pop(0)

    body = await _read_body(receive)
    assert body == b"hello world"


@pytest.mark.asyncio
async def test_read_body_stops_on_disconnect():
    async def receive():
        return {"type": "http.disconnect"}

    body = await _read_body(receive)
    assert body == b""


@pytest.mark.asyncio
async def test_replay_body_only_sends_once():
    receive = _replay_body(b"data")
    first = await receive()
    second = await receive()
    assert first["body"] == b"data"
    assert second["body"] == b""


def test_www_authenticate_from_scope_uses_host_header():
    scope = {"headers": [(b"host", b"example.com")]}
    header = _www_authenticate_from_scope(scope)
    assert "https://example.com/.well-known/oauth-protected-resource" in header


def _build_middleware(settings: Settings) -> DualAuthMiddleware:
    DualAuthMiddleware._auth_cache = {}
    DualAuthMiddleware._jwks_cache = {}

    async def protected(_request):
        return PlainTextResponse("ok")

    app = Starlette(routes=[Route("/sse", protected, methods=["GET", "POST"])])
    return DualAuthMiddleware(app, settings)


def test_mcp_json_auth_required_returns_error_payload():
    settings = Settings(api_service_token="")
    middleware = _build_middleware(settings)
    client = TestClient(middleware, raise_server_exceptions=False)

    response = client.post(
        "/sse",
        json={"jsonrpc": "2.0", "id": "1", "method": "tools/call"},
        headers={"mcp-session-id": "session"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["result"]["isError"] is True
    assert "mcp/www_authenticate" in payload["result"]["_meta"]


def test_mcp_tools_list_allows_unauthenticated_call():
    settings = Settings(api_service_token="")
    middleware = _build_middleware(settings)
    client = TestClient(middleware, raise_server_exceptions=False)

    response = client.post(
        "/sse",
        json={"jsonrpc": "2.0", "id": "1", "method": "tools/list"},
    )
    assert response.status_code == 200
    assert response.text == "ok"


@pytest.mark.asyncio
async def test_workos_signing_key_caches(monkeypatch):
    settings = Settings(
        api_service_token="token",
        workos_domain="workos.test",
        workos_client_id="client",
        workos_client_secret="secret",
    )
    middleware = _build_middleware(settings)

    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"keys": [{"kid": "kid1"}]}

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_response

    with patch("instainstru_mcp.server.httpx.AsyncClient") as mock_async_client:
        mock_async_client.return_value.__aenter__.return_value = mock_client
        monkeypatch.setattr(
            "instainstru_mcp.server.PyJWK.from_dict",
            lambda _data: SimpleNamespace(key="signing-key"),
        )

        key = await middleware._get_workos_signing_key("kid1")
        assert key == "signing-key"
        key_cached = await middleware._get_workos_signing_key("kid1")
        assert key_cached == "signing-key"
        assert mock_client.get.call_count == 1


@pytest.mark.asyncio
async def test_workos_signing_key_missing_returns_none(monkeypatch):
    settings = Settings(
        api_service_token="token",
        workos_domain="workos.test",
        workos_client_id="client",
        workos_client_secret="secret",
    )
    middleware = _build_middleware(settings)

    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"keys": [{"kid": "other"}]}

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_response

    with patch("instainstru_mcp.server.httpx.AsyncClient") as mock_async_client:
        mock_async_client.return_value.__aenter__.return_value = mock_client
        monkeypatch.setattr(
            "instainstru_mcp.server.PyJWK.from_dict",
            lambda _data: SimpleNamespace(key="signing-key"),
        )
        assert await middleware._get_workos_signing_key("kid1") is None


@pytest.mark.asyncio
async def test_workos_signing_key_returns_none_when_not_configured():
    settings = Settings(api_service_token="token")
    middleware = _build_middleware(settings)
    assert await middleware._get_workos_signing_key("kid1") is None


@pytest.mark.asyncio
async def test_validate_workos_token_missing_kid(monkeypatch):
    settings = Settings(
        api_service_token="token",
        workos_domain="workos.test",
        workos_client_id="client",
        workos_client_secret="secret",
    )
    middleware = _build_middleware(settings)

    monkeypatch.setattr(pyjwt, "get_unverified_header", lambda _token: {})
    assert await middleware._validate_workos_token("token") is None


@pytest.mark.asyncio
async def test_validate_workos_token_success(monkeypatch):
    settings = Settings(
        api_service_token="token",
        workos_domain="workos.test",
        workos_client_id="client",
        workos_client_secret="secret",
    )
    middleware = _build_middleware(settings)

    monkeypatch.setattr(pyjwt, "get_unverified_header", lambda _token: {"kid": "kid1"})
    monkeypatch.setattr(middleware, "_get_workos_signing_key", AsyncMock(return_value="key"))
    monkeypatch.setattr(pyjwt, "decode", lambda *args, **kwargs: {"sub": "user"})

    result = await middleware._validate_workos_token("token")
    assert result == {"method": "workos", "claims": {"sub": "user"}}


@pytest.mark.asyncio
async def test_validate_workos_token_invalid(monkeypatch):
    settings = Settings(
        api_service_token="token",
        workos_domain="workos.test",
        workos_client_id="client",
        workos_client_secret="secret",
    )
    middleware = _build_middleware(settings)

    monkeypatch.setattr(pyjwt, "get_unverified_header", lambda _token: {"kid": "kid1"})
    monkeypatch.setattr(middleware, "_get_workos_signing_key", AsyncMock(return_value="key"))

    def _raise(*_args, **_kwargs):
        raise pyjwt.InvalidTokenError("bad")

    monkeypatch.setattr(pyjwt, "decode", _raise)
    assert await middleware._validate_workos_token("token") is None


@pytest.mark.asyncio
async def test_authenticate_uses_cache():
    settings = Settings(api_service_token="token")
    middleware = _build_middleware(settings)
    cache_key = hashlib.sha256(b"token").hexdigest()
    middleware._auth_cache[cache_key] = (time.time() + 60, {"method": "simple_token"})

    result = await middleware._authenticate("token", "https://mcp.instainstru.com")
    assert result == {"method": "simple_token"}


def test_main_invokes_uvicorn(monkeypatch):
    mock_uvicorn = SimpleNamespace(run=MagicMock())
    monkeypatch.setitem(sys.modules, "uvicorn", mock_uvicorn)
    main()
    assert mock_uvicorn.run.called is True
