from importlib import reload
import os

from fastapi.testclient import TestClient
import pytest


@pytest.fixture(scope="module")
def client():
    old = os.environ.get("STRICT_SCHEMAS")
    os.environ["STRICT_SCHEMAS"] = "true"

    import app.main as main
    import app.routes.v1.services as routes
    import app.schemas.base as base
    import app.schemas.service_catalog as sc

    reload(base)
    reload(sc)
    reload(routes)
    reload(main)
    _client = TestClient(main.fastapi_app, raise_server_exceptions=False)
    yield _client

    if old is None:
        os.environ.pop("STRICT_SCHEMAS", None)
    else:
        os.environ["STRICT_SCHEMAS"] = old
    reload(base)
    reload(sc)
    reload(routes)
    reload(main)


def test_add_service_rejects_extra_field(client: TestClient):
    # Endpoint requires auth; we only verify validation behavior
    body = {
        "catalog_service_id": "svc_123",
        "hourly_rate": 80,
        "custom_description": "desc",
        "duration_options": [60],
        "unexpected": 1,
    }
    # Phase 13: Services migrated to /api/v1/services
    resp = client.post("/api/v1/services/instructor/add", json=body)
    if resp.status_code in (401, 403):
        pytest.skip("Auth prevented validation; covered in authenticated suites")
    assert resp.status_code == 422
    data = resp.json()
    assert "title" in data or "detail" in data
