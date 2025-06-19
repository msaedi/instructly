# backend/app/services/email.py

import logging
from typing import Any, Dict, Optional

import resend

from ..core.config import settings
from ..core.constants import BRAND_NAME, NOREPLY_EMAIL

logger = logging.getLogger(__name__)


class EmailService:
    """Service for sending emails using Resend"""

    def __init__(self):
        """Initialize Resend with API key"""
        api_key = settings.resend_api_key
        resend.api_key = api_key
        self.from_email = settings.from_email or NOREPLY_EMAIL

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
            Exception: If email sending fails
        """
        try:
            # Build the from field
            if from_email:
                sender = f"{from_name} <{from_email}>" if from_name else from_email
            else:
                sender = f"{BRAND_NAME} <{self.from_email}>"

            # Build email data
            email_data = {
                "from": sender,
                "to": to_email,
                "subject": subject,
                "html": html_content,
            }

            # Add text content if provided
            if text_content:
                email_data["text"] = text_content

            # Send email
            response = resend.Emails.send(email_data)

            logger.info(f"Email sent successfully to {to_email} - Subject: {subject}")
            return response

        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {str(e)}")
            raise

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

            # HTML email content
            html_content = """
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
                        This email was sent by {BRAND_NAME}. If you have any questions, please contact our support team at <a href="mailto:{SUPPORT_EMAIL}">{SUPPORT_EMAIL}</a>.
                    </p>
                </div>
            </body>
            </html>
            """

            # Plain text fallback
            text_content = """
            Reset Your {BRAND_NAME} Password

            Hi {user_name or 'there'},

            We received a request to reset your password. Click the link below to create a new password:

            {reset_url}

            This link will expire in 1 hour for security reasons.

            If you didn't request this password reset, please ignore this email. Your password won't be changed.

            - The {BRAND_NAME} Team
            Questions? Contact us at {SUPPORT_EMAIL}
            """

            # Send email using the generic method
            self.send_email(
                to_email=to_email,
                subject=subject,
                html_content=html_content,
                text_content=text_content,
            )

            return True

        except Exception as e:
            logger.error(f"Failed to send password reset email to {to_email}: {str(e)}")
            return False

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

            html_content = """
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

            self.send_email(to_email=to_email, subject=subject, html_content=html_content)

            return True

        except Exception as e:
            logger.error(f"Failed to send confirmation email to {to_email}: {str(e)}")
            return False


# Create a singleton instance
email_service = EmailService()
