from fastapi.testclient import TestClient
from starlette.responses import Response

from app.routes.v1 import health as health_routes


def test_health_includes_git_sha(client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("RENDER_GIT_COMMIT", "abc123")
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    payload = res.json()
    assert payload["git_sha"] == "abc123"


def test_health_lite_and_rate_limit_ok(client: TestClient) -> None:
    res = client.get("/api/v1/health/lite")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"

    res = client.get("/api/v1/health/rate-limit-test")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_apply_health_headers_handles_settings_error(monkeypatch) -> None:
    class _BrokenSettings:
        def __getattr__(self, _name):  # pragma: no cover - exercised in test
            raise RuntimeError("boom")

    monkeypatch.setenv("SITE_MODE", "local")
    monkeypatch.setattr(health_routes, "settings", _BrokenSettings())
    response = Response()

    health_routes._apply_health_headers(response)

    assert response.headers["X-Commit-Sha"]
