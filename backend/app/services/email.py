# backend/app/services/email.py

import logging
import resend
from typing import Optional
from ..core.config import settings

logger = logging.getLogger(__name__)

class EmailService:
    """Service for sending emails using Resend"""
    
    def __init__(self):
        """Initialize Resend with API key"""
        api_key = settings.resend_api_key
        resend.api_key = api_key
        self.from_email = settings.from_email or "noreply@instructly.com"
        
    async def send_password_reset_email(
        self, 
        to_email: str, 
        reset_url: str,
        user_name: Optional[str] = None
    ) -> bool:
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
            subject = "Reset Your Instructly Password"
            
            # HTML email content
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
                    <h1 style="color: white; margin: 0;">Instructly</h1>
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
                        This email was sent by Instructly. If you have any questions, please contact our support team.
                    </p>
                </div>
            </body>
            </html>
            """
            
            # Plain text fallback
            text_content = f"""
            Reset Your Instructly Password
            
            Hi {user_name or 'there'},
            
            We received a request to reset your password. Click the link below to create a new password:
            
            {reset_url}
            
            This link will expire in 1 hour for security reasons.
            
            If you didn't request this password reset, please ignore this email. Your password won't be changed.
            
            - The Instructly Team
            """
            
            # Send email using Resend
            response = resend.Emails.send({
                "from": self.from_email,
                "to": to_email,
                "subject": subject,
                "html": html_content,
                "text": text_content
            })
            
            logger.info(f"Password reset email sent successfully to {to_email}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send password reset email to {to_email}: {str(e)}")
            return False
    
    async def send_password_reset_confirmation(
        self, 
        to_email: str,
        user_name: Optional[str] = None
    ) -> bool:
        """
        Send confirmation email after successful password reset.
        
        Args:
            to_email: Recipient email address
            user_name: Optional user's name for personalization
            
        Returns:
            bool: True if email sent successfully, False otherwise
        """
        try:
            subject = "Your Instructly Password Has Been Reset"
            
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
            </head>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
                <div style="background-color: #4F46E5; padding: 30px; text-align: center; border-radius: 10px 10px 0 0;">
                    <h1 style="color: white; margin: 0;">Instructly</h1>
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
                    
                    <p>Best regards,<br>The Instructly Team</p>
                </div>
            </body>
            </html>
            """
            
            response = resend.Emails.send({
                "from": self.from_email,
                "to": to_email,
                "subject": subject,
                "html": html_content
            })
            
            logger.info(f"Password reset confirmation email sent to {to_email}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send confirmation email to {to_email}: {str(e)}")
            return False

# Create a singleton instance
email_service = EmailService()