from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app import errors

REQUEST_ID = "req-test-123"


def _make_app(monkeypatch, strict: bool) -> FastAPI:
    if strict:
        monkeypatch.setenv("STRICT_SCHEMAS", "true")
    else:
        monkeypatch.delenv("STRICT_SCHEMAS", raising=False)

    app = FastAPI()

    @app.middleware("http")
    async def _inject_request_id(request, call_next):  # type: ignore[no-untyped-def]
        request.state.request_id = REQUEST_ID
        response = await call_next(request)
        response.headers["X-Request-ID"] = REQUEST_ID
        return response

    errors.register_error_handlers(app)

    @app.get("/boom")
    def _boom() -> None:
        raise RuntimeError("boom")

    @app.get("/bad-request")
    def _bad_request() -> None:
        raise HTTPException(status_code=400, detail="bad")

    @app.get("/validate")
    def _validate(q: int) -> dict[str, int]:
        return {"q": q}

    return app


def _assert_request_id(response) -> None:
    payload = response.json()
    assert payload["request_id"] == REQUEST_ID
    assert response.headers["x-request-id"] == REQUEST_ID


def test_http_exception_includes_request_id(monkeypatch) -> None:
    client = TestClient(_make_app(monkeypatch, strict=True))
    response = client.get("/bad-request")
    assert response.status_code == 400
    _assert_request_id(response)


def test_validation_error_includes_request_id(monkeypatch) -> None:
    client = TestClient(_make_app(monkeypatch, strict=True))
    response = client.get("/validate", params={"q": "nope"})
    assert response.status_code == 422
    _assert_request_id(response)


def test_unhandled_exception_includes_request_id(monkeypatch) -> None:
    client = TestClient(_make_app(monkeypatch, strict=True), raise_server_exceptions=False)
    response = client.get("/boom")
    assert response.status_code == 500
    _assert_request_id(response)
