"""Tests targeting missed lines in app/middleware/timing_asgi.py.

Missed lines:
  33-34: non-http scope passes through
  81->83: pool_status is None (not set) => skip db_pool key
  84: pool_error is truthy => add to log_extra
"""
from __future__ import annotations

import itertools

import pytest

from app.middleware.timing_asgi import TimingMiddlewareASGI


async def _run_app(app, scope):
    messages = []

    async def receive():
        return {"type": "http.request"}

    async def send(message):
        messages.append(message)

    await app(scope, receive, send)
    return messages


@pytest.mark.asyncio
async def test_non_http_scope_passes_through() -> None:
    """Lines 33-34: non-http scope type goes straight through."""
    called = {"inner": False}

    async def app(scope, receive, send):
        called["inner"] = True

    middleware = TimingMiddlewareASGI(app)

    async def receive():
        return {}

    async def send(msg):
        pass

    await middleware({"type": "websocket"}, receive, send)
    assert called["inner"] is True


@pytest.mark.asyncio
async def test_very_slow_request_pool_status_none(monkeypatch, caplog) -> None:
    """Line 81->83, 84: get_db_pool_status returns None => pool_error path."""
    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    # Make it appear very slow (>1000ms)
    times = itertools.cycle([0.0, 2.0])
    monkeypatch.setattr("app.middleware.timing_asgi.time.time", lambda: next(times))
    # get_db_pool_status raises an exception
    monkeypatch.setattr(
        "app.middleware.timing_asgi.get_db_pool_status",
        lambda: (_ for _ in ()).throw(RuntimeError("pool error")),
    )

    middleware = TimingMiddlewareASGI(app)
    scope = {"type": "http", "method": "GET", "path": "/api/v1/test", "headers": []}
    messages = await _run_app(middleware, scope)

    # Should still add timing header
    headers = dict(messages[0]["headers"])
    assert b"x-process-time" in headers
    assert any("Slow request exceeded 1s" in rec.message for rec in caplog.records)
