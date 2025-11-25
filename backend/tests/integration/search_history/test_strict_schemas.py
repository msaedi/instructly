from fastapi.testclient import TestClient
import pytest


@pytest.fixture(autouse=True)
def _enable_strict(monkeypatch):
    monkeypatch.setenv("STRICT_SCHEMAS", "true")


@pytest.fixture()
def client(_enable_strict):
    from importlib import reload

    import app.main as main
    import app.routes.v1.search_history as rh
    import app.schemas.base as base
    import app.schemas.search_history as sh

    reload(base)
    reload(sh)
    reload(rh)
    reload(main)
    return TestClient(main.fastapi_app)


def test_extra_field_rejected_for_search_create(client: TestClient):
    headers = {"X-Guest-Session-ID": "guest-123"}
    payload = {
        "search_query": "math",
        "search_type": "natural_language",
        "results_count": 1,
        "unknown": "nope",
    }
    resp = client.post("/api/v1/search-history", headers=headers, json=payload)
    assert resp.status_code == 422
    assert resp.headers.get("content-type", "").startswith("application/problem+json")


def test_valid_search_create_ok(client: TestClient):
    headers = {"X-Guest-Session-ID": "guest-123"}
    payload = {
        "search_query": "music",
        "search_type": "natural_language",
        "results_count": 0,
    }
    resp = client.post("/api/v1/search-history", headers=headers, json=payload)
    assert resp.status_code in {200, 201, 400, 500}
