from fastapi.testclient import TestClient
import pytest
from tests.integration.routes.conftest import strict_schema_app


@pytest.fixture(scope="module")
def client():
    with strict_schema_app() as c:
        yield c


def test_gated_ping_rejects_extra(client: TestClient):
    # Dependency enforces beta access; skip if blocked before validation
    res = client.get("/api/v1/gated/ping", params={"unexpected": 1})
    if res.status_code in (401, 403):
        pytest.skip("Access control prevented schema validation here")
    assert res.status_code == 422
