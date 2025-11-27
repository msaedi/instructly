from fastapi.testclient import TestClient


def _make_token_for_user(user_email: str):
    from app.auth import create_access_token

    return create_access_token(data={"sub": user_email})


class TestBetaSettingsRoutes:
    def test_get_settings_requires_admin(self, client: TestClient, test_student):
        token = _make_token_for_user(test_student.email)
        headers = {"Authorization": f"Bearer {token}"}
        res = client.get("/api/v1/beta/settings", headers=headers)
        assert res.status_code == 403

    def test_update_settings_requires_admin(self, client: TestClient, test_student):
        token = _make_token_for_user(test_student.email)
        headers = {"Authorization": f"Bearer {token}"}
        res = client.put(
            "/api/v1/beta/settings",
            headers=headers,
            json={
                "beta_disabled": False,
                "beta_phase": "open_beta",
                "allow_signup_without_invite": False,
            },
        )
        assert res.status_code == 403

    def test_settings_round_trip_as_admin(self, client: TestClient, db):
        # Create admin user and token
        from app.core.enums import RoleName
        from app.models.user import User
        from app.services.permission_service import PermissionService

        admin = User(
            email="admin.settings@example.com",
            hashed_password="x",
            is_active=True,
            first_name="Beta",
            last_name="Admin",
            zip_code="10001",
        )
        db.add(admin)
        db.flush()
        PermissionService(db).assign_role(admin.id, RoleName.ADMIN)
        db.commit()

        token = _make_token_for_user(admin.email)
        headers = {"Authorization": f"Bearer {token}"}

        # GET should return defaults on first call
        res_get = client.get("/api/v1/beta/settings", headers=headers)
        assert res_get.status_code == 200
        data = res_get.json()
        assert set(data.keys()) == {"beta_disabled", "beta_phase", "allow_signup_without_invite"}

        # PUT update
        res_put = client.put(
            "/api/v1/beta/settings",
            headers=headers,
            json={
                "beta_disabled": False,
                "beta_phase": "open_beta",
                "allow_signup_without_invite": True,
            },
        )
        assert res_put.status_code == 200
        updated = res_put.json()
        assert updated["beta_phase"] == "open_beta"
        assert updated["allow_signup_without_invite"] is True

        # GET again should reflect changes
        res_get2 = client.get("/api/v1/beta/settings", headers=headers)
        assert res_get2.status_code == 200
        again = res_get2.json()
        assert again == updated
