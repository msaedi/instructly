# backend/tests/integration/services/test_password_reset_service.py
"""
Comprehensive test suite for PasswordResetService.
Tests all security-critical paths including token generation, validation, and password updates.
Target: Increase coverage from 22% to 90%+

FIXED VERSION: Updated for EmailService dependency injection
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest

from app.core.exceptions import ValidationException
from app.models.password_reset import PasswordResetToken
from app.models.user import User
from app.services.email import EmailService
from app.services.password_reset_service import PasswordResetService
from tests.fixtures.unique_test_data import unique_data


@pytest.fixture
def mock_email_service():
    """Mock email service for password reset tests."""
    mock = Mock(spec=EmailService)
    mock.send_password_reset_email = Mock(return_value=True)
    mock.send_password_reset_confirmation = Mock(return_value=True)
    return mock


@pytest.fixture
def password_reset_service(db, mock_email_service):
    """Create PasswordResetService with dependencies."""
    return PasswordResetService(db, email_service=mock_email_service)


@pytest.fixture
def unique_test_user(db, test_password):
    """Create a unique test user for password reset tests."""
    from app.auth import get_password_hash
    from app.core.enums import RoleName
    from app.repositories.factory import RepositoryFactory
    from app.services.permission_service import PermissionService

    user_repo = RepositoryFactory.create_user_repository(db)

    user = user_repo.create(
        email=unique_data.unique_email("password.reset.test"),
        hashed_password=get_password_hash(test_password),
        first_name="Test",
        last_name="User",
        phone="+12125551234",
        zip_code="10001",
        timezone="America/New_York",
        is_active=True,
    )

    # Assign student role
    permission_service = PermissionService(db)
    permission_service.assign_role(user.id, RoleName.STUDENT)
    db.refresh(user)

    return user


class TestPasswordResetService:
    """Test password reset service functionality with real database."""

    def test_request_password_reset_valid_user(self, password_reset_service, unique_test_user, mock_email_service):
        """Test password reset request for valid user."""
        # Execute
        result = password_reset_service.request_password_reset(unique_test_user.email)

        # Verify
        assert result is True
        mock_email_service.send_password_reset_email.assert_called_once()

        # Verify email parameters
        email_call = mock_email_service.send_password_reset_email.call_args
        assert email_call.kwargs["to_email"] == unique_test_user.email
        assert email_call.kwargs["user_name"] == unique_test_user.first_name
        assert "reset_url" in email_call.kwargs

    def test_request_password_reset_nonexistent_user(self, password_reset_service, mock_email_service):
        """Test password reset for non-existent user - should still return True."""
        # Execute
        result = password_reset_service.request_password_reset("nonexistent@example.com")

        # Verify - returns True to prevent email enumeration
        assert result is True
        mock_email_service.send_password_reset_email.assert_not_called()

    def test_request_password_reset_invalidates_existing_tokens(
        self, password_reset_service, unique_test_user, db, mock_email_service
    ):
        """Test that existing tokens are invalidated when requesting new reset."""
        # Create existing tokens
        for i in range(3):
            token = PasswordResetToken(
                user_id=unique_test_user.id,
                token=f"old_token_{i}",
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
                used=False,
            )
            db.add(token)
        db.commit()

        # Execute
        password_reset_service.request_password_reset(unique_test_user.email)

        # Verify existing tokens were invalidated
        old_tokens = (
            db.query(PasswordResetToken)
            .filter(PasswordResetToken.user_id == unique_test_user.id, PasswordResetToken.token.like("old_token_%"))
            .all()
        )

        assert all(token.used for token in old_tokens)

    def test_request_password_reset_email_error_handled(
        self, password_reset_service, unique_test_user, mock_email_service
    ):
        """Test that email sending errors are handled gracefully."""
        # Email service throws error
        mock_email_service.send_password_reset_email.side_effect = Exception("Email service down")

        # Execute
        result = password_reset_service.request_password_reset(unique_test_user.email)

        # Verify - still returns True
        assert result is True

    def test_verify_reset_token_valid(self, password_reset_service, unique_test_user, db):
        """Test verification of valid reset token."""
        # Create valid token
        future_time = datetime.now(timezone.utc) + timedelta(hours=1)
        reset_token = PasswordResetToken(
            user_id=unique_test_user.id, token="valid_token_123", expires_at=future_time, used=False
        )
        db.add(reset_token)
        db.commit()

        # Execute
        is_valid, masked_email = password_reset_service.verify_reset_token("valid_token_123")

        # Verify
        assert is_valid is True
        # The unique_test_user email starts with 'password.reset.test' which gets masked to 'pa***'
        assert masked_email.startswith("pa***") and masked_email.endswith("@example.com")

    def test_verify_reset_token_nonexistent(self, password_reset_service):
        """Test verification of non-existent token."""
        # Execute
        is_valid, masked_email = password_reset_service.verify_reset_token("nonexistent_token")

        # Verify
        assert is_valid is False
        assert masked_email is None

    def test_verify_reset_token_already_used(self, password_reset_service, unique_test_user, db):
        """Test verification of already used token."""
        # Create used token
        reset_token = PasswordResetToken(
            user_id=unique_test_user.id,
            token="used_token",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            used=True,
        )
        db.add(reset_token)
        db.commit()

        # Execute
        is_valid, masked_email = password_reset_service.verify_reset_token("used_token")

        # Verify
        assert is_valid is False
        assert masked_email is None

    def test_verify_reset_token_expired(self, password_reset_service, unique_test_user, db):
        """Test verification of expired token."""
        # Create expired token
        past_time = datetime.now(timezone.utc) - timedelta(hours=1)
        reset_token = PasswordResetToken(
            user_id=unique_test_user.id, token="expired_token", expires_at=past_time, used=False
        )
        db.add(reset_token)
        db.commit()

        # Execute
        is_valid, masked_email = password_reset_service.verify_reset_token("expired_token")

        # Verify
        assert is_valid is False
        assert masked_email is None

    def test_email_masking_logic(self, password_reset_service, db):
        """Test email masking for different email formats."""
        # Test cases
        test_cases = [
            ("test@example.com", "te***@example.com"),
            ("a@example.com", "***@example.com"),  # Short email
            ("ab@example.com", "***@example.com"),  # 2 char email
            ("longusername@example.com", "lo***@example.com"),
        ]

        for email, expected_masked in test_cases:
            # Create user with specific email
            user = User(
                email=email,
                hashed_password="dummy",
                first_name="Test",
                last_name="User",
                phone="+12125550000",
                zip_code="10001",
            )
            db.add(user)
            db.flush()

            # Create token
            reset_token = PasswordResetToken(
                user_id=user.id,
                token=f"token_{email}",
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
                used=False,
            )
            db.add(reset_token)
            db.flush()

            # Execute
            is_valid, masked_email = password_reset_service.verify_reset_token(f"token_{email}")

            # Verify
            assert masked_email == expected_masked

            # Cleanup
            db.rollback()

    def test_confirm_password_reset_success(self, password_reset_service, unique_test_user, db, mock_email_service):
        """Test successful password reset confirmation."""
        # Create valid token
        future_time = datetime.now(timezone.utc) + timedelta(hours=1)
        reset_token = PasswordResetToken(
            user_id=unique_test_user.id, token="valid_token_123", expires_at=future_time, used=False
        )
        db.add(reset_token)
        db.commit()

        # Execute
        new_password = "NewSecurePassword123!"
        result = password_reset_service.confirm_password_reset("valid_token_123", new_password)

        # Verify
        assert result is True

        # Check token is marked as used
        db.refresh(reset_token)
        assert reset_token.used is True

        # Check email was sent
        mock_email_service.send_password_reset_confirmation.assert_called_once()

    def test_confirm_password_reset_invalid_token(self, password_reset_service):
        """Test password reset with invalid token."""
        # Execute & Verify
        with pytest.raises(ValidationException) as exc_info:
            password_reset_service.confirm_password_reset("invalid_token", "NewPassword123!")

        assert "Invalid or expired reset token" in str(exc_info.value)

    def test_confirm_password_reset_used_token(self, password_reset_service, unique_test_user, db):
        """Test password reset with already used token."""
        # Create used token
        reset_token = PasswordResetToken(
            user_id=unique_test_user.id,
            token="used_token",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            used=True,
        )
        db.add(reset_token)
        db.commit()

        # Execute & Verify
        with pytest.raises(ValidationException) as exc_info:
            password_reset_service.confirm_password_reset("used_token", "NewPassword123!")

        assert "already been used" in str(exc_info.value)

    def test_confirm_password_reset_expired_token(self, password_reset_service, unique_test_user, db):
        """Test password reset with expired token."""
        # Create expired token
        past_time = datetime.now(timezone.utc) - timedelta(hours=1)
        reset_token = PasswordResetToken(
            user_id=unique_test_user.id, token="expired_token", expires_at=past_time, used=False
        )
        db.add(reset_token)
        db.commit()

        # Execute & Verify
        with pytest.raises(ValidationException) as exc_info:
            password_reset_service.confirm_password_reset("expired_token", "NewPassword123!")

        assert "expired" in str(exc_info.value)

    def test_generate_reset_token(self, password_reset_service, unique_test_user, db):
        """Test reset token generation."""
        # Execute
        token = password_reset_service._generate_reset_token(unique_test_user.id)

        # Verify
        assert token is not None
        assert len(token) >= 32

        # Check token was saved to database
        saved_token = db.query(PasswordResetToken).filter_by(user_id=unique_test_user.id, token=token).first()

        assert saved_token is not None
        assert saved_token.used is False
        assert saved_token.expires_at > datetime.now(timezone.utc)

    def test_invalidate_existing_tokens(self, password_reset_service, unique_test_user, db):
        """Test invalidation of existing tokens."""
        # Create multiple tokens
        tokens = []
        for i in range(5):
            token = PasswordResetToken(
                user_id=unique_test_user.id,
                token=f"token_{i}",
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
                used=False,
            )
            db.add(token)
            tokens.append(token)
        db.commit()

        # Execute
        password_reset_service._invalidate_existing_tokens(unique_test_user.id)
        db.commit()

        # Verify all tokens are marked as used
        for token in tokens:
            db.refresh(token)
            assert token.used is True


class TestPasswordResetSecurityScenarios:
    """Test security-specific scenarios for password reset."""

    def test_concurrent_reset_requests(self, password_reset_service, unique_test_user, db, mock_email_service):
        """Test handling of concurrent password reset requests."""
        # Create multiple existing tokens (simulating concurrent requests)
        for i in range(5):
            token = PasswordResetToken(
                user_id=unique_test_user.id,
                token=f"concurrent_token_{i}",
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
                used=False,
            )
            db.add(token)
        db.commit()

        # Execute new request
        password_reset_service.request_password_reset(unique_test_user.email)

        # Verify all previous tokens are invalidated
        old_tokens = (
            db.query(PasswordResetToken)
            .filter(
                PasswordResetToken.user_id == unique_test_user.id, PasswordResetToken.token.like("concurrent_token_%")
            )
            .all()
        )

        assert all(token.used for token in old_tokens)

    @pytest.mark.asyncio
    async def test_token_reuse_prevention(self, password_reset_service, unique_test_user, db):
        """Test that used tokens cannot be reused."""
        # Create and use a token
        used_token = PasswordResetToken(
            user_id=unique_test_user.id,
            token="reuse_test_token",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            used=True,
        )
        db.add(used_token)
        db.commit()

        # First verify returns false
        is_valid, _ = password_reset_service.verify_reset_token("reuse_test_token")
        assert is_valid is False

        # Confirm also raises exception
        with pytest.raises(ValidationException) as exc_info:
            password_reset_service.confirm_password_reset("reuse_test_token", "NewPassword123!")
        assert "already been used" in str(exc_info.value)

    def test_timing_attack_prevention(self, password_reset_service, unique_test_user, mock_email_service):
        """Test that response time is consistent for existing and non-existing users."""
        import time

        # Test with existing user
        start = time.time()
        result1 = password_reset_service.request_password_reset(unique_test_user.email)
        time1 = time.time() - start

        # Test with non-existing user
        start = time.time()
        result2 = password_reset_service.request_password_reset("notexists@example.com")
        time2 = time.time() - start

        # Both should return True
        assert result1 is True
        assert result2 is True

        # Response times should be similar (within 100ms)
        # Note: This is a basic check - in production you'd want more sophisticated timing attack prevention
        assert abs(time1 - time2) < 0.1

    def test_token_entropy(self, password_reset_service, unique_test_user, db):
        """Test that tokens have sufficient entropy."""
        # Generate multiple tokens
        tokens = set()
        for _ in range(10):
            token = password_reset_service._generate_reset_token(unique_test_user.id)
            tokens.add(token)

            # Each token should be unique
            assert len(token) >= 43  # Base64 encoding of 32 bytes

        # All tokens should be unique
        assert len(tokens) == 10
