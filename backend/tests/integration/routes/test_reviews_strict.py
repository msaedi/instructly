from importlib import reload
import os

from fastapi.testclient import TestClient
import pytest


@pytest.fixture(scope="module")
def client():
    old = os.environ.get("STRICT_SCHEMAS")
    os.environ["STRICT_SCHEMAS"] = "true"

    import app.main as main
    import app.routes.v1.reviews as routes  # Phase 12: Reviews migrated to v1
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


def test_submit_review_rejects_extra_field(client: TestClient):
    body = {
        "booking_id": "bk_123",
        "rating": 5,
        "review_text": "great",
        "unexpected": 1,
    }
    # Phase 12: Reviews migrated to /api/v1/reviews
    resp = client.post("/api/v1/reviews", json=body)
    if resp.status_code in (401, 403):
        pytest.skip("Auth prevented validation; covered in authenticated suites")
    assert resp.status_code == 422
    data = resp.json()
    assert "title" in data or "detail" in data
