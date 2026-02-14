# backend/app/services/password_reset_service.py
"""
Password Reset Service for InstaInstru Platform

Handles password reset token generation, validation, and password updates.
Follows the service layer pattern to keep business logic out of routes.
"""

from datetime import datetime, timedelta, timezone
import logging
import secrets
from typing import TYPE_CHECKING, Optional, Tuple

from sqlalchemy.orm import Session

from ..auth import get_password_hash
from ..core.config import settings
from ..core.exceptions import ValidationException
from ..models.password_reset import PasswordResetToken
from ..models.user import User
from ..repositories.factory import RepositoryFactory
from ..services.email import EmailService
from .base import BaseService, CacheInvalidationProtocol

if TYPE_CHECKING:
    from ..repositories.base_repository import BaseRepository

logger = logging.getLogger(__name__)


class PasswordResetService(BaseService):
    """Service for handling password reset operations."""

    def __init__(
        self,
        db: Session,
        cache_service: Optional[CacheInvalidationProtocol] = None,
        email_service: Optional[EmailService] = None,
        user_repository: Optional["BaseRepository[User]"] = None,
        token_repository: Optional["BaseRepository[PasswordResetToken]"] = None,
    ):
        """Initialize password reset service."""
        super().__init__(db, cache=cache_service)
        self.logger = logging.getLogger(__name__)

        # Initialize email service using dependency injection
        if email_service is None:
            self.email_service = EmailService(db, cache_service)
        else:
            self.email_service = email_service

        # Initialize repositories using BaseRepository
        self.user_repository = user_repository or RepositoryFactory.create_user_repository(db)
        self.token_repository = token_repository or RepositoryFactory.create_base_repository(
            db, PasswordResetToken
        )

    @BaseService.measure_operation("request_password_reset")
    def request_password_reset(self, email: str) -> bool:
        """
        Request a password reset for the given email.

        Always returns True to prevent email enumeration attacks.

        Args:
            email: Email address requesting reset

        Returns:
            bool: Always True for security
        """
        self.log_operation("request_password_reset", email=email)

        # Find user by email
        user = self.user_repository.find_one_by(email=email)

        if user:
            try:
                with self.transaction():
                    # Invalidate existing tokens
                    self._invalidate_existing_tokens(user.id)

                    # Generate new token
                    _token = self._generate_reset_token(user.id)

                    # Create reset URL
                    reset_url = f"{settings.frontend_url}/reset-password?token={_token}"

                    # Send email
                    self.email_service.send_password_reset_email(
                        to_email=user.email,
                        reset_url=reset_url,
                        user_name=user.first_name,
                    )

                    self.logger.info(f"Password reset token created for user {user.id}")

            except Exception as e:
                self.logger.error(f"Error creating password reset token: {str(e)}")
                # Still return True to prevent enumeration
        else:
            # Log that email doesn't exist but don't reveal this
            self.logger.warning(f"Password reset requested for non-existent email: {email}")

        # Always return True to prevent email enumeration
        return True

    @BaseService.measure_operation("verify_reset_token")
    def verify_reset_token(self, token: str) -> Tuple[bool, Optional[str]]:
        """
        Verify if a reset token is valid.

        Args:
            token: Reset token to verify

        Returns:
            Tuple of (is_valid, masked_email)
        """
        reset_token = self.token_repository.find_one_by(token=token)

        if not reset_token:
            return (False, None)

        if reset_token.used:
            self.logger.warning(f"Attempted to use already used token: {token[:8]}...")
            return (False, None)

        if datetime.now(timezone.utc) > reset_token.expires_at:
            self.logger.warning(f"Attempted to use expired token: {token[:8]}...")
            return (False, None)

        # Get user for email masking
        user = self.user_repository.get_by_id(reset_token.user_id)
        if not user:
            return (False, None)

        # Mask email for privacy
        email_parts = user.email.split("@")
        if len(email_parts[0]) > 2:
            masked_email = email_parts[0][:2] + "***" + "@" + email_parts[1]
        else:
            masked_email = "***@" + email_parts[1]

        return (True, masked_email)

    @BaseService.measure_operation("confirm_password_reset")
    def confirm_password_reset(self, token: str, new_password: str) -> bool:
        """
        Complete password reset with token and new password.

        Args:
            token: Reset token
            new_password: New password to set

        Returns:
            bool: True if successful

        Raises:
            ValidationException: If token is invalid, expired, or already used
        """
        self.logger.info(f"Password reset confirmation attempted with token: {token[:8]}...")

        # Find the token
        reset_token = self.token_repository.find_one_by(token=token)

        if not reset_token:
            self.logger.warning(f"Invalid password reset token: {token[:8]}...")
            raise ValidationException("Invalid or expired reset token")

        # Check if token is already used
        if reset_token.used:
            self.logger.warning(f"Attempted to reuse password reset token: {token[:8]}...")
            raise ValidationException("This reset link has already been used")

        # Check if token is expired
        if datetime.now(timezone.utc) > reset_token.expires_at:
            self.logger.warning(f"Expired password reset token used: {token[:8]}...")
            raise ValidationException("This reset link has expired")

        # Get the user
        user = self.user_repository.get_by_id(reset_token.user_id)
        if not user:
            self.logger.error(f"User not found for reset token: {reset_token.user_id}")
            raise ValidationException("Invalid reset token")

        try:
            with self.transaction():
                # Update password
                self.user_repository.update(
                    user.id, hashed_password=get_password_hash(new_password)
                )

                # Mark token as used
                self.token_repository.update(reset_token.id, used=True)

                # Send confirmation email
                self.email_service.send_password_reset_confirmation(
                    to_email=user.email,
                    user_name=user.first_name,
                )

            invalidation_repo = RepositoryFactory.create_user_repository(self.db)
            if not invalidation_repo.invalidate_all_tokens(user.id):
                self.logger.warning(
                    "Password reset succeeded but token invalidation helper returned false for user %s",
                    user.id,
                )

            self.logger.info(f"Password successfully reset for user {user.id}")
            return True

        except Exception as e:
            self.logger.error(f"Error resetting password: {str(e)}")
            raise ValidationException("An error occurred while resetting your password")

    def _generate_reset_token(self, user_id: str) -> str:
        """
        Generate a unique reset token for a user.

        Args:
            user_id: User ID

        Returns:
            str: Generated token string
        """
        token = secrets.token_urlsafe(32)
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

        _reset_token = self.token_repository.create(
            user_id=user_id,
            token=token,
            expires_at=expires_at,
            used=False,
        )

        return token

    def _invalidate_existing_tokens(self, user_id: str) -> None:
        """
        Mark all existing tokens for a user as used.

        Args:
            user_id: User ID
        """
        # Get all unused tokens for this user
        unused_tokens = self.token_repository.find_by(user_id=user_id, used=False)

        # Update each token to mark as used
        for token in unused_tokens:
            self.token_repository.update(token.id, used=True)

        self.token_repository.flush()
