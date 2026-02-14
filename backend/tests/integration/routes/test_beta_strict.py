from importlib import reload
import os

from fastapi.testclient import TestClient
import pytest


@pytest.fixture(scope="module")
def client():
    old = os.environ.get("STRICT_SCHEMAS")
    os.environ["STRICT_SCHEMAS"] = "true"

    import app.main as main
    import app.routes.v1.beta as routes
    import app.schemas.base as base

    reload(base)
    reload(routes)
    reload(main)
    _client = TestClient(main.fastapi_app, raise_server_exceptions=False)
    yield _client

    if old is None:
        os.environ.pop("STRICT_SCHEMAS", None)
    else:
        os.environ["STRICT_SCHEMAS"] = old
    reload(base)
    reload(routes)
    reload(main)


def test_update_beta_settings_rejects_extra_field(client: TestClient):
    body = {
        "beta_disabled": False,
        "beta_phase": "open_beta",
        "allow_signup_without_invite": True,
        "unexpected": 1,
    }
    resp = client.put("/api/v1/beta/settings", json=body)
    if resp.status_code in (401, 403):
        pytest.skip("Auth prevented validation; covered in authenticated suites")
    assert resp.status_code == 422
    data = resp.json()
    assert "title" in data or "detail" in data
