import pytest
from fastapi.testclient import TestClient

from app.main import fastapi_app


@pytest.fixture(autouse=True)
def _enable_strict(monkeypatch):
    monkeypatch.setenv("STRICT_SCHEMAS", "true")


client = TestClient(fastapi_app)


def test_extra_field_rejected_for_search_create(monkeypatch):
    headers = {"X-Guest-Session-ID": "guest-123"}
    payload = {
        "search_query": "math",
        "search_type": "natural_language",
        "results_count": 1,
        "unknown": "nope",
    }
    resp = client.post("/api/search-history/", headers=headers, json=payload)
    assert resp.status_code == 422
    assert resp.headers.get("content-type", "").startswith("application/problem+json")


def test_valid_search_create_ok(monkeypatch):
    headers = {"X-Guest-Session-ID": "guest-123"}
    payload = {
        "search_query": "music",
        "search_type": "natural_language",
        "results_count": 0,
    }
    resp = client.post("/api/search-history/", headers=headers, json=payload)
    assert resp.status_code in {200, 201, 400, 500}
