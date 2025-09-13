import pytest
from fastapi.testclient import TestClient


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
