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
from ..core.constants import BRAND_NAME
from ..core.exceptions import ServiceException
from .base import BaseService
from .email_subjects import EmailSubject
from .template_registry import TemplateRegistry
from .template_service import TemplateService

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
            # Use better default with root domain
            self.from_email = "InstaInstru <hello@instainstru.com>"

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
            error_msg = str(e) if e else "Unknown error"
            self.logger.error(f"Failed to send email to {to_email}: {error_msg}")
            self.logger.error(f"Exception type: {type(e).__name__}")
            self.logger.error(f"Exception details: {repr(e)}")
            self.log_operation("email_failed", to_email=to_email, subject=subject, error=error_msg)
            raise ServiceException(f"Email sending failed: {error_msg}")

    @BaseService.measure_operation("send_password_reset_email")
    def send_password_reset_email(self, to_email: str, reset_url: str, user_name: Optional[str] = None) -> bool:
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
            subject = EmailSubject.password_reset()

            # Render via Jinja template
            template_service = TemplateService(self.db, self.cache)
            html_content = template_service.render_template(
                TemplateRegistry.AUTH_PASSWORD_RESET,
                context={"reset_url": reset_url, "user_name": user_name},
            )

            # Minimal text fallback
            text_content = f"Reset your {BRAND_NAME} password: {reset_url} (expires in 1 hour)"

            self.send_email(to_email=to_email, subject=subject, html_content=html_content, text_content=text_content)

            self.log_operation("password_reset_email_sent", to_email=to_email)
            return True

        except ServiceException:
            # Already logged in send_email
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error sending password reset email to {to_email}: {str(e)}")
            return False

    @BaseService.measure_operation("send_password_reset_confirmation")
    def send_password_reset_confirmation(self, to_email: str, user_name: Optional[str] = None) -> bool:
        """
        Send confirmation email after successful password reset.

        Args:
            to_email: Recipient email address
            user_name: Optional user's name for personalization

        Returns:
            bool: True if email sent successfully, False otherwise
        """
        try:
            subject = EmailSubject.password_reset_confirmation()

            template_service = TemplateService(self.db, self.cache)
            html_content = template_service.render_template(
                TemplateRegistry.AUTH_PASSWORD_RESET_CONFIRMATION,
                context={"user_name": user_name},
            )
            text_content = f"Your {BRAND_NAME} password has been reset. Log in: {settings.frontend_url}/login"

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

    @BaseService.measure_operation("send_referral_invite")
    def send_referral_invite(self, to_email: str, referral_link: str, inviter_name: str) -> Dict[str, Any]:
        """
        Send a referral invite email using Jinja2 templates.

        Args:
            to_email: Recipient email
            referral_link: Referral URL
            inviter_name: Name of the inviter
        """
        template_service = TemplateService(self.db, self.cache)
        # Render referral template with correct variable names
        html = template_service.render_template(
            TemplateRegistry.REFERRALS_INVITE,
            context={
                "inviter_name": inviter_name,
                "referral_link": referral_link,
                # Title/subtitle are controlled by the child template; subject still drives the email header
                "subject": EmailSubject.referral_invite(inviter_name),
            },
        )

        subject = EmailSubject.referral_invite(inviter_name)

        return self.send_email(
            to_email=to_email,
            subject=subject,
            html_content=html,
            text_content=f"{inviter_name} invited you to {BRAND_NAME}. Claim your discount: {referral_link}",
            from_email="invites@instainstru.com",
            from_name=BRAND_NAME,
        )

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
