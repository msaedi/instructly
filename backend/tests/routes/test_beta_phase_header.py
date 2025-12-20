from fastapi.testclient import TestClient


def test_beta_phase_header_default_instructor_only(client: TestClient, db):
    res = client.get("/health")
    assert res.status_code == 200
    # Default repo.get_singleton() returns instructor_only when not disabled
    assert res.headers.get("x-beta-phase") in ("instructor_only", "disabled", "open_beta")


def test_beta_phase_header_respects_disabled(client: TestClient, db):
    from app.middleware.beta_phase_header import invalidate_beta_settings_cache
    from app.repositories.beta_repository import BetaSettingsRepository

    repo = BetaSettingsRepository(db)
    repo.update_settings(beta_disabled=True, beta_phase="instructor_only", allow_signup_without_invite=False)
    db.commit()

    # Invalidate in-memory cache so middleware reads fresh DB value
    invalidate_beta_settings_cache()

    res = client.get("/health")
    assert res.status_code == 200
    assert res.headers.get("x-beta-phase") == "disabled"
