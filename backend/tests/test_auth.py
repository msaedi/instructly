# backend/tests/test_auth.py
"""
Test authentication functionality using proper test client.
"""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth import create_access_token, get_password_hash, verify_password
from app.main import app
from app.models.user import User, UserRole


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

    def test_register_new_user(self, db: Session):
        """Test user registration endpoint."""
        client = TestClient(app)

        response = client.post(
            "/auth/register",
            json={
                "email": "newuser@example.com",
                "password": "SecurePassword123!",
                "full_name": "New User",
                "role": "student",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["email"] == "newuser@example.com"
        assert data["full_name"] == "New User"
        assert data["role"] == "student"
        assert "id" in data

        # Verify user in database
        user = db.query(User).filter(User.email == "newuser@example.com").first()
        assert user is not None
        assert user.role == UserRole.STUDENT

    def test_register_duplicate_user(self, db: Session, test_student: User):
        """Test registering with existing email fails."""
        client = TestClient(app)

        response = client.post(
            "/auth/register",
            json={
                "email": test_student.email,  # Existing email
                "password": "Password123!",
                "full_name": "Duplicate User",
                "role": "student",
            },
        )

        assert response.status_code == 400
        assert "already registered" in response.json()["detail"]

    def test_login_success(self, db: Session, test_student: User, test_password: str):
        """Test successful login."""
        client = TestClient(app)

        response = client.post("/auth/login", data={"username": test_student.email, "password": test_password})

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    def test_login_wrong_password(self, db: Session, test_student: User):
        """Test login with wrong password."""
        client = TestClient(app)

        response = client.post("/auth/login", data={"username": test_student.email, "password": "WrongPassword123!"})

        assert response.status_code == 401
        assert "Incorrect email or password" in response.json()["detail"]

    def test_login_nonexistent_user(self, db: Session):
        """Test login with non-existent user."""
        client = TestClient(app)

        response = client.post("/auth/login", data={"username": "nonexistent@example.com", "password": "Password123!"})

        assert response.status_code == 401
        assert "Incorrect email or password" in response.json()["detail"]

    def test_get_current_user(self, db: Session, test_student: User, auth_headers_student: dict):
        """Test getting current user with valid token."""
        client = TestClient(app)

        response = client.get("/auth/me", headers=auth_headers_student)

        assert response.status_code == 200
        data = response.json()
        assert data["email"] == test_student.email
        assert data["full_name"] == test_student.full_name
        assert data["role"] == "student"

    def test_get_current_user_invalid_token(self, db: Session):
        """Test getting current user with invalid token."""
        client = TestClient(app)

        response = client.get("/auth/me", headers={"Authorization": "Bearer invalid_token"})

        assert response.status_code == 401
        assert "Could not validate credentials" in response.json()["detail"]

    def test_get_current_user_no_token(self, db: Session):
        """Test getting current user without token."""
        client = TestClient(app)

        response = client.get("/auth/me")

        assert response.status_code == 401
        assert "Not authenticated" in response.json()["detail"]
