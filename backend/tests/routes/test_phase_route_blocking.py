from fastapi.testclient import TestClient


def _make_token_for_user(user_email: str):
    from app.auth import create_access_token

    return create_access_token(data={"sub": user_email})


class TestPhaseRouteBlocking:
    def test_search_blocked_without_open_beta(self, client: TestClient, db):
        # Ensure beta is enabled and phase is instructor_only
        from app.repositories.beta_repository import BetaSettingsRepository

        settings_repo = BetaSettingsRepository(db)
        settings_repo.update_settings(
            beta_disabled=False, beta_phase="instructor_only", allow_signup_without_invite=False
        )
        db.commit()

        # Hitting the search endpoint (phase-gated) should 403 when authenticated under instructor_only
        _res = client.get("/api/search/instructors", params={"q": "piano"})
        # Since dependency requires auth, we expect 401 or 403 depending on setup; but phase dependency should 403
        # Ensure we get 403 if authenticated but phase is not open
        from app.models.user import User

        u = User(
            email="student1@example.com",
            hashed_password="x",
            is_active=True,
            first_name="Stu",
            last_name="Dent",
            zip_code="10001",
        )
        db.add(u)
        db.commit()
        token = _make_token_for_user(u.email)
        headers = {"Authorization": f"Bearer {token}"}
        res2 = client.get(
            "/api/search/instructors",
            params={"q": "piano"},
            headers={**headers, "x-enforce-beta-checks": "1"},
        )
        assert res2.status_code == 403

    def test_search_allowed_when_beta_disabled(self, client: TestClient, db):
        # Flip settings to disable beta
        from app.repositories.beta_repository import BetaSettingsRepository

        repo = BetaSettingsRepository(db)
        repo.update_settings(beta_disabled=True, beta_phase="instructor_only", allow_signup_without_invite=False)
        db.commit()

        res = client.get("/api/search/instructors", params={"q": "piano"})
        # Unauthenticated search can now proceed (public search), but our endpoint expects only query validation
        assert res.status_code in (200, 400)  # 200 if service returns, 400 if empty/trivial input handling kicks in
