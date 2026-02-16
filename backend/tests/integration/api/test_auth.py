# backend/tests/test_auth.py
"""
Test authentication functionality using proper test client fixture.
"""

from datetime import datetime, timedelta, timezone
import re
import time as time_module
from typing import Any

from fastapi.testclient import TestClient
import jwt
from sqlalchemy.orm import Session

from app.auth import create_access_token, get_password_hash, verify_password
from app.core.auth_cache import invalidate_cached_user_by_id_sync
from app.core.config import settings
from app.core.enums import RoleName
from app.models.password_reset import PasswordResetToken
from app.models.user import User


def _extract_session_token(response: Any) -> str:
    set_cookie = response.headers.get("set-cookie", "")
    match = re.search(rf"{re.escape(settings.session_cookie_name)}=([^;]+)", set_cookie)
    assert match, f"Expected {settings.session_cookie_name} in set-cookie header"
    return match.group(1)


class TestAuth:
    """Test authentication endpoints and functions."""

    def test_password_hashing(self):
        """Test password hashing and verification."""
        password = "TestPassword123!"
        hashed = get_password_hash(password)

        # Hash should be different from original
        assert hashed != password

        # Should verify correctly
        assert verify_password(password, hashed) is True

        # Wrong password should fail
        assert verify_password("WrongPassword", hashed) is False

    def test_create_access_token(self):
        """Test JWT token creation."""
        data = {"sub": "01ARZ3NDEKTSV4RRFFQ69G5FAV", "email": "test@example.com"}
        token = create_access_token(data)

        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0

    def test_register_new_user(self, db: Session, client: TestClient):
        """Test user registration endpoint."""
        # Now using the client fixture instead of creating TestClient
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": "newuser@example.com",
                "password": "SecurePassword123!",
                "first_name": "New",
                "last_name": "User",
                "phone": "+12125550000",
                "zip_code": "10001",
                "role": "student",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "check your email" in data["message"].lower()

        # Verify user in database
        user = db.query(User).filter(User.email == "newuser@example.com").first()
        assert user is not None
        assert any(role.name == RoleName.STUDENT for role in user.roles)

    def test_register_duplicate_user(self, db: Session, client: TestClient):
        """Test registering with existing email fails."""
        # Use a fixed email for this test (duplicate detection requires deterministic email)
        FIXED_DUP_EMAIL = "dup.user.test@example.com"

        # Create the first user explicitly with fixed email
        from app.auth import get_password_hash
        from app.core.enums import RoleName
        from app.services.permission_service import PermissionService

        existing = db.query(User).filter(User.email == FIXED_DUP_EMAIL).first()
        if not existing:
            first_user = User(
                email=FIXED_DUP_EMAIL,
                hashed_password=get_password_hash("Password123!"),
                first_name="First",
                last_name="User",
                phone="+12125550000",
                zip_code="10001",
                is_active=True,
            )
            db.add(first_user)
            db.flush()
            permission_service = PermissionService(db)
            permission_service.assign_role(first_user.id, RoleName.STUDENT)
            db.commit()
            db.refresh(first_user)

        # Attempt to register the same email via API
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": FIXED_DUP_EMAIL,
                "password": "Password123!",
                "first_name": "Duplicate",
                "last_name": "User",
                "phone": "+12125550001",
                "zip_code": "10001",
                "role": "student",
            },
        )

        # Anti-enumeration: duplicate email returns same generic 200 as new registration
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.json()}"
        data = response.json()
        assert "check your email" in data["message"].lower()
        assert "already" not in data["message"].lower()

    def test_login_success(self, db: Session, client: TestClient, test_student: User, test_password: str):
        """Test successful login."""
        response = client.post(
            "/api/v1/auth/login",
            data={"username": test_student.email, "password": test_password},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" not in data
        token = _extract_session_token(response)
        decoded = jwt.decode(
            token,
            settings.secret_key.get_secret_value(),
            algorithms=[settings.algorithm],
            options={"verify_aud": False},
        )
        assert decoded["sub"] == test_student.id
        # Ensure Set-Cookie is present with configured session cookie name
        set_cookie = response.headers.get("set-cookie", "")
        assert f"{settings.session_cookie_name}=" in set_cookie
        # Note: Test functions should not return values in pytest

    def test_cookie_authentication_fallback(
        self, db: Session, client: TestClient, test_student: User, test_password: str
    ):
        """Test that authentication works with cookie when no Authorization header is present."""
        # First login to get a token
        response = client.post(
            "/api/v1/auth/login",
            data={"username": test_student.email, "password": test_password},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert response.status_code == 200
        token = _extract_session_token(response)

        # Test with Authorization header (traditional method)
        response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == test_student.email

        # Test with cookie only (no Authorization header)
        client.cookies.set(settings.session_cookie_name, token)
        response = client.get("/api/v1/auth/me")
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == test_student.email

        # Clear cookie and verify authentication fails
        client.cookies.clear()
        response = client.get("/api/v1/auth/me")
        assert response.status_code == 401

    def test_cookie_only_auth_local(
        self, db: Session, client: TestClient, test_student: User, test_password: str, monkeypatch
    ):
        """Local mode: cookie-only auth should succeed on /auth/me."""
        # Simulate local mode
        monkeypatch.setenv("SITE_MODE", "local")
        # Login form-urlencoded to set cookie
        r = client.post(
            "/api/v1/auth/login",
            data={"username": test_student.email, "password": test_password},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert r.status_code == 200
        # Call /auth/me without Authorization header (cookie-only)
        r2 = client.get("/api/v1/auth/me")
        assert r2.status_code == 200

    def test_cookie_only_auth_allowed_in_prod(
        self, db: Session, client: TestClient, test_student: User, test_password: str, monkeypatch
    ):
        """Prod/preview should honor real session cookies on /api routes."""
        monkeypatch.setenv("SITE_MODE", "prod")
        monkeypatch.setattr(settings, "session_cookie_secure", True, raising=False)
        # Login still returns a token (and sets cookie)
        r = client.post(
            "/api/v1/auth/login",
            data={"username": test_student.email, "password": test_password},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert r.status_code == 200
        # Manually set the secure cookie since TestClient does not store HTTPS-only cookies
        cookie_token = create_access_token({"sub": test_student.id, "email": test_student.email})
        client.cookies.set(settings.session_cookie_name, cookie_token)
        # Cookie-only should succeed for API routes in hosted environments
        r2 = client.get("/api/v1/addresses/me")
        assert r2.status_code == 200
        # header path still works
        r3 = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {cookie_token}"})
        assert r3.status_code == 200

    def test_login_wrong_password(self, db: Session, client: TestClient, test_student: User):
        """Test login with wrong password."""
        response = client.post("/api/v1/auth/login", data={"username": test_student.email, "password": "WrongPassword123!"})

        assert response.status_code == 401
        assert "Incorrect email or password" in response.json()["detail"]

    def test_login_nonexistent_user(self, db: Session, client: TestClient):
        """Test login with non-existent user."""
        response = client.post("/api/v1/auth/login", data={"username": "nonexistent@example.com", "password": "Password123!"})

        assert response.status_code == 401
        assert "Incorrect email or password" in response.json()["detail"]

    def test_get_current_user(self, db: Session, client: TestClient, test_student: User, auth_headers_student: dict):
        """Test getting current user with valid token."""
        response = client.get("/api/v1/auth/me", headers=auth_headers_student)

        assert response.status_code == 200
        data = response.json()
        assert data["email"] == test_student.email
        assert data["first_name"] == test_student.first_name
        assert data["last_name"] == test_student.last_name
        assert data["roles"] == ["student"]

    def test_get_current_user_invalid_token(self, db: Session, client: TestClient):
        """Test getting current user with invalid token."""
        response = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer invalid_token"})

        assert response.status_code == 401
        assert "Could not validate credentials" in response.json()["detail"]

    def test_get_current_user_no_token(self, db: Session, client: TestClient):
        """Test getting current user without token."""
        response = client.get("/api/v1/auth/me")

        assert response.status_code == 401
        assert "Not authenticated" in response.json()["detail"]

    def test_auth_rejects_token_when_tokens_valid_after_is_after_iat(
        self, db: Session, client: TestClient, test_student: User
    ):
        token = create_access_token({"sub": test_student.id, "email": test_student.email})
        test_student.tokens_valid_after = datetime.now(timezone.utc) + timedelta(seconds=30)
        db.add(test_student)
        db.commit()
        invalidate_cached_user_by_id_sync(test_student.id, db)

        response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401
        assert response.json().get("detail") == "Token has been invalidated"

    def test_auth_allows_token_when_tokens_valid_after_is_before_iat(
        self, db: Session, client: TestClient, test_student: User
    ):
        test_student.tokens_valid_after = datetime.now(timezone.utc) - timedelta(minutes=10)
        db.add(test_student)
        db.commit()
        invalidate_cached_user_by_id_sync(test_student.id, db)

        token = create_access_token({"sub": test_student.id, "email": test_student.email})
        response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        assert response.json()["id"] == test_student.id

    def test_change_password_invalidates_old_token_and_allows_new_login(
        self, db: Session, client: TestClient, test_student: User, test_password: str
    ):
        old_token = create_access_token({"sub": test_student.id, "email": test_student.email})
        # iat is second-granularity; ensure invalidation timestamp is strictly later.
        time_module.sleep(1.1)
        change_response = client.post(
            "/api/v1/auth/change-password",
            json={"current_password": test_password, "new_password": "NewSecurePassword123"},
            headers={"Authorization": f"Bearer {old_token}"},
        )
        assert change_response.status_code == 200

        old_token_response = client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {old_token}"}
        )
        assert old_token_response.status_code == 401
        # The change-password endpoint blacklists the current token's JTI
        # (belt-and-suspenders), so the blacklist check fires before
        # tokens_valid_after — hence "revoked" rather than "invalidated".
        assert old_token_response.json().get("detail") == "Token has been revoked"

        login_response = client.post(
            "/api/v1/auth/login",
            data={"username": test_student.email, "password": "NewSecurePassword123"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert login_response.status_code == 200
        assert "access_token" not in login_response.json()

    def test_password_reset_invalidates_old_token_and_allows_new_login(
        self, db: Session, client: TestClient, test_student: User
    ):
        old_token = create_access_token({"sub": test_student.id, "email": test_student.email})
        # iat is second-granularity; ensure invalidation timestamp is strictly later.
        time_module.sleep(1.1)
        reset_token_value = f"phase3-reset-token-{test_student.id}"
        reset_token = PasswordResetToken(
            user_id=test_student.id,
            token=reset_token_value,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            used=False,
        )
        db.add(reset_token)
        db.commit()

        confirm_response = client.post(
            "/api/v1/password-reset/confirm",
            json={
                "token": reset_token_value,
                "new_password": "ResetSecurePassword123",
            },
        )
        assert confirm_response.status_code == 200

        old_token_response = client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {old_token}"}
        )
        assert old_token_response.status_code == 401
        assert old_token_response.json().get("detail") == "Token has been invalidated"

        login_response = client.post(
            "/api/v1/auth/login",
            data={"username": test_student.email, "password": "ResetSecurePassword123"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert login_response.status_code == 200
        assert "access_token" not in login_response.json()

    def test_logout_all_devices_invalidates_existing_tokens(
        self, client: TestClient, test_student: User, test_password: str
    ):
        token_a = create_access_token({"sub": test_student.id, "email": test_student.email})
        token_b = create_access_token({"sub": test_student.id, "email": test_student.email})
        # Ensure tokens predate tokens_valid_after set by logout-all.
        time_module.sleep(1.1)
        headers = {"Authorization": f"Bearer {token_a}"}

        logout_response = client.post("/api/v1/account/logout-all-devices", headers=headers)
        assert logout_response.status_code == 200
        assert logout_response.json().get("message") == "All sessions have been logged out"

        token_a_response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token_a}"})
        assert token_a_response.status_code == 401

        token_b_response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token_b}"})
        assert token_b_response.status_code == 401

        login_response = client.post(
            "/api/v1/auth/login",
            data={"username": test_student.email, "password": test_password},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert login_response.status_code == 200
        assert "access_token" not in login_response.json()

    def test_admin_force_logout_invalidates_target_but_keeps_admin_active(
        self, client: TestClient, test_student: User, admin_user: User
    ):
        target_token = create_access_token({"sub": test_student.id, "email": test_student.email})
        admin_token = create_access_token({"sub": admin_user.id, "email": admin_user.email})
        # Ensure target token predates tokens_valid_after set by force-logout.
        time_module.sleep(1.1)
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        force_response = client.post(
            f"/api/v1/admin/users/{test_student.id}/force-logout",
            headers=admin_headers,
        )
        assert force_response.status_code == 200
        assert force_response.json().get("message") == "User sessions have been logged out"

        target_me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {target_token}"})
        assert target_me.status_code == 401
        assert target_me.json().get("detail") == "Token has been invalidated"

        admin_me = client.get("/api/v1/auth/me", headers=admin_headers)
        assert admin_me.status_code == 200
        assert admin_me.json().get("id") == admin_user.id
