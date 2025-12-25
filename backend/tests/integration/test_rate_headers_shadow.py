from fastapi.testclient import TestClient
import pytest


def test_read_route_has_rate_headers_shadow(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    """Verify rate limit headers are present in shadow mode."""
    # Ensure global shadow is on
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("RATE_LIMIT_SHADOW", "true")

    # Use shared client fixture from conftest
    # Use search route which we wired with read bucket
    # This route requires query param q; use a simple value
    r = client.get("/api/v1/search", params={"q": "piano"})
    assert r.status_code != 429
    assert "X-RateLimit-Remaining" in r.headers
    assert "X-RateLimit-Limit" in r.headers
    assert "X-RateLimit-Reset" in r.headers
