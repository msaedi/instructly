import itertools

import pytest

from app.core.constants import SSE_PATH_PREFIX
from app.middleware.timing_asgi import TimingMiddlewareASGI


async def _run_app(app, scope):
    messages = []

    async def receive():
        return {"type": "http.request"}

    async def send(message):
        messages.append(message)

    await app(scope, receive, send)
    return messages


def _scope(path="/api/v1/test"):
    return {"type": "http", "method": "GET", "path": path, "headers": []}


@pytest.mark.asyncio
async def test_timing_skips_health():
    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    middleware = TimingMiddlewareASGI(app)
    messages = await _run_app(middleware, _scope(path="/api/v1/health"))
    headers = dict(messages[0]["headers"])
    assert b"x-process-time" not in headers


@pytest.mark.asyncio
async def test_timing_skips_sse():
    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    middleware = TimingMiddlewareASGI(app)
    messages = await _run_app(middleware, _scope(path=SSE_PATH_PREFIX))
    headers = dict(messages[0]["headers"])
    assert b"x-process-time" not in headers


@pytest.mark.asyncio
async def test_timing_adds_header_and_logs_slow(monkeypatch, caplog):
    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    times = itertools.cycle([0.0, 0.2])
    monkeypatch.setattr("app.middleware.timing_asgi.time.time", lambda: next(times))

    middleware = TimingMiddlewareASGI(app)
    messages = await _run_app(middleware, _scope())
    headers = dict(messages[0]["headers"])
    assert b"x-process-time" in headers
    assert any("Slow request" in rec.message for rec in caplog.records)


@pytest.mark.asyncio
async def test_timing_logs_pool_for_very_slow(monkeypatch, caplog):
    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    times = itertools.cycle([0.0, 2.0])
    monkeypatch.setattr("app.middleware.timing_asgi.time.time", lambda: next(times))
    monkeypatch.setattr(
        "app.middleware.timing_asgi.get_db_pool_status", lambda: {"used": 1, "size": 5}
    )

    middleware = TimingMiddlewareASGI(app)
    await _run_app(middleware, _scope())
    assert any("Slow request exceeded 1s" in rec.message for rec in caplog.records)


@pytest.mark.asyncio
async def test_timing_logs_errors(monkeypatch, caplog):
    async def app(scope, receive, send):
        raise RuntimeError("boom")

    times = itertools.cycle([0.0, 0.1])
    monkeypatch.setattr("app.middleware.timing_asgi.time.time", lambda: next(times))

    middleware = TimingMiddlewareASGI(app)
    with pytest.raises(RuntimeError):
        await _run_app(middleware, _scope())
    assert any("Error in request" in rec.message for rec in caplog.records)
