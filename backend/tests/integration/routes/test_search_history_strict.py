from importlib import reload
import os

from fastapi.testclient import TestClient
import pytest


@pytest.fixture(scope="module")
def client():
    old = os.environ.get("STRICT_SCHEMAS")
    os.environ["STRICT_SCHEMAS"] = "true"

    import app.main as main
    import app.routes.v1.search_history as rh
    import app.schemas.base as base
    import app.schemas.search_history as sh

    reload(base)
    reload(sh)
    reload(rh)
    reload(main)
    _client = TestClient(main.fastapi_app, raise_server_exceptions=False)
    yield _client

    if old is None:
        os.environ.pop("STRICT_SCHEMAS", None)
    else:
        os.environ["STRICT_SCHEMAS"] = old
    reload(base)
    reload(sh)
    reload(rh)
    reload(main)


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
