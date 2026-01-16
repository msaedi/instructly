from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app import errors


def _make_app(monkeypatch, strict: bool) -> FastAPI:
    if strict:
        monkeypatch.setenv("STRICT_SCHEMAS", "true")
    else:
        monkeypatch.delenv("STRICT_SCHEMAS", raising=False)

    app = FastAPI()
    errors.register_error_handlers(app)
    return app


def test_parse_detail_variants() -> None:
    detail_text, code, extras = errors._parse_detail({"code": "X", "detail": "msg"})
    assert detail_text == "msg"
    assert code == "X"
    assert extras is None

    detail_text, code, extras = errors._parse_detail("plain")
    assert detail_text == "plain"
    assert code is None
    assert extras is None

    detail_text, code, extras = errors._parse_detail(None)
    assert detail_text is None
    assert code is None
    assert extras is None

    detail_text, code, extras = errors._parse_detail(123)
    assert detail_text == "123"
    assert code is None
    assert extras is None


def test_http_exception_handler_strict(monkeypatch) -> None:
    app = _make_app(monkeypatch, strict=True)

    @app.get("/http")
    def _raise_http() -> None:
        raise HTTPException(
            status_code=418,
            detail={
                "message": "teapot",
                "code": "TEAPOT",
                "title": "I'm a teapot",
                "error": "short",
                "current_version": "1.2.3",
                "checkr_error": {"oops": True},
            },
        )

    client = TestClient(app)
    response = client.get("/http")

    assert response.status_code == 418
    assert response.headers["content-type"].startswith("application/problem+json")
    payload = response.json()
    assert payload["title"] == "I'm a teapot"
    assert payload["detail"] == "teapot"
    assert payload["code"] == "TEAPOT"
    assert payload["error"] == "short"
    assert payload["current_version"] == "1.2.3"
    assert payload["checkr_error"] == {"oops": True}


def test_request_validation_handler_non_strict(monkeypatch) -> None:
    app = _make_app(monkeypatch, strict=False)

    @app.get("/validate")
    def _validate(q: int) -> dict[str, int]:
        return {"q": q}

    client = TestClient(app)
    response = client.get("/validate", params={"q": "nope"})

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/json")
    payload = response.json()
    assert payload["code"] == "validation_error"
    assert isinstance(payload["errors"], list)


def test_request_validation_handler_strict(monkeypatch) -> None:
    app = _make_app(monkeypatch, strict=True)

    @app.get("/validate")
    def _validate(q: int) -> dict[str, int]:
        return {"q": q}

    client = TestClient(app)
    response = client.get("/validate", params={"q": "nope"})

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    payload = response.json()
    assert payload["code"] == "validation_error"
    assert payload["detail"] == "Request validation failed"


def test_pydantic_validation_handler(monkeypatch) -> None:
    app = _make_app(monkeypatch, strict=True)

    class Payload(BaseModel):
        value: int

    @app.get("/pydantic")
    def _raise_validation() -> dict[str, Any]:
        Payload.model_validate({"value": "bad"})
        return {"ok": True}

    client = TestClient(app)
    response = client.get("/pydantic")

    assert response.status_code == 422
    assert response.json()["detail"] == "Validation failed"


def test_generic_exception_handler(monkeypatch) -> None:
    app = _make_app(monkeypatch, strict=True)

    @app.get("/boom")
    def _boom() -> None:
        raise RuntimeError("boom")

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/boom")

    assert response.status_code == 500
    assert response.json()["code"] == "internal_server_error"
