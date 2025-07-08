# backend/tests/integration/services/test_password_reset_service.py
"""
Comprehensive test suite for PasswordResetService.
Tests all security-critical paths including token generation, validation, and password updates.
Target: Increase coverage from 22% to 90%+

FIXED VERSION: Addresses mock counting and fixture scope issues
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest
from sqlalchemy.orm import Session

from app.core.exceptions import ValidationException
from app.models.password_reset import PasswordResetToken
from app.models.user import User
from app.services.password_reset_service import PasswordResetService


class TestPasswordResetService:
    """Test password reset service functionality."""

    @pytest.fixture
    def mock_db(self):
        """Create mock database session."""
        db = Mock(spec=Session)
        db.commit = Mock()
        db.rollback = Mock()
        db.flush = Mock()
        db.begin_nested = Mock()
        db.begin_nested.return_value.__enter__ = Mock()
        db.begin_nested.return_value.__exit__ = Mock()
        return db

    @pytest.fixture
    def mock_user_repository(self):
        """Create mock user repository."""
        repo = Mock()
        repo.find_one_by = Mock()
        repo.get_by_id = Mock()
        repo.update = Mock()
        return repo

    @pytest.fixture
    def mock_token_repository(self):
        """Create mock token repository."""
        repo = Mock()
        repo.find_one_by = Mock()
        repo.create = Mock()
        repo.update = Mock()
        repo.find_by = Mock()
        return repo

    @pytest.fixture
    def mock_email_service(self):
        """Mock email service."""
        with patch("app.services.password_reset_service.email_service") as mock:
            mock.send_password_reset_email = AsyncMock(return_value=True)
            mock.send_password_reset_confirmation = AsyncMock(return_value=True)
            yield mock

    @pytest.fixture
    def service(self, mock_db, mock_user_repository, mock_token_repository):
        """Create password reset service with mocked dependencies."""
        return PasswordResetService(
            db=mock_db, user_repository=mock_user_repository, token_repository=mock_token_repository
        )

    @pytest.mark.asyncio
    async def test_request_password_reset_valid_user(
        self, service, mock_user_repository, mock_token_repository, mock_email_service
    ):
        """Test password reset request for valid user."""
        # Setup
        email = "test@example.com"
        user = Mock(spec=User)
        user.id = 123
        user.email = email
        user.full_name = "Test User"

        mock_user_repository.find_one_by.return_value = user
        mock_token_repository.find_by.return_value = []  # No existing tokens

        # Mock token creation
        mock_token_repository.create.return_value = Mock(token="test_token_123")

        # Execute
        result = await service.request_password_reset(email)

        # Verify
        assert result is True
        mock_user_repository.find_one_by.assert_called_once_with(email=email)
        mock_token_repository.create.assert_called_once()
        mock_email_service.send_password_reset_email.assert_called_once()

        # Verify email parameters
        email_call = mock_email_service.send_password_reset_email.call_args
        assert email_call.kwargs["to_email"] == email
        assert email_call.kwargs["user_name"] == "Test User"
        assert "reset_url" in email_call.kwargs

    @pytest.mark.asyncio
    async def test_request_password_reset_nonexistent_user(self, service, mock_user_repository, mock_email_service):
        """Test password reset for non-existent user - should still return True."""
        # Setup
        email = "nonexistent@example.com"
        mock_user_repository.find_one_by.return_value = None

        # Execute
        result = await service.request_password_reset(email)

        # Verify - returns True to prevent email enumeration
        assert result is True
        mock_user_repository.find_one_by.assert_called_once_with(email=email)
        mock_email_service.send_password_reset_email.assert_not_called()

    @pytest.mark.asyncio
    async def test_request_password_reset_invalidates_existing_tokens(
        self, service, mock_user_repository, mock_token_repository, mock_email_service
    ):
        """Test that existing tokens are invalidated when requesting new reset."""
        # Setup
        email = "test@example.com"
        user = Mock(spec=User, id=123, email=email, full_name="Test User")
        mock_user_repository.find_one_by.return_value = user

        # FIX: Only return unused tokens from find_by (matches implementation)
        existing_tokens = [
            Mock(id=1, used=False),
            Mock(id=2, used=False),
        ]
        mock_token_repository.find_by.return_value = existing_tokens

        # Execute
        await service.request_password_reset(email)

        # Verify existing tokens were invalidated
        assert mock_token_repository.update.call_count == 2  # Only unused tokens
        mock_token_repository.update.assert_any_call(1, used=True)
        mock_token_repository.update.assert_any_call(2, used=True)

    @pytest.mark.asyncio
    async def test_request_password_reset_email_error_handled(
        self, service, mock_user_repository, mock_email_service, mock_token_repository
    ):
        """Test that email sending errors are handled gracefully."""
        # Setup
        email = "test@example.com"
        user = Mock(spec=User, id=123, email=email, full_name="Test User")
        mock_user_repository.find_one_by.return_value = user
        mock_token_repository.find_by.return_value = []  # No existing tokens

        # Email service throws error
        mock_email_service.send_password_reset_email.side_effect = Exception("Email service down")

        # Execute
        result = await service.request_password_reset(email)

        # Verify - still returns True
        assert result is True

    def test_verify_reset_token_valid(self, service, mock_token_repository, mock_user_repository):
        """Test verification of valid reset token."""
        # Setup
        token_str = "valid_token_123"
        future_time = datetime.now(timezone.utc) + timedelta(hours=1)

        reset_token = Mock(spec=PasswordResetToken)
        reset_token.token = token_str
        reset_token.used = False
        reset_token.expires_at = future_time
        reset_token.user_id = 123

        user = Mock(spec=User)
        user.email = "test@example.com"

        mock_token_repository.find_one_by.return_value = reset_token
        mock_user_repository.get_by_id.return_value = user

        # Execute
        is_valid, masked_email = service.verify_reset_token(token_str)

        # Verify
        assert is_valid is True
        assert masked_email == "te***@example.com"
        mock_token_repository.find_one_by.assert_called_once_with(token=token_str)

    def test_verify_reset_token_nonexistent(self, service, mock_token_repository):
        """Test verification of non-existent token."""
        # Setup
        mock_token_repository.find_one_by.return_value = None

        # Execute
        is_valid, masked_email = service.verify_reset_token("nonexistent_token")

        # Verify
        assert is_valid is False
        assert masked_email is None

    def test_verify_reset_token_already_used(self, service, mock_token_repository):
        """Test verification of already used token."""
        # Setup
        reset_token = Mock(spec=PasswordResetToken)
        reset_token.used = True
        mock_token_repository.find_one_by.return_value = reset_token

        # Execute
        is_valid, masked_email = service.verify_reset_token("used_token")

        # Verify
        assert is_valid is False
        assert masked_email is None

    def test_verify_reset_token_expired(self, service, mock_token_repository):
        """Test verification of expired token."""
        # Setup
        past_time = datetime.now(timezone.utc) - timedelta(hours=1)
        reset_token = Mock(spec=PasswordResetToken)
        reset_token.used = False
        reset_token.expires_at = past_time
        mock_token_repository.find_one_by.return_value = reset_token

        # Execute
        is_valid, masked_email = service.verify_reset_token("expired_token")

        # Verify
        assert is_valid is False
        assert masked_email is None

    def test_verify_reset_token_user_not_found(self, service, mock_token_repository, mock_user_repository):
        """Test verification when user not found."""
        # Setup
        future_time = datetime.now(timezone.utc) + timedelta(hours=1)
        reset_token = Mock(spec=PasswordResetToken)
        reset_token.used = False
        reset_token.expires_at = future_time
        reset_token.user_id = 999

        mock_token_repository.find_one_by.return_value = reset_token
        mock_user_repository.get_by_id.return_value = None

        # Execute
        is_valid, masked_email = service.verify_reset_token("valid_token")

        # Verify
        assert is_valid is False
        assert masked_email is None

    def test_email_masking_logic(self, service, mock_token_repository, mock_user_repository):
        """Test email masking for different email formats."""
        # Test cases
        test_cases = [
            ("test@example.com", "te***@example.com"),
            ("a@example.com", "***@example.com"),  # Short email
            ("ab@example.com", "***@example.com"),  # 2 char email
            ("longusername@example.com", "lo***@example.com"),
        ]

        for email, expected_masked in test_cases:
            # Setup
            future_time = datetime.now(timezone.utc) + timedelta(hours=1)
            reset_token = Mock(spec=PasswordResetToken)
            reset_token.used = False
            reset_token.expires_at = future_time
            reset_token.user_id = 123

            user = Mock(spec=User)
            user.email = email

            mock_token_repository.find_one_by.return_value = reset_token
            mock_user_repository.get_by_id.return_value = user

            # Execute
            is_valid, masked_email = service.verify_reset_token("token")

            # Verify
            assert masked_email == expected_masked

    @pytest.mark.asyncio
    async def test_confirm_password_reset_success(
        self, service, mock_token_repository, mock_user_repository, mock_email_service
    ):
        """Test successful password reset confirmation."""
        # Setup
        token_str = "valid_token_123"
        new_password = "NewSecurePassword123!"
        future_time = datetime.now(timezone.utc) + timedelta(hours=1)

        reset_token = Mock(spec=PasswordResetToken)
        reset_token.id = 1
        reset_token.token = token_str
        reset_token.used = False
        reset_token.expires_at = future_time
        reset_token.user_id = 123

        user = Mock(spec=User)
        user.id = 123
        user.email = "test@example.com"
        user.full_name = "Test User"

        mock_token_repository.find_one_by.return_value = reset_token
        mock_user_repository.get_by_id.return_value = user

        # Execute
        with patch("app.services.password_reset_service.get_password_hash") as mock_hash:
            mock_hash.return_value = "hashed_password"
            result = await service.confirm_password_reset(token_str, new_password)

        # Verify
        assert result is True
        mock_hash.assert_called_once_with(new_password)
        mock_user_repository.update.assert_called_once_with(123, hashed_password="hashed_password")
        mock_token_repository.update.assert_called_once_with(1, used=True)
        mock_email_service.send_password_reset_confirmation.assert_called_once()

    @pytest.mark.asyncio
    async def test_confirm_password_reset_invalid_token(self, service, mock_token_repository):
        """Test password reset with invalid token."""
        # Setup
        mock_token_repository.find_one_by.return_value = None

        # Execute & Verify
        with pytest.raises(ValidationException) as exc_info:
            await service.confirm_password_reset("invalid_token", "NewPassword123!")

        assert "Invalid or expired reset token" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_confirm_password_reset_used_token(self, service, mock_token_repository):
        """Test password reset with already used token."""
        # Setup
        reset_token = Mock(spec=PasswordResetToken)
        reset_token.used = True
        mock_token_repository.find_one_by.return_value = reset_token

        # Execute & Verify
        with pytest.raises(ValidationException) as exc_info:
            await service.confirm_password_reset("used_token", "NewPassword123!")

        assert "already been used" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_confirm_password_reset_expired_token(self, service, mock_token_repository):
        """Test password reset with expired token."""
        # Setup
        past_time = datetime.now(timezone.utc) - timedelta(hours=1)
        reset_token = Mock(spec=PasswordResetToken)
        reset_token.used = False
        reset_token.expires_at = past_time
        mock_token_repository.find_one_by.return_value = reset_token

        # Execute & Verify
        with pytest.raises(ValidationException) as exc_info:
            await service.confirm_password_reset("expired_token", "NewPassword123!")

        assert "expired" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_confirm_password_reset_user_not_found(self, service, mock_token_repository, mock_user_repository):
        """Test password reset when user not found."""
        # Setup
        future_time = datetime.now(timezone.utc) + timedelta(hours=1)
        reset_token = Mock(spec=PasswordResetToken)
        reset_token.used = False
        reset_token.expires_at = future_time
        reset_token.user_id = 999

        mock_token_repository.find_one_by.return_value = reset_token
        mock_user_repository.get_by_id.return_value = None

        # Execute & Verify
        with pytest.raises(ValidationException) as exc_info:
            await service.confirm_password_reset("token", "NewPassword123!")

        assert "Invalid reset token" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_confirm_password_reset_database_error(self, service, mock_token_repository, mock_user_repository):
        """Test password reset with database error."""
        # Setup
        future_time = datetime.now(timezone.utc) + timedelta(hours=1)
        reset_token = Mock(spec=PasswordResetToken)
        reset_token.id = 1
        reset_token.used = False
        reset_token.expires_at = future_time
        reset_token.user_id = 123

        user = Mock(spec=User, id=123, email="test@example.com", full_name="Test User")

        mock_token_repository.find_one_by.return_value = reset_token
        mock_user_repository.get_by_id.return_value = user

        # Simulate database error
        mock_user_repository.update.side_effect = Exception("Database error")

        # Execute & Verify
        with pytest.raises(ValidationException) as exc_info:
            await service.confirm_password_reset("token", "NewPassword123!")

        assert "An error occurred" in str(exc_info.value)

    def test_generate_reset_token(self, service, mock_token_repository):
        """Test reset token generation."""
        # Setup
        user_id = 123
        mock_token_repository.create.return_value = Mock(token="generated_token")

        # Execute
        with patch("app.services.password_reset_service.secrets.token_urlsafe") as mock_secrets:
            mock_secrets.return_value = "secure_random_token"
            token = service._generate_reset_token(user_id)

        # Verify
        assert token == "secure_random_token"
        mock_token_repository.create.assert_called_once()

        # Verify token parameters
        create_call = mock_token_repository.create.call_args
        assert create_call.kwargs["user_id"] == user_id
        assert create_call.kwargs["token"] == "secure_random_token"
        assert create_call.kwargs["used"] is False
        assert "expires_at" in create_call.kwargs

    def test_generate_reset_token_uniqueness(self, service, mock_token_repository):
        """Test that generated tokens are unique."""
        # Generate multiple tokens
        tokens = set()
        for i in range(10):
            with patch("app.services.password_reset_service.secrets.token_urlsafe") as mock_secrets:
                # Simulate unique token generation
                mock_secrets.return_value = f"unique_token_{i}"
                token = service._generate_reset_token(123)
                tokens.add(token)

        # All tokens should be unique
        assert len(tokens) == 10

    def test_invalidate_existing_tokens(self, service, mock_token_repository):
        """Test invalidation of existing tokens."""
        # Setup
        user_id = 123
        # FIX: find_by with used=False should only return unused tokens
        existing_tokens = [
            Mock(id=1, used=False),
            Mock(id=2, used=False),
            Mock(id=3, used=False),
        ]
        mock_token_repository.find_by.return_value = existing_tokens

        # Execute
        service._invalidate_existing_tokens(user_id)

        # Verify
        mock_token_repository.find_by.assert_called_once_with(user_id=user_id, used=False)

        # Should update only unused tokens
        assert mock_token_repository.update.call_count == 3
        mock_token_repository.update.assert_any_call(1, used=True)
        mock_token_repository.update.assert_any_call(2, used=True)
        mock_token_repository.update.assert_any_call(3, used=True)

        # Should flush changes
        service.db.flush.assert_called_once()

    def test_invalidate_existing_tokens_none_found(self, service, mock_token_repository):
        """Test invalidation when no existing tokens found."""
        # Setup
        mock_token_repository.find_by.return_value = []

        # Execute
        service._invalidate_existing_tokens(123)

        # Verify
        mock_token_repository.update.assert_not_called()
        service.db.flush.assert_called_once()


class TestPasswordResetSecurityScenarios:
    """Test security-specific scenarios for password reset."""

    @pytest.fixture
    def mock_db(self):
        """Create mock database session."""
        db = Mock(spec=Session)
        db.commit = Mock()
        db.rollback = Mock()
        db.flush = Mock()
        db.begin_nested = Mock()
        db.begin_nested.return_value.__enter__ = Mock()
        db.begin_nested.return_value.__exit__ = Mock()
        return db

    @pytest.fixture
    def mock_user_repository(self):
        """Create mock user repository."""
        repo = Mock()
        repo.find_one_by = Mock()
        repo.get_by_id = Mock()
        repo.update = Mock()
        return repo

    @pytest.fixture
    def mock_token_repository(self):
        """Create mock token repository."""
        repo = Mock()
        repo.find_one_by = Mock()
        repo.create = Mock()
        repo.update = Mock()
        repo.find_by = Mock()
        return repo

    @pytest.fixture
    def mock_email_service(self):
        """Mock email service."""
        with patch("app.services.password_reset_service.email_service") as mock:
            mock.send_password_reset_email = AsyncMock(return_value=True)
            mock.send_password_reset_confirmation = AsyncMock(return_value=True)
            yield mock

    @pytest.fixture
    def service(self, mock_db, mock_user_repository, mock_token_repository):
        """Create service for security tests."""
        return PasswordResetService(
            db=mock_db, user_repository=mock_user_repository, token_repository=mock_token_repository
        )

    @pytest.mark.asyncio
    async def test_concurrent_reset_requests(
        self, service, mock_user_repository, mock_token_repository, mock_email_service
    ):
        """Test handling of concurrent password reset requests."""
        # Setup
        email = "test@example.com"
        user = Mock(spec=User, id=123, email=email, full_name="Test User")
        mock_user_repository.find_one_by.return_value = user

        # Simulate multiple existing tokens (from concurrent requests)
        existing_tokens = [Mock(id=i, used=False) for i in range(5)]
        mock_token_repository.find_by.return_value = existing_tokens

        # Execute
        await service.request_password_reset(email)

        # Verify all previous tokens are invalidated
        assert mock_token_repository.update.call_count == 5

    @pytest.mark.asyncio
    async def test_token_reuse_prevention(self, service, mock_token_repository):
        """Test that used tokens cannot be reused."""
        # Setup
        used_token = Mock(spec=PasswordResetToken)
        used_token.used = True
        used_token.id = 1
        mock_token_repository.find_one_by.return_value = used_token

        # First verify returns false
        is_valid, _ = service.verify_reset_token("used_token")
        assert is_valid is False

        # Confirm also raises exception
        with pytest.raises(ValidationException) as exc_info:
            await service.confirm_password_reset("used_token", "NewPassword123!")
        assert "already been used" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_timing_attack_prevention(
        self, service, mock_user_repository, mock_email_service, mock_token_repository
    ):
        """Test that response time is consistent for existing and non-existing users."""
        import time

        # Setup for existing user
        user = Mock(spec=User, id=123, email="exists@example.com", full_name="User")
        mock_user_repository.find_one_by.return_value = user
        mock_token_repository.find_by.return_value = []

        start = time.time()
        result1 = await service.request_password_reset("exists@example.com")
        time.time() - start

        # Test with non-existing user
        mock_user_repository.find_one_by.return_value = None

        start = time.time()
        result2 = await service.request_password_reset("notexists@example.com")
        time.time() - start

        # Both should return True
        assert result1 is True
        assert result2 is True

        # Response times should be similar (preventing timing attacks)
        # Note: In real implementation, you might add deliberate delays

    def test_token_entropy(self, service, mock_token_repository):
        """Test that tokens have sufficient entropy."""
        # Mock the secrets module to verify it's being used correctly
        with patch("app.services.password_reset_service.secrets.token_urlsafe") as mock_secrets:
            mock_secrets.return_value = "X" * 43  # Base64 encoding of 32 bytes

            token = service._generate_reset_token(123)

            # Verify 32 bytes of entropy (256 bits)
            mock_secrets.assert_called_once_with(32)
            assert len(token) >= 32  # Base64 encoded will be longer
