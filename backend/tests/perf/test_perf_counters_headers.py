from __future__ import annotations

import pathlib
import sys

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from starlette.requests import Request
from starlette.responses import Response

BACKEND_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import app.middleware.perf_counters as perf_counters_module
from app.middleware.perf_counters import (
    PerfCounterMiddleware,
    inc_db_query,
    note_cache_hit,
    note_cache_miss,
    record_cache_key,
    snapshot,
)


def _build_client(monkeypatch, include_cache_route: bool = False) -> TestClient:
    monkeypatch.setenv("AVAILABILITY_PERF_DEBUG", "1")
    app = FastAPI()
    app.add_middleware(PerfCounterMiddleware)

    @app.get("/ping")
    def ping() -> dict[str, str]:
        inc_db_query("SELECT 1")
        return {"status": "ok"}

    if include_cache_route:

        @app.get("/simulate-cache")
        def simulate_cache() -> dict[str, str]:
            note_cache_miss("cache:test-key")
            note_cache_hit("cache:test-key")
            return {"status": "cached"}

    return TestClient(app)


def test_headers_present_for_request(monkeypatch) -> None:
    client = _build_client(monkeypatch)
    response = client.get("/ping")
    assert response.status_code == 200
    for header in ("x-db-query-count", "x-cache-hits", "x-cache-misses"):
        assert header in response.headers
        assert response.headers[header].isdigit()
    assert response.headers["x-db-query-count"] == "1"


def test_cache_hit_and_miss_increment(monkeypatch) -> None:
    client = _build_client(monkeypatch, include_cache_route=True)
    response = client.get("/simulate-cache")
    assert response.status_code == 200
    assert int(response.headers["x-cache-hits"]) >= 1
    assert int(response.headers["x-cache-misses"]) >= 1


def test_snapshot_uses_empty_state_when_uninitialized() -> None:
    perf_counters_module._state_var.set(None)

    snap = snapshot()

    assert snap.db_queries == 0
    assert snap.cache_hits == 0
    assert snap.cache_misses == 0
    assert snap.table_counts == {}
    assert snap.cache_keys == []


def test_inc_db_query_tracks_availability_slots_table(monkeypatch) -> None:
    monkeypatch.setenv("AVAILABILITY_PERF_DEBUG", "1")
    perf_counters_module.reset_counters()

    inc_db_query("SELECT * FROM availability_slots WHERE id = 1")
    snap = snapshot()

    assert snap.db_queries == 1
    assert snap.table_counts["availability_slots"] == 1


def test_cache_helpers_noop_when_perf_debug_disabled(monkeypatch) -> None:
    monkeypatch.delenv("AVAILABILITY_PERF_DEBUG", raising=False)
    perf_counters_module.reset_counters()

    note_cache_hit("cache:key")
    note_cache_miss("cache:key")
    record_cache_key("cache:key")
    snap = snapshot()

    assert snap.cache_hits == 0
    assert snap.cache_misses == 0
    assert snap.cache_keys == []


def test_middleware_handles_missing_context_state(monkeypatch) -> None:
    monkeypatch.setenv("AVAILABILITY_PERF_DEBUG", "1")
    app = FastAPI()
    app.add_middleware(PerfCounterMiddleware)

    @app.get("/state-reset")
    def state_reset() -> dict[str, str]:
        perf_counters_module._state_var.set(None)
        return {"status": "ok"}

    client = TestClient(app)
    response = client.get("/state-reset")

    assert response.status_code == 200
    assert response.headers["x-db-query-count"] == "0"
    assert response.headers["x-cache-hits"] == "0"
    assert response.headers["x-cache-misses"] == "0"


def test_middleware_falls_back_to_empty_state_when_reset_is_disabled(monkeypatch) -> None:
    monkeypatch.setenv("AVAILABILITY_PERF_DEBUG", "1")
    app = FastAPI()
    app.add_middleware(PerfCounterMiddleware)
    monkeypatch.setattr(perf_counters_module, "reset_counters", lambda: None)

    @app.get("/no-reset")
    def no_reset() -> dict[str, str]:
        return {"status": "ok"}

    client = TestClient(app)
    response = client.get("/no-reset")

    assert response.status_code == 200
    assert response.headers["x-db-query-count"] == "0"


@pytest.mark.asyncio
async def test_dispatch_fallback_creates_state_when_none(monkeypatch) -> None:
    monkeypatch.setattr(perf_counters_module, "perf_counters_enabled", lambda: True)
    monkeypatch.setattr(perf_counters_module, "reset_counters", lambda: None)
    perf_counters_module._state_var.set(None)
    middleware = PerfCounterMiddleware(FastAPI())
    request = Request({"type": "http", "method": "GET", "path": "/", "headers": []})

    async def _call_next(_request: Request) -> Response:
        return Response("ok")

    response = await middleware.dispatch(request, _call_next)

    assert response.headers["x-db-query-count"] == "0"
