import logging

# backend/tests/routes/test_password_reset_routes.py
"""
Comprehensive test suite for password reset routes.
Tests all endpoints and error scenarios.
FIXED: Using proper dependency injection pattern with EmailService
"""

from unittest.mock import Mock, patch

from fastapi import HTTPException, status
import pytest

from app.api.dependencies.services import get_password_reset_service
from app.core.exceptions import NotFoundException, ServiceException, ValidationException
from app.main import fastapi_app as app
from app.models.password_reset import PasswordResetToken
from app.services.email import EmailService
from app.services.password_reset_service import PasswordResetService


class TestPasswordResetRoutes:
    """Test password reset API endpoints."""

    @pytest.fixture
    def mock_email_service(self):
        """Create mock email service."""
        mock = Mock(spec=EmailService)
        mock.send_password_reset_email = Mock(return_value=True)
        mock.send_password_reset_confirmation = Mock(return_value=True)
        return mock

    @pytest.fixture
    def mock_password_reset_service(self, db, mock_email_service):
        """Create a properly initialized mock password reset service."""
        # Create real service with mocked email service
        service = PasswordResetService(db, email_service=mock_email_service)

        # Mock the public methods (now synchronous)
        service.request_password_reset = Mock(return_value=True)
        service.confirm_password_reset = Mock(return_value=True)
        service.verify_reset_token = Mock(return_value=(True, "te***@example.com"))

        return service

    @pytest.fixture
    def client_with_mock_service(self, client, mock_password_reset_service):
        """Create test client with mocked password reset service."""
        # Override the dependency
        app.dependency_overrides[get_password_reset_service] = lambda: mock_password_reset_service

        yield client

        # Clean up
        app.dependency_overrides.clear()

    def test_request_password_reset_success(self, client_with_mock_service, mock_password_reset_service):
        """Test successful password reset request."""
        # Execute
        response = client_with_mock_service.post("/api/v1/password-reset/request", json={"email": "test@example.com"})

        # Verify
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["message"] == "Check your email for the reset link."
        mock_password_reset_service.request_password_reset.assert_called_once_with(email="test@example.com")

    def test_request_password_reset_unknown_email(self, client_with_mock_service, mock_password_reset_service):
        """Test password reset request with an email that has no account."""
        mock_password_reset_service.request_password_reset = Mock(
            side_effect=NotFoundException(
                "Password reset account not found",
                code="PASSWORD_RESET_ACCOUNT_NOT_FOUND",
            )
        )

        response = client_with_mock_service.post(
            "/api/v1/password-reset/request",
            json={"email": "missing@example.com"},
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.json()["detail"] == (
            "We couldn't find an account with that email. Please double-check and try again."
        )

    def test_request_password_reset_email_delivery_failure(
        self, client_with_mock_service, mock_password_reset_service
    ):
        """Test password reset request when reset email delivery fails."""
        mock_password_reset_service.request_password_reset = Mock(
            side_effect=ServiceException(
                "Couldn't send reset email. Please try again or contact support.",
                code="PASSWORD_RESET_EMAIL_FAILED",
            )
        )

        response = client_with_mock_service.post(
            "/api/v1/password-reset/request",
            json={"email": "test@example.com"},
        )

        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert response.json()["detail"] == (
            "Couldn't send reset email. Please try again or contact support."
        )

    def test_request_password_reset_unknown_service_exception_maps_to_500(
        self, client_with_mock_service, mock_password_reset_service, caplog
    ):
        """If a future ServiceException code is added without explicit handling,
        the route returns 500 with the route-local message rather than swallowing
        into the global handler.
        """
        mock_password_reset_service.request_password_reset = Mock(
            side_effect=ServiceException(
                "Future password reset service failure",
                code="PASSWORD_RESET_FUTURE_FAILURE",
            )
        )

        with caplog.at_level(logging.ERROR):
            response = client_with_mock_service.post(
                "/api/v1/password-reset/request",
                json={"email": "test@example.com"},
            )

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert response.json()["detail"] == "An error occurred while requesting your password reset."
        assert any(
            record.getMessage() == "Unhandled ServiceException code in password reset request"
            and getattr(record, "code", None) == "PASSWORD_RESET_FUTURE_FAILURE"
            for record in caplog.records
        )

    def test_request_password_reset_unhandled_exception_maps_to_500(
        self, client_with_mock_service, mock_password_reset_service
    ):
        """Unexpected raw exception is mapped to 500 with the route-local
        detail message and is logged via logger.exception.
        """
        mock_password_reset_service.request_password_reset = Mock(
            side_effect=RuntimeError("database unavailable")
        )

        with patch("app.routes.v1.password_reset.logger.exception") as mock_logger_exception:
            response = client_with_mock_service.post(
                "/api/v1/password-reset/request",
                json={"email": "test@example.com"},
            )

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert response.json()["detail"] == "An error occurred while requesting your password reset."
        mock_logger_exception.assert_called_once()

    def test_request_password_reset_preserves_http_exceptions(
        self, client_with_mock_service, mock_password_reset_service
    ):
        """HTTP exceptions from dependencies should not be recast as 500s."""
        mock_password_reset_service.request_password_reset = Mock(
            side_effect=HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many password reset attempts. Please try again later.",
            )
        )

        response = client_with_mock_service.post(
            "/api/v1/password-reset/request",
            json={"email": "test@example.com"},
        )

        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert response.json()["detail"] == "Too many password reset attempts. Please try again later."

    def test_request_password_reset_invalid_email(self, client):
        """Test password reset request with invalid email format."""
        # Execute
        response = client.post("/api/v1/password-reset/request", json={"email": "invalid-email"})

        # Verify
        assert response.status_code == 422
        error = response.json()
        assert any("email" in str(err).lower() for err in error["detail"])

    def test_request_password_reset_missing_email(self, client):
        """Test password reset request without email."""
        # Execute
        response = client.post("/api/v1/password-reset/request", json={})

        # Verify
        assert response.status_code == 422

    def test_confirm_password_reset_success(self, client_with_mock_service, mock_password_reset_service):
        """Test successful password reset confirmation."""
        # Execute
        response = client_with_mock_service.post(
            "/api/v1/password-reset/confirm",
            json={"token": "valid_token_123", "new_password": "NewSecurePassword123!"},
        )

        # Verify
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "successfully reset" in data["message"]
        mock_password_reset_service.confirm_password_reset.assert_called_once_with(
            token="valid_token_123", new_password="NewSecurePassword123!"
        )

    def test_confirm_password_reset_invalid_token(self, client_with_mock_service, mock_password_reset_service):
        """Test password reset with invalid token."""
        # Set up the mock to raise ValidationException
        mock_password_reset_service.confirm_password_reset = Mock(
            side_effect=ValidationException("Invalid or expired reset token")
        )

        # Execute
        response = client_with_mock_service.post(
            "/api/v1/password-reset/confirm", json={"token": "invalid_token", "new_password": "NewSecurePassword123!"}
        )

        # Verify
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        data = response.json()
        assert "Invalid or expired reset token" in data["detail"]

    def test_confirm_password_reset_weak_password(self, client):
        """Test password reset with weak password."""
        # Execute - password too short
        response = client.post(
            "/api/v1/password-reset/confirm", json={"token": "valid_token", "new_password": "weak"}
        )

        # Verify
        assert response.status_code == 422
        error = response.json()
        assert any("at least 8 characters" in str(err).lower() for err in error["detail"])

        # Execute - password without digit
        response = client.post(
            "/api/v1/password-reset/confirm", json={"token": "valid_token", "new_password": "NoDigitsHere"}
        )

        # Verify
        assert response.status_code == 422

        # Execute - password without uppercase
        response = client.post(
            "/api/v1/password-reset/confirm", json={"token": "valid_token", "new_password": "nouppercase123"}
        )

        # Verify
        assert response.status_code == 422

    def test_confirm_password_reset_server_error(self, client_with_mock_service, mock_password_reset_service):
        """Test password reset with unexpected server error."""
        # Set up mock to raise generic exception
        mock_password_reset_service.confirm_password_reset = Mock(side_effect=Exception("Database connection failed"))

        # Execute
        response = client_with_mock_service.post(
            "/api/v1/password-reset/confirm", json={"token": "valid_token", "new_password": "NewSecurePassword123!"}
        )

        # Verify
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        data = response.json()
        assert "An error occurred" in data["detail"]

    def test_verify_reset_token_valid(self, client_with_mock_service, mock_password_reset_service):
        """Test verification of valid reset token."""
        # Execute
        response = client_with_mock_service.get("/api/v1/password-reset/verify/valid_token_123")

        # Verify
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["valid"] is True
        assert data["email"] == "te***@example.com"
        mock_password_reset_service.verify_reset_token.assert_called_once_with(token="valid_token_123")

    def test_verify_reset_token_invalid(self, client_with_mock_service, mock_password_reset_service):
        """Test verification of invalid reset token."""
        # Set up mock to return invalid result
        mock_password_reset_service.verify_reset_token = Mock(return_value=(False, None))

        # Execute
        response = client_with_mock_service.get("/api/v1/password-reset/verify/invalid_token")

        # Verify
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["valid"] is False
        assert "email" not in data

    def test_verify_reset_token_special_characters(self, client_with_mock_service, mock_password_reset_service):
        """Test token verification with special characters."""
        # Setup
        token_with_special = "token_with-special.chars~123"

        # Execute
        response = client_with_mock_service.get(f"/api/v1/password-reset/verify/{token_with_special}")

        # Verify
        assert response.status_code == status.HTTP_200_OK
        mock_password_reset_service.verify_reset_token.assert_called_once_with(token=token_with_special)

    def test_request_password_reset_handles_repeated_requests(
        self, client_with_mock_service, mock_password_reset_service
    ):
        """Multiple sequential requests for the same email succeed at the
        route layer when the service accepts each. Rate limiting itself
        is enforced at the dependency layer and tested separately via
        test_request_password_reset_preserves_http_exceptions.
        """
        email = "test@example.com"

        # Execute multiple requests
        for _ in range(5):
            response = client_with_mock_service.post("/api/v1/password-reset/request", json={"email": email})
            assert response.status_code == status.HTTP_200_OK

        # All requests should succeed
        assert mock_password_reset_service.request_password_reset.call_count == 5

    def test_confirm_password_reset_missing_fields(self, client):
        """Test confirmation with missing required fields."""
        # Missing token
        response = client.post("/api/v1/password-reset/confirm", json={"new_password": "NewSecurePassword123!"})
        assert response.status_code == 422

        # Missing password
        response = client.post("/api/v1/password-reset/confirm", json={"token": "valid_token"})
        assert response.status_code == 422

        # Empty payload
        response = client.post("/api/v1/password-reset/confirm", json={})
        assert response.status_code == 422

    def test_password_validation_edge_cases(self, client_with_mock_service, mock_password_reset_service):
        """Test edge cases in password validation."""
        # Test valid password (should pass validation and call service)
        response = client_with_mock_service.post(
            "/api/v1/password-reset/confirm", json={"token": "valid_token", "new_password": "Valid1234"}
        )
        # Should succeed with mocked service
        assert response.status_code == status.HTTP_200_OK


class TestPasswordResetIntegration:
    """Integration tests for password reset flow."""

    @pytest.fixture
    def mock_email_service(self):
        """Create mock email service for integration tests."""
        mock = Mock(spec=EmailService)
        mock.send_password_reset_email = Mock(return_value=True)
        mock.send_password_reset_confirmation = Mock(return_value=True)
        return mock

    def test_request_password_reset_email_false_return_captures_sentry(
        self, client, db, test_student, mock_email_service
    ):
        """A valid account with reset email failure should return 503 and be observable."""
        mock_email_service.send_password_reset_email.return_value = False

        def override_get_password_reset_service():
            return PasswordResetService(db, email_service=mock_email_service)

        app.dependency_overrides[get_password_reset_service] = override_get_password_reset_service

        try:
            with patch(
                "app.services.password_reset_service.capture_sentry_exception"
            ) as mock_capture:
                response = client.post(
                    "/api/v1/password-reset/request",
                    json={"email": test_student.email},
                )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert response.json()["detail"] == (
            "Couldn't send reset email. Please try again or contact support."
        )
        mock_capture.assert_called_once()
        capture_args, capture_kwargs = mock_capture.call_args
        assert capture_args[0] == "password_reset_email_failed"
        assert isinstance(capture_args[1], RuntimeError)
        assert capture_kwargs == {"user_id": test_student.id}

    @pytest.mark.asyncio
    async def test_complete_password_reset_flow(self, client, db, test_student, mock_email_service):
        """Test complete password reset flow from request to confirmation."""

        # Override the password reset service to use mocked email
        def override_get_password_reset_service():
            return PasswordResetService(db, email_service=mock_email_service)

        app.dependency_overrides[get_password_reset_service] = override_get_password_reset_service

        try:
            # Step 1: Request password reset
            response = client.post("/api/v1/password-reset/request", json={"email": test_student.email})
            assert response.status_code == status.HTTP_200_OK

            # Step 2: Get the token from database
            token_record = (
                db.query(PasswordResetToken)
                .filter_by(user_id=test_student.id)
                .order_by(PasswordResetToken.created_at.desc())
                .first()
            )

            assert token_record is not None
            assert token_record.used is False

            # Step 3: Verify the token
            response = client.get(f"/api/v1/password-reset/verify/{token_record.token}")
            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["valid"] is True

            # Step 4: Reset password with the token
            new_password = "MyNewSecurePassword123!"
            response = client.post(
                "/api/v1/password-reset/confirm", json={"token": token_record.token, "new_password": new_password}
            )
            assert response.status_code == status.HTTP_200_OK

            # Verify token is now marked as used - requery from db
            updated_token = db.query(PasswordResetToken).filter_by(token=token_record.token).first()
            assert updated_token.used is True

            # Step 5: Try to login with new password
            response = client.post("/api/v1/auth/login", data={"username": test_student.email, "password": new_password})
            assert response.status_code == status.HTTP_200_OK
            assert "access_token" not in response.json()

            # Step 6: Verify old token cannot be reused
            response = client.post(
                "/api/v1/password-reset/confirm",
                json={"token": token_record.token, "new_password": "AnotherPassword123!"},
            )
            assert response.status_code == status.HTTP_400_BAD_REQUEST
            # Accept either error message - different services might return different messages
            error_detail = response.json()["detail"]
            assert "Invalid or expired reset token" in error_detail or "already been used" in error_detail

        finally:
            # Clean up the override
            app.dependency_overrides.clear()
