# backend/tests/test_auth.py
"""
Test authentication functionality using proper test client fixture.
"""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth import create_access_token, get_password_hash, verify_password
from app.core.config import settings
from app.core.enums import RoleName
from app.models.user import User


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
        data = {"sub": "test@example.com"}
        token = create_access_token(data)

        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0

    def test_register_new_user(self, db: Session, client: TestClient):
        """Test user registration endpoint."""
        # Now using the client fixture instead of creating TestClient
        response = client.post(
            "/auth/register",
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

        assert response.status_code == 201
        data = response.json()
        assert data["email"] == "newuser@example.com"
        assert data["first_name"] == "New"
        assert data["last_name"] == "User"
        assert data["roles"] == ["student"]
        assert "id" in data

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
            "/auth/register",
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

        assert response.status_code in (400, 409, 422), f"Expected 400/409/422, got {response.status_code}: {response.json()}"
        response_data = response.json()
        # Handle both dict and list response formats
        if isinstance(response_data, dict):
            detail = str(response_data.get("detail", "")).lower()
        else:
            detail = str(response_data).lower()
        assert any(keyword in detail for keyword in ["duplicate", "already", "exists", "registered"]), \
            f"Expected duplicate error message, got: {detail}"

    def test_login_success(self, db: Session, client: TestClient, test_student: User, test_password: str):
        """Test successful login."""
        response = client.post(
            "/auth/login",
            data={"username": test_student.email, "password": test_password},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
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
            "/auth/login",
            data={"username": test_student.email, "password": test_password},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert response.status_code == 200
        token = response.json()["access_token"]

        # Test with Authorization header (traditional method)
        response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == test_student.email

        # Test with cookie only (no Authorization header)
        client.cookies.set(settings.session_cookie_name, token)
        response = client.get("/auth/me")
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == test_student.email

        # Clear cookie and verify authentication fails
        client.cookies.clear()
        response = client.get("/auth/me")
        assert response.status_code == 401

    def test_cookie_only_auth_local(
        self, db: Session, client: TestClient, test_student: User, test_password: str, monkeypatch
    ):
        """Local mode: cookie-only auth should succeed on /auth/me."""
        # Simulate local mode
        monkeypatch.setenv("SITE_MODE", "local")
        # Login form-urlencoded to set cookie
        r = client.post(
            "/auth/login",
            data={"username": test_student.email, "password": test_password},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert r.status_code == 200
        # Call /auth/me without Authorization header (cookie-only)
        r2 = client.get("/auth/me")
        assert r2.status_code == 200

    def test_cookie_only_auth_denied_in_prod(
        self, db: Session, client: TestClient, test_student: User, test_password: str, monkeypatch
    ):
        """Prod/preview: cookie-only must be rejected; header required."""
        # Simulate prod mode
        monkeypatch.setenv("SITE_MODE", "prod")
        monkeypatch.setattr(settings, "session_cookie_secure", True, raising=False)
        # Login still returns a token (we won't use it here)
        r = client.post(
            "/auth/login",
            data={"username": test_student.email, "password": test_password},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert r.status_code == 200
        # Cookie-only should fail in prod for /api routes
        r2 = client.get("/api/addresses/me")
        assert r2.status_code == 401
        # With header it should succeed
        token = r.json().get("access_token")
        r3 = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert r3.status_code == 200

    def test_login_wrong_password(self, db: Session, client: TestClient, test_student: User):
        """Test login with wrong password."""
        response = client.post("/auth/login", data={"username": test_student.email, "password": "WrongPassword123!"})

        assert response.status_code == 401
        assert "Incorrect email or password" in response.json()["detail"]

    def test_login_nonexistent_user(self, db: Session, client: TestClient):
        """Test login with non-existent user."""
        response = client.post("/auth/login", data={"username": "nonexistent@example.com", "password": "Password123!"})

        assert response.status_code == 401
        assert "Incorrect email or password" in response.json()["detail"]

    def test_get_current_user(self, db: Session, client: TestClient, test_student: User, auth_headers_student: dict):
        """Test getting current user with valid token."""
        response = client.get("/auth/me", headers=auth_headers_student)

        assert response.status_code == 200
        data = response.json()
        assert data["email"] == test_student.email
        assert data["first_name"] == test_student.first_name
        assert data["last_name"] == test_student.last_name
        assert data["roles"] == ["student"]

    def test_get_current_user_invalid_token(self, db: Session, client: TestClient):
        """Test getting current user with invalid token."""
        response = client.get("/auth/me", headers={"Authorization": "Bearer invalid_token"})

        assert response.status_code == 401
        assert "Could not validate credentials" in response.json()["detail"]

    def test_get_current_user_no_token(self, db: Session, client: TestClient):
        """Test getting current user without token."""
        response = client.get("/auth/me")

        assert response.status_code == 401
        assert "Not authenticated" in response.json()["detail"]
