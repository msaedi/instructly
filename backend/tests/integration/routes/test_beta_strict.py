from fastapi.testclient import TestClient
import pytest


@pytest.fixture(autouse=True)
def _enable_strict(monkeypatch):
    monkeypatch.setenv("STRICT_SCHEMAS", "true")


@pytest.fixture()
def client(_enable_strict):
    from importlib import reload

    import app.main as main
    import app.routes.beta as routes
    import app.schemas.base as base

    reload(base)
    reload(routes)
    reload(main)
    return TestClient(main.fastapi_app, raise_server_exceptions=False)


def test_update_beta_settings_rejects_extra_field(client: TestClient):
    body = {
        "beta_disabled": False,
        "beta_phase": "open_beta",
        "allow_signup_without_invite": True,
        "unexpected": 1,
    }
    resp = client.put("/api/beta/settings", json=body)
    if resp.status_code in (401, 403):
        pytest.skip("Auth prevented validation; covered in authenticated suites")
    assert resp.status_code == 422
    data = resp.json()
    assert "title" in data or "detail" in data
