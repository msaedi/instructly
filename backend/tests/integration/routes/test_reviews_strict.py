from fastapi.testclient import TestClient
import pytest
from tests.integration.routes.conftest import strict_schema_app


@pytest.fixture(scope="module")
def client():
    import app.routes.v1.reviews as routes
    with strict_schema_app(routes) as c:
        yield c


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
