
from fastapi.testclient import TestClient

from app.main import fastapi_app as app


def test_health_headers_present():
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    # Headers should exist even if values are defaults
    assert "x-site-mode" in r.headers
    assert "x-phase" in r.headers
    assert "x-commit-sha" in r.headers


def test_cors_preflight_allows_allowed_origin():
    client = TestClient(app)
    # Use a default dev origin present in ALLOWED_ORIGINS at import time
    origin = "http://localhost:3000"
    r = client.options(
        "/api/v1/auth/login",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert r.status_code in (200, 204)
    assert r.headers.get("access-control-allow-origin") == origin
    assert r.headers.get("access-control-allow-credentials", "").lower() == "true"


def test_csrf_blocks_cross_origin_on_state_change(monkeypatch):
    # Put API in preview to enforce CSRF origin/referrer check
    monkeypatch.setenv("SITE_MODE", "preview")
    # Ensure CSRF origin checks are not disabled by the default test harness.
    monkeypatch.delenv("DISABLE_CSRF_FOR_TESTS", raising=False)
    client = TestClient(app)
    # Cross-site origin should be blocked before hitting route
    r = client.post(
        "/api/v1/bookings/",
        json={},
        headers={"Origin": "https://evil.example.com"},
    )
    assert r.status_code == 403
    body = r.json()
    assert body.get("code") == "CSRF_ORIGIN_MISMATCH"
