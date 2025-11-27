from fastapi.testclient import TestClient


def _create_invite(db, email: str | None = None):
    from app.services.beta_service import BetaService

    svc = BetaService(db)
    created = svc.bulk_generate(
        count=1,
        role="instructor_beta",
        expires_in_days=7,
        source="tests",
        emails=[email] if email else None,
    )
    return created[0].code


def _make_token_for_user(user_email: str):
    from app.auth import create_access_token

    return create_access_token(data={"sub": user_email})


class TestBetaRoutes:
    def test_validate_invite_not_found(self, client: TestClient):
        res = client.get("/api/v1/beta/invites/validate", params={"code": "NOPE0001"})
        assert res.status_code == 200
        data = res.json()
        assert data["valid"] is False
        assert data["reason"] == "not_found"

    def test_generate_invites_requires_admin(self, client: TestClient, test_student):
        # Non-admin should get 403 from require_role("admin")
        token = _make_token_for_user(test_student.email)
        headers = {"Authorization": f"Bearer {token}"}
        res = client.post(
            "/api/v1/beta/invites/generate",
            headers=headers,
            json={"count": 1, "role": "instructor_beta", "expires_in_days": 7, "source": "test"},
        )
        assert res.status_code == 403

    def test_generate_and_validate_invite_as_admin(self, client: TestClient, db):
        # Create an admin user and auth header
        from app.core.enums import RoleName
        from app.models.user import User
        from app.services.permission_service import PermissionService

        admin = User(
            email="admin.beta@example.com",
            hashed_password="x",
            is_active=True,
            first_name="Admin",
            last_name="User",
            zip_code="10001",
        )
        db.add(admin)
        db.flush()
        PermissionService(db).assign_role(admin.id, RoleName.ADMIN)
        db.commit()

        token = _make_token_for_user(admin.email)
        headers = {"Authorization": f"Bearer {token}"}

        # Generate 2 invites
        res = client.post(
            "/api/v1/beta/invites/generate",
            headers=headers,
            json={"count": 2, "role": "instructor_beta", "expires_in_days": 5, "source": "seed", "emails": ["a@x.com"]},
        )
        assert res.status_code == 200
        body = res.json()
        assert "invites" in body and len(body["invites"]) == 2
        code = body["invites"][0]["code"]

        # Validate should be true
        res2 = client.get("/api/v1/beta/invites/validate", params={"code": code})
        assert res2.status_code == 200
        data2 = res2.json()
        assert data2["valid"] is True
        assert data2["code"] == code

    def test_consume_invite_and_grant_access(self, client: TestClient, db):
        # Seed an invite directly through service to get a known code
        code = _create_invite(db)

        # Create a user to consume
        from app.models.user import User

        user = User(
            email="consumer@example.com",
            hashed_password="x",
            is_active=True,
            first_name="Consumer",
            last_name="User",
            zip_code="10001",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        res = client.post(
            "/api/v1/beta/invites/consume",
            json={"code": code, "user_id": user.id, "role": "instructor_beta", "phase": "instructor_only"},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["user_id"] == user.id
        assert body["invited_by_code"] == code

    def test_validate_invite_supports_invite_code_param(self, client: TestClient, db, monkeypatch):
        monkeypatch.setenv("SITE_MODE", "local")
        code = _create_invite(db)

        res = client.get("/api/v1/beta/invites/validate", params={"invite_code": code, "email": "example@test.com"})
        assert res.status_code == 200
        data = res.json()
        assert data["valid"] is True
        assert data["code"] == code

    def test_validate_invite_sets_cookie(self, client: TestClient, db, monkeypatch):
        monkeypatch.setenv("SITE_MODE", "local")
        code = _create_invite(db)

        res = client.get("/api/v1/beta/invites/validate", params={"code": code})
        assert res.status_code == 200
        assert res.cookies.get("iv_local")
        assert res.cookies.get("iv_local").startswith(code)

    def test_validate_invite_failure_clears_cookie(self, client: TestClient, db, monkeypatch):
        monkeypatch.setenv("SITE_MODE", "local")
        code = _create_invite(db)
        client.get("/api/v1/beta/invites/validate", params={"code": code})
        assert "iv_local" in client.cookies

        res = client.get("/api/v1/beta/invites/validate", params={"code": "BADCODE"})
        header = res.headers.get("set-cookie", "")
        assert "iv_local=" in header
        assert "Max-Age=0" in header or "max-age=0" in header.lower()
        assert "iv_local" not in client.cookies

    def test_invite_verified_endpoint(self, client: TestClient, db, monkeypatch):
        monkeypatch.setenv("SITE_MODE", "local")
        code = _create_invite(db)
        client.get("/api/v1/beta/invites/validate", params={"code": code})

        res_verified = client.get("/api/v1/beta/invites/verified")
        assert res_verified.status_code == 204

        client.cookies.clear()
        res_missing = client.get("/api/v1/beta/invites/verified")
        assert res_missing.status_code == 401

    def test_invite_cookie_cleared_after_register(
        self, client: TestClient, db, monkeypatch
    ) -> None:
        monkeypatch.setenv("SITE_MODE", "local")
        code = _create_invite(db)

        res_validate = client.get("/api/v1/beta/invites/validate", params={"code": code})
        assert res_validate.status_code == 200
        assert client.cookies.get("iv_local")

        email = f"cookie-clear-{code.lower()}@example.com"
        res_register = client.post(
            "/api/v1/auth/register",
            json={
                "email": email,
                "password": "StrongPass123!",
                "first_name": "Cookie",
                "last_name": "Cleaner",
                "zip_code": "10001",
                "role": "student",
                "metadata": {"invite_code": code},
            },
        )
        assert res_register.status_code == 201
        header_value = res_register.headers.get("set-cookie", "")
        assert "iv_local=" in header_value
        lowered_header = header_value.lower()
        assert "max-age=0" in lowered_header or "expires=" in lowered_header
        assert "iv_local" not in client.cookies

        res_verified = client.get("/api/v1/beta/invites/verified")
        assert res_verified.status_code == 401
