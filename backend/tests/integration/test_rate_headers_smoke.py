from fastapi.testclient import TestClient

from app.main import app as asgi_app


def test_smoke_rate_headers_present():
    client = TestClient(asgi_app)

    # health
    r = client.get("/health")
    assert r.status_code == 200
    assert "X-RateLimit-Limit" in r.headers
    assert "X-RateLimit-Remaining" in r.headers

    # representative read route
    r = client.get("/api/search/instructors", params={"q": "piano"})
    assert r.status_code in (200, 401, 403)
    assert "X-RateLimit-Limit" in r.headers
    assert "X-RateLimit-Remaining" in r.headers

    # representative write route (shadow/enforced in prod; disabled in tests)
    r = client.post("/api/v1/instructors/me", json={"bio": "test"})
    assert r.status_code in (200, 201, 401, 403)
    assert "X-RateLimit-Limit" in r.headers
    assert "X-RateLimit-Remaining" in r.headers
