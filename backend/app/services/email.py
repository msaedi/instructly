# backend/app/services/email.py
"""
Email Service for InstaInstru Platform (Refactored)

Provides email sending functionality using Resend API with proper dependency injection,
metrics collection, and error handling. Extends BaseService for consistency.

Changes from original:
- Extends BaseService for consistent architecture
- No singleton pattern - uses dependency injection
- Added performance metrics with @measure_operation
- Improved error handling and logging
- Better separation of concerns
"""

import logging
from typing import TYPE_CHECKING, Any, Dict, Optional

import resend
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.constants import BRAND_NAME, NOREPLY_EMAIL
from ..core.exceptions import ServiceException
from .base import BaseService

# Use TYPE_CHECKING to avoid circular imports
if TYPE_CHECKING:
    from .cache_service import CacheService

logger = logging.getLogger(__name__)


class EmailService(BaseService):
    """
    Service for sending emails using Resend API.

    Extends BaseService for consistent architecture, metrics collection,
    and standardized error handling. Uses dependency injection pattern.
    """

    def __init__(self, db: Session, cache: Optional["CacheService"] = None):
        """
        Initialize email service with dependencies.

        Args:
            db: Database session (required by BaseService)
            cache: Optional cache service (not used but kept for consistency)
        """
        super().__init__(db, cache)

        # Initialize Resend with API key
        api_key = settings.resend_api_key
        if not api_key:
            raise ServiceException("Resend API key not configured")

        resend.api_key = api_key
        self.from_email = settings.from_email
        if not self.from_email or "noreply" in self.from_email.lower():
            # Use better default with mail subdomain
            self.from_email = "InstaInstru <hello@mail.instainstru.com>"

        self.logger.info("EmailService initialized successfully")

    def _html_to_text(self, html_content: str) -> str:
        """Convert HTML content to plain text for better deliverability"""
        import re

        # Remove HTML tags
        text = re.sub(r"<[^>]+>", "", html_content)
        # Replace multiple whitespace/newlines with single
        text = re.sub(r"\s+", " ", text)
        # Clean up spacing around lines
        text = text.strip()
        return text

    @BaseService.measure_operation("send_email")
    def send_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None,
        from_email: Optional[str] = None,
        from_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Send a generic email using Resend.

        Args:
            to_email: Recipient email address
            subject: Email subject
            html_content: HTML content of the email
            text_content: Optional plain text version
            from_email: Optional sender email (defaults to settings)
            from_name: Optional sender name

        Returns:
            Dict containing the Resend API response

        Raises:
            ServiceException: If email sending fails
        """
        try:
            # Configure sender
            sender_email = from_email or self.from_email
            if from_name:
                sender = f"{from_name} <{sender_email}>"
            else:
                sender = sender_email

            # IMPORTANT: Always include text version for better deliverability
            if not text_content:
                text_content = self._html_to_text(html_content)

            # Build email data
            email_data = {
                "from": sender,
                "to": to_email,
                "subject": subject,
                "html": html_content,
                "text": text_content,  # Critical for authentication
            }

            # Send email
            response = resend.Emails.send(email_data)

            self.logger.info(f"Email sent successfully to {to_email} - Subject: {subject}")
            self.log_operation("email_sent", to_email=to_email, subject=subject)

            return response

        except Exception as e:
            self.logger.error(f"Failed to send email to {to_email}: {str(e)}")
            self.log_operation("email_failed", to_email=to_email, subject=subject, error=str(e))
            raise ServiceException(f"Email sending failed: {str(e)}")

    @BaseService.measure_operation("send_password_reset_email")
    async def send_password_reset_email(self, to_email: str, reset_url: str, user_name: Optional[str] = None) -> bool:
        """
        Send password reset email.

        Args:
            to_email: Recipient email address
            reset_url: The password reset URL with token
            user_name: Optional user's name for personalization

        Returns:
            bool: True if email sent successfully, False otherwise
        """
        try:
            subject = f"Reset Your {BRAND_NAME} Password"

            # HTML email content (with f-strings fixed)
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Reset Your Password</title>
            </head>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
                <div style="background-color: #4F46E5; padding: 30px; text-align: center; border-radius: 10px 10px 0 0;">
                    <h1 style="color: white; margin: 0;">{BRAND_NAME}</h1>
                </div>

                <div style="background-color: #f8f9fa; padding: 40px; border-radius: 0 0 10px 10px;">
                    <h2 style="color: #4F46E5; margin-bottom: 20px;">Reset Your Password</h2>

                    <p>Hi {user_name or 'there'},</p>

                    <p>We received a request to reset your password. Click the button below to create a new password:</p>

                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{reset_url}" style="background-color: #4F46E5; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; display: inline-block;">
                            Reset Password
                        </a>
                    </div>

                    <p>Or copy and paste this link into your browser:</p>
                    <p style="word-break: break-all; color: #666; font-size: 14px;">{reset_url}</p>

                    <p><strong>This link will expire in 1 hour for security reasons.</strong></p>

                    <p>If you didn't request this password reset, please ignore this email. Your password won't be changed.</p>

                    <hr style="border: none; border-top: 1px solid #ddd; margin: 30px 0;">

                    <p style="color: #666; font-size: 12px; text-align: center;">
                        This email was sent by {BRAND_NAME}. If you have any questions, please contact our support team.
                    </p>
                </div>
            </body>
            </html>
            """

            # Plain text fallback (with f-strings fixed)
            text_content = f"""
            Reset Your {BRAND_NAME} Password

            Hi {user_name or 'there'},

            We received a request to reset your password. Click the link below to create a new password:

            {reset_url}

            This link will expire in 1 hour for security reasons.

            If you didn't request this password reset, please ignore this email. Your password won't be changed.

            - The {BRAND_NAME} Team
            """

            # Send email using the generic method
            self.send_email(
                to_email=to_email,
                subject=subject,
                html_content=html_content,
                text_content=text_content,
            )

            self.log_operation("password_reset_email_sent", to_email=to_email)
            return True

        except ServiceException:
            # Already logged in send_email
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error sending password reset email to {to_email}: {str(e)}")
            return False

    @BaseService.measure_operation("send_password_reset_confirmation")
    async def send_password_reset_confirmation(self, to_email: str, user_name: Optional[str] = None) -> bool:
        """
        Send confirmation email after successful password reset.

        Args:
            to_email: Recipient email address
            user_name: Optional user's name for personalization

        Returns:
            bool: True if email sent successfully, False otherwise
        """
        try:
            subject = f"Your {BRAND_NAME} Password Has Been Reset"

            # HTML content (with f-strings fixed)
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
            </head>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
                <div style="background-color: #4F46E5; padding: 30px; text-align: center; border-radius: 10px 10px 0 0;">
                    <h1 style="color: white; margin: 0;">{BRAND_NAME}</h1>
                </div>

                <div style="background-color: #f8f9fa; padding: 40px; border-radius: 0 0 10px 10px;">
                    <h2 style="color: #4F46E5; margin-bottom: 20px;">Password Reset Successful</h2>

                    <p>Hi {user_name or 'there'},</p>

                    <p>Your password has been successfully reset. You can now log in with your new password.</p>

                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{settings.frontend_url}/login" style="background-color: #4F46E5; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; display: inline-block;">
                            Log In
                        </a>
                    </div>

                    <p>If you didn't make this change, please contact our support team immediately.</p>

                    <p>Best regards,<br>The {BRAND_NAME} Team</p>
                </div>
            </body>
            </html>
            """

            # Plain text fallback
            text_content = f"""
            Your {BRAND_NAME} Password Has Been Reset

            Hi {user_name or 'there'},

            Your password has been successfully reset. You can now log in with your new password.

            Log in at: {settings.frontend_url}/login

            If you didn't make this change, please contact our support team immediately.

            Best regards,
            The {BRAND_NAME} Team
            """

            self.send_email(to_email=to_email, subject=subject, html_content=html_content, text_content=text_content)

            self.log_operation("password_reset_confirmation_sent", to_email=to_email)
            return True

        except ServiceException:
            # Already logged in send_email
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error sending confirmation email to {to_email}: {str(e)}")
            return False

    @BaseService.measure_operation("validate_email_config")
    def validate_email_config(self) -> bool:
        """
        Validate email service configuration.

        Returns:
            bool: True if configuration is valid

        Raises:
            ServiceException: If configuration is invalid
        """
        if not settings.resend_api_key:
            raise ServiceException("Resend API key not configured")

        if not self.from_email:
            raise ServiceException("From email address not configured")

        self.logger.info("Email configuration validated successfully")
        return True

    @BaseService.measure_operation("get_send_stats")
    def get_send_stats(self) -> Dict[str, Any]:
        """
        Get email sending statistics from metrics.

        Returns:
            Dict with email sending statistics
        """
        metrics = self.get_metrics()

        # Extract email-specific metrics
        email_stats = {
            "emails_sent": metrics.get("send_email", {}).get("success_count", 0),
            "emails_failed": metrics.get("send_email", {}).get("failure_count", 0),
            "password_resets_sent": metrics.get("send_password_reset_email", {}).get("success_count", 0),
            "confirmations_sent": metrics.get("send_password_reset_confirmation", {}).get("success_count", 0),
            "avg_send_time": metrics.get("send_email", {}).get("avg_time", 0),
        }

        # Calculate success rate
        total_attempts = email_stats["emails_sent"] + email_stats["emails_failed"]
        if total_attempts > 0:
            email_stats["success_rate"] = email_stats["emails_sent"] / total_attempts
        else:
            email_stats["success_rate"] = 0.0

        return email_stats
