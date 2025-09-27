from importlib import reload

from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest

from app.routes.messages import ReactionRequest


@pytest.fixture(autouse=True)
def _enable_strict(monkeypatch):
    monkeypatch.setenv("STRICT_SCHEMAS", "true")


@pytest.fixture()
def client(_enable_strict):
    import app.main as main
    import app.routes.messages as routes
    import app.schemas.base as base
    import app.schemas.message_requests as req

    reload(base)
    reload(req)
    reload(routes)
    reload(main)
    return TestClient(main.fastapi_app, raise_server_exceptions=False)


def test_send_message_rejects_extra_field(client: TestClient):
    body = {
        "booking_id": "bk_1",
        "content": "hello",
        "unexpected": 1,
    }
    resp = client.post("/api/messages/send", json=body)
    if resp.status_code in (401, 403):
        pytest.skip("Auth prevented validation; covered in authenticated suites")
    assert resp.status_code == 422
    data = resp.json()
    assert "title" in data or "detail" in data


def test_mark_read_rejects_extra_field(client: TestClient):
    body = {
        "booking_id": "bk_1",
        "unexpected": 1,
    }
    resp = client.post("/api/messages/mark-read", json=body)
    if resp.status_code in (401, 403):
        pytest.skip("Auth prevented validation; covered in authenticated suites")
    assert resp.status_code == 422
    data = resp.json()
    assert "title" in data or "detail" in data


def test_reaction_request_rejects_extra_field(client: TestClient):
    # Endpoint requires auth; we only verify validation when body is parsed
    resp = client.post("/api/messages/abc/reactions", json={"emoji": "👍", "unexpected": 1})
    if resp.status_code in (401, 403):
        pytest.skip("Auth prevented validation; covered in authenticated suites")
    assert resp.status_code == 422


def test_reaction_model_rejects_extra_field():
    with pytest.raises(ValidationError):
        ReactionRequest(emoji="👍", unexpected=1)
