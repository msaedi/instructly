import os

import pytest
from fastapi.testclient import TestClient

from app.auth import create_access_token
from app.main import fastapi_app as app
from app.models.user import User


def _set_env(site_mode: str, phase: str = "beta"):
    os.environ["SITE_MODE"] = site_mode
    os.environ["PHASE"] = phase


@pytest.fixture
def client(db):
    # Reuse the app from conftest but allow header overrides
    return TestClient(app)


def _auth_headers_for(user: User) -> dict[str, str]:
    token = create_access_token(data={"sub": user.email})
    return {"Authorization": f"Bearer {token}"}


class TestPreviewNoGates:
    def test_preview_bypasses_beta_for_bookings(self, monkeypatch, client: TestClient, test_student: User):
        _set_env("preview", "beta")
        headers = _auth_headers_for(test_student)
        r = client.get(
            "/bookings/?exclude_future_confirmed=true&per_page=1&page=1",
            headers=headers,
        )
        # Should not be gated in preview, auth still required (we provided it)
        assert r.status_code in (200, 204), r.text


class TestProdPhaseBehavior:
    def test_prod_beta_requires_beta_grant(self, monkeypatch, client: TestClient, test_student: User):
        _set_env("prod", "beta")
        headers = _auth_headers_for(test_student)
        r = client.get(
            "/bookings/?exclude_future_confirmed=true&per_page=1&page=1",
            headers=headers,
        )
        assert r.status_code == 403

    def test_prod_open_allows_without_beta_grant(self, monkeypatch, client: TestClient, test_student: User, db):
        _set_env("prod", "open")
        # Also toggle DB BetaSettings to open_beta if present
        try:
            from app.repositories.beta_repository import BetaSettingsRepository

            repo = BetaSettingsRepository(db)
            s = repo.get_singleton()
            if s:
                s.beta_phase = "open_beta"
                db.add(s)
                db.commit()
        except Exception:
            pass

        headers = _auth_headers_for(test_student)
        r = client.get(
            "/bookings/?exclude_future_confirmed=true&per_page=1&page=1",
            headers=headers,
        )
        assert r.status_code in (200, 204), r.text


def test_health_headers_reflect_mode_phase(monkeypatch, client: TestClient, db):
    _set_env("preview", "beta")
    res = client.get("/health")
    assert res.status_code == 200
    assert res.headers.get("X-Site-Mode") == "preview"
    assert res.headers.get("X-Phase") in {"beta", "instructor_only", "open_beta", "open"}
