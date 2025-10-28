from __future__ import annotations

import pathlib
import sys

from fastapi import FastAPI
from fastapi.testclient import TestClient

BACKEND_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.middleware.perf_counters import (
    PerfCounterMiddleware,
    inc_db_query,
    note_cache_hit,
    note_cache_miss,
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
