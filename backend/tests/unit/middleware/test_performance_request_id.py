from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.request_context import get_request_id
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
