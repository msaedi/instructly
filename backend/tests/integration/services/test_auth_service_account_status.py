# backend/tests/integration/services/test_auth_service_account_status.py
"""
Integration tests for AuthService with account status constraints.

Tests authentication behavior for different account statuses:
- Active users can login
- Suspended users can login
- Deactivated users cannot login
"""

import pytest
from sqlalchemy.orm import Session

from app.auth import get_password_hash
from app.models.user import User
from app.services.auth_service import AuthService


class TestAuthServiceAccountStatus:
    """Test authentication service respects account status."""

    @pytest.fixture
    def auth_service(self, db: Session):
        """Create AuthService instance."""
        return AuthService(db)

    @pytest.fixture
    def test_password(self):
        """Standard test password."""
        return "testpassword123"

    @pytest.fixture
    def active_instructor(self, db: Session, test_password):
        """Create an active instructor."""
        user = User(
            email="active.instructor@example.com",
            hashed_password=get_password_hash(test_password),
            first_name="Active",
            last_name="Instructor",
            phone="+12125550000",
            zip_code="10001",
            account_status="active",
            is_active=True,
        )
        db.add(user)
        db.commit()
        return user

    @pytest.fixture
    def suspended_instructor(self, db: Session, test_password):
        """Create a suspended instructor."""
        user = User(
            email="suspended.instructor@example.com",
            hashed_password=get_password_hash(test_password),
            first_name="Suspended",
            last_name="Instructor",
            phone="+12125550000",
            zip_code="10001",
            account_status="suspended",
            is_active=True,
        )
        db.add(user)
        db.commit()
        return user

    @pytest.fixture
    def deactivated_instructor(self, db: Session, test_password):
        """Create a deactivated instructor."""
        user = User(
            email="deactivated.instructor@example.com",
            hashed_password=get_password_hash(test_password),
            first_name="Deactivated",
            last_name="Instructor",
            phone="+12125550000",
            zip_code="10001",
            account_status="deactivated",
            is_active=True,
        )
        db.add(user)
        db.commit()
        return user

    @pytest.fixture
    def active_student(self, db: Session, test_password):
        """Create an active student."""
        user = User(
            email="active.student@example.com",
            hashed_password=get_password_hash(test_password),
            first_name="Active",
            last_name="Student",
            phone="+12125550000",
            zip_code="10001",
            account_status="active",
            is_active=True,
        )
        db.add(user)
        db.commit()
        return user

    def test_authenticate_active_instructor(
        self, auth_service: AuthService, active_instructor: User, test_password: str
    ):
        """Test that active instructors can authenticate."""
        authenticated_user = auth_service.authenticate_user(active_instructor.email, test_password)

        assert authenticated_user is not None
        assert authenticated_user.id == active_instructor.id
        assert authenticated_user.account_status == "active"

    def test_authenticate_suspended_instructor(
        self, auth_service: AuthService, suspended_instructor: User, test_password: str
    ):
        """Test that suspended instructors can still authenticate."""
        authenticated_user = auth_service.authenticate_user(suspended_instructor.email, test_password)

        assert authenticated_user is not None
        assert authenticated_user.id == suspended_instructor.id
        assert authenticated_user.account_status == "suspended"

    def test_authenticate_deactivated_instructor(
        self, auth_service: AuthService, deactivated_instructor: User, test_password: str
    ):
        """Test that deactivated instructors cannot authenticate."""
        authenticated_user = auth_service.authenticate_user(deactivated_instructor.email, test_password)

        assert authenticated_user is None

    def test_authenticate_active_student(self, auth_service: AuthService, active_student: User, test_password: str):
        """Test that active students can authenticate."""
        authenticated_user = auth_service.authenticate_user(active_student.email, test_password)

        assert authenticated_user is not None
        assert authenticated_user.id == active_student.id
        assert authenticated_user.account_status == "active"

    def test_authenticate_with_wrong_password(self, auth_service: AuthService, active_instructor: User):
        """Test authentication fails with wrong password."""
        authenticated_user = auth_service.authenticate_user(active_instructor.email, "wrongpassword")

        assert authenticated_user is None

    def test_authenticate_nonexistent_user(self, auth_service: AuthService):
        """Test authentication fails for nonexistent user."""
        authenticated_user = auth_service.authenticate_user("nonexistent@example.com", "anypassword")

        assert authenticated_user is None

    def test_get_current_user_active(self, auth_service: AuthService, active_instructor: User):
        """Test getting current user works for active users."""
        current_user = auth_service.get_current_user(active_instructor.email)

        assert current_user is not None
        assert current_user.id == active_instructor.id
        assert current_user.account_status == "active"

    def test_get_current_user_suspended(self, auth_service: AuthService, suspended_instructor: User):
        """Test getting current user works for suspended users."""
        current_user = auth_service.get_current_user(suspended_instructor.email)

        assert current_user is not None
        assert current_user.id == suspended_instructor.id
        assert current_user.account_status == "suspended"

    def test_get_current_user_deactivated(self, auth_service: AuthService, deactivated_instructor: User):
        """Test getting current user works even for deactivated users."""
        # Note: get_current_user is used after JWT validation,
        # so it should still return the user even if deactivated
        current_user = auth_service.get_current_user(deactivated_instructor.email)

        assert current_user is not None
        assert current_user.id == deactivated_instructor.id
        assert current_user.account_status == "deactivated"

    def test_register_user_with_default_status(self, auth_service: AuthService, db: Session):
        """Test that new users are registered with active status by default."""
        new_user = auth_service.register_user(
            email="newuser@example.com", password="password123", first_name="New", last_name="User", zip_code="10001"
        )

        assert new_user is not None
        assert new_user.account_status == "active"

        # Verify in database
        db_user = db.query(User).filter(User.email == "newuser@example.com").first()
        assert db_user is not None
        assert db_user.account_status == "active"

    def test_api_login_endpoint_with_deactivated_user(self, client, deactivated_instructor: User, test_password: str):
        """Test that login endpoint rejects deactivated users with specific message."""
        response = client.post(
            "/api/v1/auth/login", data={"username": deactivated_instructor.email, "password": test_password}
        )

        # Should return 401 Unauthorized with specific deactivation message
        # This provides better UX than generic "Incorrect email or password"
        assert response.status_code == 401
        detail = response.json()["detail"]
        # Accept either the specific message or dict format
        if isinstance(detail, dict):
            assert detail.get("message") == "Account has been deactivated"
        else:
            assert "deactivated" in detail.lower()

    def test_api_login_endpoint_with_suspended_user(self, client, suspended_instructor: User, test_password: str):
        """Test that login endpoint accepts suspended users."""
        response = client.post("/api/v1/auth/login", data={"username": suspended_instructor.email, "password": test_password})

        # Should succeed
        assert response.status_code == 200
        assert "access_token" in response.json()
        assert response.json()["token_type"] == "bearer"

    def test_api_protected_endpoint_with_suspended_user_token(
        self, client, suspended_instructor: User, test_password: str
    ):
        """Test that suspended users can access protected endpoints after login."""
        # First login to get token
        login_response = client.post(
            "/api/v1/auth/login", data={"username": suspended_instructor.email, "password": test_password}
        )
        token = login_response.json()["access_token"]

        # Try to access a protected endpoint
        headers = {"Authorization": f"Bearer {token}"}
        response = client.get("/api/v1/auth/me", headers=headers)

        assert response.status_code == 200
        user_data = response.json()
        assert user_data["email"] == suspended_instructor.email
        # Suspended users can still access endpoints and get their info
