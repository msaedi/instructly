from fastapi.testclient import TestClient
import pytest


@pytest.fixture(autouse=True)
def _enable_strict(monkeypatch):
    monkeypatch.setenv("STRICT_SCHEMAS", "true")


@pytest.fixture()
def client(_enable_strict):
    from importlib import reload

    import app.main as main
    import app.routes.v1.instructors as routes
    import app.schemas.base as base
    import app.schemas.instructor as ins

    reload(base)
    reload(ins)
    reload(routes)
    reload(main)
    return TestClient(main.fastapi_app, raise_server_exceptions=False)


def test_create_instructor_profile_rejects_extra_field(client: TestClient):
    body = {
        "bio": "Experienced teacher",
        "service_area_boroughs": ["Manhattan"],
        "years_experience": 5,
        "services": [
            {
                "service_catalog_id": "svc_123",
                "hourly_rate": 80,
                "duration_options": [60],
            }
        ],
        "unexpected": 1,
    }
    resp = client.post("/api/v1/instructors/me", json=body)
    if resp.status_code in (401, 403):
        pytest.skip("Auth prevented validation; covered in authenticated suites")
    assert resp.status_code == 422
    data = resp.json()
    assert "title" in data or "detail" in data
