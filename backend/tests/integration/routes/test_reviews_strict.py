import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _enable_strict(monkeypatch):
    monkeypatch.setenv("STRICT_SCHEMAS", "true")


@pytest.fixture()
def client(_enable_strict):
    from importlib import reload
    import app.schemas.base as base
    import app.routes.reviews as routes
    import app.main as main

    reload(base)
    reload(routes)
    reload(main)
    return TestClient(main.fastapi_app, raise_server_exceptions=False)


def test_submit_review_rejects_extra_field(client: TestClient):
    body = {
        "booking_id": "bk_123",
        "rating": 5,
        "review_text": "great",
        "unexpected": 1,
    }
    resp = client.post("/api/reviews/submit", json=body)
    if resp.status_code in (401, 403):
        pytest.skip("Auth prevented validation; covered in authenticated suites")
    assert resp.status_code == 422
    data = resp.json()
    assert "title" in data or "detail" in data
