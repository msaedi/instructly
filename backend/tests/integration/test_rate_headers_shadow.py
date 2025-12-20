
from fastapi.testclient import TestClient

from app.main import fastapi_app


def test_read_route_has_rate_headers_shadow(monkeypatch):
    # Ensure global shadow is on
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("RATE_LIMIT_SHADOW", "true")

    client = TestClient(fastapi_app)
    # Use search route which we wired with read bucket
    # This route requires query param q; use a simple value
    r = client.get("/api/v1/search", params={"q": "piano"})
    assert r.status_code != 429
    assert "X-RateLimit-Remaining" in r.headers
    assert "X-RateLimit-Limit" in r.headers
    assert "X-RateLimit-Reset" in r.headers
