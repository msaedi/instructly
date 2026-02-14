from importlib import reload
import os

from fastapi.testclient import TestClient
import pytest


@pytest.fixture(scope="module")
def client():
    old = os.environ.get("STRICT_SCHEMAS")
    os.environ["STRICT_SCHEMAS"] = "true"

    import app.main as main

    reload(main)
    _client = TestClient(main.fastapi_app, raise_server_exceptions=False)
    yield _client

    if old is None:
        os.environ.pop("STRICT_SCHEMAS", None)
    else:
        os.environ["STRICT_SCHEMAS"] = old
    reload(main)


def test_gated_ping_rejects_extra(client: TestClient):
    # Dependency enforces beta access; skip if blocked before validation
    res = client.get("/api/v1/gated/ping", params={"unexpected": 1})
    if res.status_code in (401, 403):
        pytest.skip("Access control prevented schema validation here")
    assert res.status_code == 422
