from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest
from tests.integration.routes.conftest import strict_schema_app

from app.routes.v1.messages import ReactionRequest


@pytest.fixture(scope="module")
def client():
    import app.routes.v1.messages as routes
    import app.schemas.message_requests as req

    with strict_schema_app(req, routes) as c:
        yield c


def test_mark_read_rejects_extra_field(client: TestClient):
    body = {
        "conversation_id": "conv_1",
        "unexpected": 1,
    }
    resp = client.post("/api/v1/messages/mark-read", json=body)
    if resp.status_code in (401, 403):
        pytest.skip("Auth prevented validation; covered in authenticated suites")
    assert resp.status_code == 422
    data = resp.json()
    assert "title" in data or "detail" in data


def test_reaction_request_rejects_extra_field(client: TestClient):
    # Endpoint requires auth; we only verify validation when body is parsed
    resp = client.post("/api/v1/messages/abc/reactions", json={"emoji": "👍", "unexpected": 1})
    if resp.status_code in (401, 403):
        pytest.skip("Auth prevented validation; covered in authenticated suites")
    assert resp.status_code == 422


def test_reaction_model_rejects_extra_field():
    with pytest.raises(ValidationError):
        ReactionRequest(emoji="👍", unexpected=1)
