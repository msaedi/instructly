"""Tests targeting missed lines in app/middleware/beta_phase_header.py.

Missed lines:
  71-72: refresh_beta_settings_cache exception branch
  96-97: SSE path => skip middleware
  126-129: DB lookup exception in __call__
  140-141: PrometheusMetrics.inc_beta_phase_header exception
"""
from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from app.core.constants import SSE_PATH_PREFIX


async def _run_middleware(middleware, scope):
    """Helper to run ASGI middleware and collect sent messages."""
    messages_sent = []

    async def receive():
        return {"type": "http.request"}

    async def send(message):
        messages_sent.append(message)

    await middleware(scope, receive, send)
    return messages_sent


def _http_scope(path="/api/v1/test"):
    return {"type": "http", "path": path}


@pytest.mark.asyncio
async def test_sse_path_skips_middleware() -> None:
    """Lines 96-97: SSE path prefix causes middleware to skip processing."""
    called = {"inner": False}

    async def inner_app(scope, receive, send):
        called["inner"] = True
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    from app.middleware.beta_phase_header import BetaPhaseHeaderMiddleware

    mw = BetaPhaseHeaderMiddleware(inner_app)
    messages = await _run_middleware(mw, _http_scope(path=SSE_PATH_PREFIX + "/test"))

    assert called["inner"] is True
    # SSE path should NOT have beta phase headers added
    if messages:
        headers = dict(messages[0].get("headers", []))
        assert b"x-beta-phase" not in headers


@pytest.mark.asyncio
async def test_non_http_scope_passes_through() -> None:
    """Line 89-90: non-http scope passes through directly."""
    called = {"inner": False}

    async def inner_app(scope, receive, send):
        called["inner"] = True

    from app.middleware.beta_phase_header import BetaPhaseHeaderMiddleware

    mw = BetaPhaseHeaderMiddleware(inner_app)

    async def receive():
        return {}

    async def send(msg):
        pass

    await mw({"type": "websocket"}, receive, send)
    assert called["inner"] is True


@pytest.mark.asyncio
async def test_db_lookup_exception_uses_cached_values() -> None:
    """Lines 126-129: DB lookup fails => use cached values even if stale."""
    import app.middleware.beta_phase_header as mod

    # Force cache to be invalid so it tries DB
    original_cache = mod._cache
    mod._cache = mod.BetaSettingsCache(
        phase_value=b"stale_phase",
        allow_signup_value=b"0",
        cached_at=0.0,  # Invalid cache
    )

    async def inner_app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    mw = mod.BetaPhaseHeaderMiddleware(inner_app)

    with patch.object(mod, "SessionLocal", side_effect=RuntimeError("DB down")):
        with patch.object(mod, "PrometheusMetrics") as mock_prom:
            mock_prom.inc_beta_phase_header = MagicMock()
            messages = await _run_middleware(mw, _http_scope())

    # Should still send response with (stale) cached headers
    assert len(messages) >= 1
    headers = dict(messages[0].get("headers", []))
    assert b"x-beta-phase" in headers

    # Restore
    mod._cache = original_cache


@pytest.mark.asyncio
async def test_prometheus_metrics_exception_in_send_wrapper() -> None:
    """Lines 140-141: PrometheusMetrics.inc_beta_phase_header raises => debug log but no break."""
    import app.middleware.beta_phase_header as mod

    # Set valid cache so it doesn't try DB
    original_cache = mod._cache
    mod._cache = mod.BetaSettingsCache(
        phase_value=b"open_beta",
        allow_signup_value=b"1",
        cached_at=time.time(),
    )

    async def inner_app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    mw = mod.BetaPhaseHeaderMiddleware(inner_app)

    with patch.object(mod.PrometheusMetrics, "inc_beta_phase_header", side_effect=RuntimeError("prom fail")):
        messages = await _run_middleware(mw, _http_scope())

    # Response should still go through despite prometheus error
    assert len(messages) >= 1
    headers = dict(messages[0].get("headers", []))
    assert b"x-beta-phase" in headers

    # Restore
    mod._cache = original_cache


def test_refresh_beta_settings_cache_exception() -> None:
    """Lines 71-72: refresh_beta_settings_cache catches exception."""
    import app.middleware.beta_phase_header as mod

    mock_db = MagicMock()
    with patch.object(mod, "BetaSettingsRepository", side_effect=RuntimeError("repo fail")):
        # Should not raise, just log warning
        mod.refresh_beta_settings_cache(mock_db)
