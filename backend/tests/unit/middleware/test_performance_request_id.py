from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.request_context import get_request_id
from app.middleware import performance as performance_module
from app.middleware.performance import PerformanceMiddleware


def _make_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(PerformanceMiddleware)

    @app.get("/ping")
    def _ping() -> dict[str, str | None]:
        return {"request_id": get_request_id()}

    return app


def test_performance_middleware_sets_request_id_from_header() -> None:
    app = _make_app()
    client = TestClient(app)
    response = client.get("/ping", headers={"X-Request-ID": "req-abc"})

    assert response.status_code == 200
    assert response.json()["request_id"] == "req-abc"
    assert response.headers["X-Request-ID"] == "req-abc"
    assert get_request_id() is None


def test_performance_middleware_generates_request_id() -> None:
    app = _make_app()
    client = TestClient(app)
    response = client.get("/ping")

    request_id = response.json()["request_id"]
    assert response.status_code == 200
    assert isinstance(request_id, str)
    assert request_id
    assert response.headers["X-Request-ID"] == request_id
    assert get_request_id() is None


def test_performance_middleware_sets_trace_id_header(monkeypatch) -> None:
    monkeypatch.setattr(performance_module, "is_otel_enabled", lambda: True)
    monkeypatch.setattr(performance_module, "get_current_trace_id", lambda: "trace-123")

    app = _make_app()
    client = TestClient(app)
    response = client.get("/ping")

    assert response.status_code == 200
    assert response.headers["X-Trace-ID"] == "trace-123"


def test_performance_middleware_skips_trace_header_when_disabled(monkeypatch) -> None:
    monkeypatch.setattr(performance_module, "is_otel_enabled", lambda: False)
    monkeypatch.setattr(performance_module, "get_current_trace_id", lambda: "trace-should-not-appear")

    app = _make_app()
    client = TestClient(app)
    response = client.get("/ping")

    assert response.status_code == 200
    assert "X-Trace-ID" not in response.headers
