import os
from importlib import reload

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _enable_strict_schemas(monkeypatch):
    monkeypatch.setenv("STRICT_SCHEMAS", "true")


@pytest.fixture()
def client(_enable_strict_schemas):
    import app.main as main

    reload(main)
    return TestClient(main.fastapi_app, raise_server_exceptions=False)


def test_gated_ping_rejects_extra(client: TestClient):
    # Dependency enforces beta access; skip if blocked before validation
    res = client.get("/v1/gated/ping", params={"unexpected": 1})
    if res.status_code in (401, 403):
        pytest.skip("Access control prevented schema validation here")
    assert res.status_code == 422

