import os

from fastapi.testclient import TestClient
import pytest

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
            "/api/v1/bookings/?exclude_future_confirmed=true&per_page=1&page=1",
            headers=headers,
        )
        # Should not be gated in preview, auth still required (we provided it)
        assert r.status_code in (200, 204), r.text

    def test_preview_bypasses_beta_for_search(self, monkeypatch, client: TestClient, test_student: User):
        _set_env("preview", "beta")
        headers = _auth_headers_for(test_student)
        r = client.get("/api/search/instructors", params={"q": "piano", "limit": 1}, headers=headers)
        assert r.status_code in (200, 204), r.text


class TestProdPhaseBehavior:
    def test_prod_beta_requires_beta_grant(self, monkeypatch, client: TestClient, test_student: User, db):
        _set_env("prod", "beta")
        # Ensure DB beta settings are in a gated phase
        try:
            from app.repositories.beta_repository import BetaSettingsRepository

            settings_repo = BetaSettingsRepository(db)
            settings_repo.update_settings(
                beta_disabled=False, beta_phase="instructor_only", allow_signup_without_invite=False
            )
            db.commit()
        except Exception:
            pass

        headers = _auth_headers_for(test_student)
        # Disable the default testing bypass so beta checks are enforced in tests
        headers["x-enforce-beta-checks"] = "1"
        r = client.get(
            "/api/v1/bookings/?exclude_future_confirmed=true&per_page=1&page=1",
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
            "/api/v1/bookings/?exclude_future_confirmed=true&per_page=1&page=1",
            headers=headers,
        )
        assert r.status_code in (200, 204), r.text

    def test_prod_open_allows_search(self, monkeypatch, client: TestClient, test_student: User, db):
        _set_env("prod", "open")
        headers = _auth_headers_for(test_student)
        r = client.get("/api/search/instructors", params={"q": "piano", "limit": 1}, headers=headers)
        assert r.status_code in (200, 204), r.text


def test_health_headers_reflect_mode_phase(monkeypatch, client: TestClient, db):
    _set_env("preview", "beta")
    res = client.get("/health")
    assert res.status_code == 200
    assert res.headers.get("X-Site-Mode") == "preview"
    assert res.headers.get("X-Phase") in {"beta", "instructor_only", "open_beta", "open"}
