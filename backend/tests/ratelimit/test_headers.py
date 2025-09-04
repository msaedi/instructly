from fastapi import Depends, FastAPI, Response
from fastapi.testclient import TestClient

from app.ratelimit.dependency import rate_limit
from app.ratelimit.headers import set_rate_headers


def test_set_rate_headers_basic():
    res = Response()
    set_rate_headers(res, remaining=5, limit=10, reset_epoch_s=1234567890, retry_after_s=None)
    assert res.headers["X-RateLimit-Remaining"] == "5"
    assert res.headers["X-RateLimit-Limit"] == "10"
    assert res.headers["X-RateLimit-Reset"] == "1234567890"
    assert "Retry-After" not in res.headers


def test_dependency_sets_headers(monkeypatch):
    # Create app and route using dependency
    app = FastAPI()

    @app.get("/dummy", dependencies=[Depends(rate_limit("read"))])
    def dummy():
        return {"ok": True}

    # Use test client
    client = TestClient(app)
    r = client.get("/dummy")
    assert r.status_code in (200, 429)  # shadow mode should allow; but don't depend on env
    assert "X-RateLimit-Remaining" in r.headers
    assert "X-RateLimit-Limit" in r.headers
    assert "X-RateLimit-Reset" in r.headers
