from instainstru_mcp.server import _attach_health_route
from starlette.applications import Starlette
from starlette.testclient import TestClient


def test_health_includes_git_sha(monkeypatch):
    monkeypatch.setenv("GIT_SHA", "abc123")
    app = Starlette()
    _attach_health_route(app)
    client = TestClient(app)

    res = client.get("/api/v1/health")
    assert res.status_code == 200
    assert res.json()["git_sha"] == "abc123"
