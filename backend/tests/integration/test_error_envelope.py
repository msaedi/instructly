import os

import pytest
from fastapi.testclient import TestClient

from app.main import fastapi_app


@pytest.fixture(autouse=True)
def _enable_strict_schemas(monkeypatch):
    monkeypatch.setenv("STRICT_SCHEMAS", "true")


client = TestClient(fastapi_app, raise_server_exceptions=False)


def test_404_problem_json():
    resp = client.get("/does-not-exist")
    assert resp.status_code == 404
    assert resp.headers.get("content-type", "").startswith("application/problem+json")
    body = resp.json()
    assert body.get("status") == 404
    assert body.get("title")
    assert body.get("type")


def test_forced_500_problem_json(monkeypatch):
    # Add a transient route for testing that raises an exception
    from fastapi import APIRouter

    router = APIRouter()

    @router.get("/test/boom")
    def boom():  # pragma: no cover - simple raise for handler wiring
        raise RuntimeError("boom")

    fastapi_app.include_router(router)

    resp = client.get("/test/boom")
    assert resp.status_code == 500
    assert resp.headers.get("content-type", "").startswith("application/problem+json")
    body = resp.json()
    assert body.get("status") == 500
    assert body.get("title")
    assert body.get("type")
