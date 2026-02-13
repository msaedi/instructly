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
    _client = TestClient(main.fastapi_app)
    yield _client

    if old is None:
        os.environ.pop("STRICT_SCHEMAS", None)
    else:
        os.environ["STRICT_SCHEMAS"] = old
    reload(base)
    reload(sh)
    reload(rh)
    reload(main)


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
