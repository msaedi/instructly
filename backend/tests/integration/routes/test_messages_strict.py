import os
from import importlib
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


def test_reaction_request_rejects_extra_field(client: TestClient):
    # Endpoint requires auth; we only verify validation when body is parsed
    resp = client.post("/api/messages/abc/reactions", json={"emoji": "👍", "unexpected": 1})
    if resp.status_code == 401:
        pytest.skip("Auth prevented validation; covered in authenticated suites")
    assert resp.status_code == 422
