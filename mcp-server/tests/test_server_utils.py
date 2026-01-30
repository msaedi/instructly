from __future__ import annotations

import hashlib
import sys
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import parse_qs

import httpx
import jwt as pyjwt
import pytest
from instainstru_mcp.config import Settings
from instainstru_mcp.server import (
    DualAuthMiddleware,
    _load_settings,
    _noop_receive,
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


def test_normalize_uuid_returns_original_for_non_hex():
    value = "not-a-uuid"
    assert _normalize_uuid(value) == value


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


def test_normalize_session_query_returns_scope_when_query_empty():
    scope = {"path": "/messages/1", "query_string": b""}
    assert _normalize_session_query(scope) is scope


def test_normalize_session_query_returns_scope_without_session_id():
    scope = {"path": "/messages/1", "query_string": b"foo=bar"}
    assert _normalize_session_query(scope) is scope


def test_normalize_session_query_returns_scope_when_already_normalized():
    scope = {
        "path": "/messages/1",
        "query_string": b"session_id=01234567-89ab-cdef-0123-456789abcdef",
    }
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


def test_mcp_invalid_json_body_returns_auth_error_payload():
    settings = Settings(api_service_token="")
    middleware = _build_middleware(settings)
    client = TestClient(middleware, raise_server_exceptions=False)

    response = client.post(
        "/sse",
        content="{not-json",
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] is None
    assert payload["result"]["isError"] is True


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
    settings = Settings(api_service_token="token", workos_domain=None)
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
async def test_validate_workos_token_logs_unexpected_error(monkeypatch):
    settings = Settings(
        api_service_token="token",
        workos_domain="workos.test",
        workos_client_id="client",
        workos_client_secret="secret",
    )
    middleware = _build_middleware(settings)

    def _raise(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(pyjwt, "get_unverified_header", _raise)
    assert await middleware._validate_workos_token("token") is None


@pytest.mark.asyncio
async def test_authenticate_uses_cache():
    settings = Settings(api_service_token="token")
    middleware = _build_middleware(settings)
    cache_key = hashlib.sha256(b"token").hexdigest()
    middleware._auth_cache[cache_key] = (time.time() + 60, {"method": "simple_token"})

    result = await middleware._authenticate("token", "https://mcp.instainstru.com")
    assert result == {"method": "simple_token"}


@pytest.mark.asyncio
async def test_authenticate_removes_expired_cache_entry(monkeypatch):
    monkeypatch.delenv("INSTAINSTRU_MCP_API_SERVICE_TOKEN", raising=False)
    settings = Settings(api_service_token="")
    middleware = _build_middleware(settings)
    cache_key = hashlib.sha256(b"token").hexdigest()
    middleware._auth_cache[cache_key] = (time.time() - 1, {"method": "simple_token"})

    result = await middleware._authenticate("token", "https://mcp.instainstru.com")
    assert result is None
    assert cache_key not in middleware._auth_cache


@pytest.mark.asyncio
async def test_authenticate_rejects_mismatched_jwt_kid(monkeypatch):
    monkeypatch.delenv("INSTAINSTRU_MCP_API_SERVICE_TOKEN", raising=False)
    settings = Settings(api_service_token="")
    middleware = _build_middleware(settings)
    middleware.jwt_signing_key = "signing-key"
    middleware.jwt_key_id = "kid-expected"

    monkeypatch.setattr(pyjwt, "get_unverified_header", lambda _token: {"kid": "kid-other"})

    result = await middleware._authenticate("token", "https://mcp.instainstru.com")
    assert result is None


@pytest.mark.asyncio
async def test_workos_signing_key_expired_cache_clears_and_handles_fetch_error(monkeypatch):
    settings = Settings(
        api_service_token="token",
        workos_domain="workos.test",
        workos_client_id="client",
        workos_client_secret="secret",
    )
    middleware = _build_middleware(settings)
    middleware._jwks_cache["kid1"] = (time.time() - 1, "old-key")

    mock_client = AsyncMock()
    mock_client.get.side_effect = httpx.HTTPError("boom")

    with patch("instainstru_mcp.server.httpx.AsyncClient") as mock_async_client:
        mock_async_client.return_value.__aenter__.return_value = mock_client
        assert await middleware._get_workos_signing_key("kid1") is None

    assert "kid1" not in middleware._jwks_cache


def test_cache_auth_cleans_expired_entries(monkeypatch):
    settings = Settings(api_service_token="token")
    middleware = _build_middleware(settings)
    now = time.time()
    middleware._auth_cache = {
        "expired": (now - 1, {"method": "simple_token"}),
        "fresh": (now + 60, {"method": "simple_token"}),
    }

    monkeypatch.setattr(DualAuthMiddleware, "_AUTH_CACHE_MAX_SIZE", 1)
    middleware._cache_auth("new", {"method": "simple_token"}, now)

    assert "expired" not in middleware._auth_cache
    assert "fresh" in middleware._auth_cache
    assert "new" in middleware._auth_cache


def test_load_settings_returns_settings():
    settings = _load_settings()
    assert isinstance(settings, Settings)


@pytest.mark.asyncio
async def test_noop_receive_returns_empty_body():
    message = await _noop_receive()
    assert message["body"] == b""


def test_jwt_public_key_invalid_logs_warning(caplog):
    with caplog.at_level("WARNING"):
        _build_middleware(
            Settings(
                api_service_token="token",
                jwt_public_key="not-a-key",
                jwt_key_id="kid-1",
            )
        )
    assert any("Failed to load JWT public key" in msg for msg in caplog.messages)


def test_no_auth_configured_logs_warning(monkeypatch, caplog):
    monkeypatch.delenv("INSTAINSTRU_MCP_API_SERVICE_TOKEN", raising=False)
    with caplog.at_level("WARNING"):
        _build_middleware(
            Settings(
                api_service_token="",
                workos_domain=None,
                jwt_public_key="",
            )
        )
    assert any("No authentication configured" in msg for msg in caplog.messages)


def test_main_invokes_uvicorn(monkeypatch):
    mock_uvicorn = SimpleNamespace(run=MagicMock())
    monkeypatch.setitem(sys.modules, "uvicorn", mock_uvicorn)
    main()
    assert mock_uvicorn.run.called is True
