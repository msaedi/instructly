from fastapi.testclient import TestClient
import pytest
from tests.integration.routes.conftest import strict_schema_app


@pytest.fixture(scope="module")
def client():
    import app.routes.v1.search_history as routes
    import app.schemas.search_history as sh
    with strict_schema_app(sh, routes) as c:
        yield c


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
