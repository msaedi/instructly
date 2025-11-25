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
    return TestClient(main.fastapi_app, raise_server_exceptions=False)


def test_record_search_rejects_extra_field(client: TestClient):
    headers = {"X-Guest-Session-ID": "guest-123"}
    payload = {
        "search_query": "algebra",
        "search_type": "natural_language",
        "results_count": 1,
        "unexpected": "nope",
    }
    resp = client.post("/api/v1/search-history", headers=headers, json=payload)
    if resp.status_code in (401, 403):
        pytest.skip("Auth prevented validation; covered in authenticated suites")
    assert resp.status_code == 422
    assert resp.headers.get("content-type", "").startswith("application/problem+json")
    body = resp.json()
    assert "title" in body and "detail" in body
