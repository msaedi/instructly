from fastapi.testclient import TestClient
import pytest
from tests.integration.routes.conftest import strict_schema_app


@pytest.fixture(scope="module")
def client():
    import app.routes.v1.beta as routes

    with strict_schema_app(routes) as c:
        yield c


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
