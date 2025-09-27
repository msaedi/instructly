from fastapi.testclient import TestClient
import pytest


@pytest.fixture(autouse=True)
def _enable_strict_schemas(monkeypatch):
    monkeypatch.setenv("STRICT_SCHEMAS", "true")


@pytest.fixture()
def client(_enable_strict_schemas):
    from importlib import reload

    import app.main as main

    reload(main)
    return TestClient(main.fastapi_app, raise_server_exceptions=False)


def test_404_problem_json(client: TestClient):
    resp = client.get("/does-not-exist")
    assert resp.status_code == 404
    assert resp.headers.get("content-type", "").startswith("application/problem+json")
    body = resp.json()
    assert body.get("status") == 404
    assert body.get("title")
    assert body.get("type")


def test_forced_500_problem_json(client: TestClient):
    # Add a transient route for testing that raises an exception
    from fastapi import APIRouter

    import app.main as main

    router = APIRouter()

    @router.get("/test/boom")
    def boom():  # pragma: no cover - simple raise for handler wiring
        raise RuntimeError("boom")

    before_len = len(main.fastapi_app.router.routes)
    main.fastapi_app.include_router(router)
    try:
        resp = client.get("/test/boom")
    finally:
        # Remove the transient routes to avoid polluting global app for later tests
        main.fastapi_app.router.routes = main.fastapi_app.router.routes[:before_len]
    assert resp.status_code == 500
    assert resp.headers.get("content-type", "").startswith("application/problem+json")
    body = resp.json()
    assert body.get("status") == 500
    assert body.get("title")
    assert body.get("type")


def test_422_problem_json_wrong_type(client: TestClient):
    # Mount a transient route that requires a typed body and triggers 422 on wrong types
    from fastapi import APIRouter
    from pydantic import BaseModel

    import app.main as main

    class Payload(BaseModel):
        a: int
        b: str

    router = APIRouter()

    @router.post("/test/validate")
    def validate(p: Payload):  # pragma: no cover - simple echo endpoint
        return {"ok": True}

    before_len = len(main.fastapi_app.router.routes)
    main.fastapi_app.include_router(router)
    try:
        r = client.post("/test/validate", json={"a": "not-int", "b": 123})
    finally:
        main.fastapi_app.router.routes = main.fastapi_app.router.routes[:before_len]
    assert r.status_code == 422
    assert r.headers.get("content-type", "").lower().startswith("application/problem+json")
    body = r.json()
    assert body.get("title")
    assert body.get("status") == 422


def test_422_problem_json_missing_required(client: TestClient):
    from fastapi import APIRouter
    from pydantic import BaseModel

    import app.main as main

    class Payload(BaseModel):
        a: int
        b: str

    router = APIRouter()

    @router.post("/test/validate2")
    def validate2(p: Payload):  # pragma: no cover - simple echo endpoint
        return {"ok": True}

    before_len = len(main.fastapi_app.router.routes)
    main.fastapi_app.include_router(router)
    try:
        r = client.post("/test/validate2", json={})
    finally:
        main.fastapi_app.router.routes = main.fastapi_app.router.routes[:before_len]
    assert r.status_code == 422
    assert r.headers.get("content-type", "").lower().startswith("application/problem+json")
    body = r.json()
    assert body.get("title")
    assert body.get("status") == 422


def test_422_problem_json_extra_field(client: TestClient):
    from fastapi import APIRouter
    from pydantic import BaseModel, ConfigDict

    import app.main as main

    class StrictPayload(BaseModel):
        model_config = ConfigDict(extra="forbid")
        a: int

    router = APIRouter()

    @router.post("/test/strict")
    def strict(p: StrictPayload):  # pragma: no cover - simple echo endpoint
        return {"ok": True}

    before_len = len(main.fastapi_app.router.routes)
    main.fastapi_app.include_router(router)
    try:
        r = client.post("/test/strict", json={"a": 1, "b": "extra"})
    finally:
        main.fastapi_app.router.routes = main.fastapi_app.router.routes[:before_len]
    assert r.status_code == 422
    ct = r.headers.get("content-type", "")
    assert ct.lower().startswith("application/problem+json")
    body = r.json()
    assert body.get("status") == 422
    assert isinstance(body.get("errors"), list)
