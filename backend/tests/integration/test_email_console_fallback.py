from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import fastapi_app as app


def test_console_email_provider(monkeypatch):
    monkeypatch.setattr(settings, "email_provider", "console", raising=False)
    with TestClient(app) as client:
        resp = client.get("/health")
        assert resp.status_code == 200
