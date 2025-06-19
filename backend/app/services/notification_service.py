# backend/app/services/notification_service.py
"""
Notification Service for InstaInstru Platform

Handles all platform notifications including:
- Booking confirmations
- Cancellation notices
- Reminder emails
- General notifications

This service acts as the central hub for all communication with users.
"""

import logging
from typing import Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from ..models.booking import Booking
from ..models.user import User
from ..models.instructor import InstructorProfile
from ..services.email import email_service
from ..core.config import settings
from ..core.constants import BRAND_NAME

logger = logging.getLogger(__name__)


class NotificationService:
    """
    Central notification service for the platform.
    
    Handles all types of notifications and ensures consistent
    communication with users across different channels.
    """
    
    def __init__(self, db: Session = None):
        """
        Initialize the notification service.
        
        Args:
            db: Optional database session for loading additional data
        """
        self.db = db
        self.email_service = email_service
        self.frontend_url = settings.frontend_url
        
    async def send_booking_confirmation(self, booking: Booking) -> bool:
        """
        Send booking confirmation emails to both student and instructor.
        
        Args:
            booking: The booking object with all related data loaded
            
        Returns:
            bool: True if all emails sent successfully
        """
        try:
            logger.info(f"Sending booking confirmation emails for booking {booking.id}")
            
            # Send to student
            student_success = await self._send_student_booking_confirmation(booking)
            
            # Send to instructor
            instructor_success = await self._send_instructor_booking_notification(booking)
            
            if student_success and instructor_success:
                logger.info(f"All booking confirmation emails sent for booking {booking.id}")
                return True
            else:
                logger.warning(f"Some booking confirmation emails failed for booking {booking.id}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending booking confirmation emails: {str(e)}")
            return False
    
    async def send_cancellation_notification(
        self, 
        booking: Booking,
        cancelled_by: User,
        reason: Optional[str] = None
    ) -> bool:
        """
        Send cancellation notification emails.
        
        Args:
            booking: The cancelled booking
            cancelled_by: The user who cancelled
            reason: Optional cancellation reason
            
        Returns:
            bool: True if all emails sent successfully
        """
        try:
            logger.info(f"Sending cancellation emails for booking {booking.id}")
            
            # Determine who cancelled
            is_student_cancellation = cancelled_by.id == booking.student_id
            
            # Send appropriate emails
            if is_student_cancellation:
                # Student cancelled - notify instructor
                success = await self._send_instructor_cancellation_notification(
                    booking, reason, "student"
                )
                # Also send confirmation to student
                student_success = await self._send_student_cancellation_confirmation(booking)
                return success and student_success
            else:
                # Instructor cancelled - notify student
                success = await self._send_student_cancellation_notification(
                    booking, reason, "instructor"
                )
                # Also send confirmation to instructor
                instructor_success = await self._send_instructor_cancellation_confirmation(booking)
                return success and instructor_success
                
        except Exception as e:
            logger.error(f"Error sending cancellation emails: {str(e)}")
            return False
    
    async def send_reminder_emails(self) -> int:
        """
        Send 24-hour reminder emails for upcoming bookings.
        
        This should be called by a scheduled job.
        
        Returns:
            int: Number of reminders sent
        """
        if not self.db:
            logger.error("Database session required for sending reminders")
            return 0
            
        try:
            # Get tomorrow's confirmed bookings
            tomorrow = datetime.now().date() + timedelta(days=1)
            
            bookings = self.db.query(Booking).filter(
                Booking.booking_date == tomorrow,
                Booking.status == "CONFIRMED"
            ).all()
            
            logger.info(f"Found {len(bookings)} bookings for tomorrow")
            
            sent_count = 0
            for booking in bookings:
                try:
                    # Send to student
                    student_sent = await self._send_student_reminder(booking)
                    # Send to instructor
                    instructor_sent = await self._send_instructor_reminder(booking)
                    
                    if student_sent and instructor_sent:
                        sent_count += 1
                        
                except Exception as e:
                    logger.error(f"Error sending reminder for booking {booking.id}: {str(e)}")
                    
            logger.info(f"Sent {sent_count} reminder emails")
            return sent_count
            
        except Exception as e:
            logger.error(f"Error in send_reminder_emails: {str(e)}")
            return 0
    
    # Private methods for specific email types
    
    async def _send_student_booking_confirmation(self, booking: Booking) -> bool:
        """Send booking confirmation email to student."""
        try:
            subject = f"Booking Confirmed: {booking.service_name} with {booking.instructor.full_name}"
            
            # Format booking time
            booking_datetime = datetime.combine(booking.booking_date, booking.start_time)
            formatted_date = booking_datetime.strftime("%A, %B %d, %Y")
            formatted_time = booking_datetime.strftime("%-I:%M %p")
            
            # Build email content
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Booking Confirmation</title>
            </head>
            <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
                <div style="background-color: #4F46E5; padding: 30px; text-align: center; border-radius: 10px 10px 0 0;">
                    <h1 style="color: white; margin: 0; font-size: 28px;">{BRAND_NAME}</h1>
                    <p style="color: #E0E7FF; margin: 10px 0 0 0;">Your lesson is confirmed!</p>
                </div>
                
                <div style="background-color: #f8f9fa; padding: 40px; border-radius: 0 0 10px 10px;">
                    <h2 style="color: #1F2937; margin-bottom: 20px;">Booking Confirmation</h2>
                    
                    <p style="color: #4B5563; font-size: 16px;">Hi {booking.student.full_name},</p>
                    
                    <p style="color: #4B5563;">Great news! Your lesson has been confirmed.</p>
                    
                    <div style="background-color: white; padding: 25px; border-radius: 8px; margin: 25px 0; border: 1px solid #E5E7EB;">
                        <h3 style="color: #1F2937; margin-top: 0; margin-bottom: 15px;">Booking Details</h3>
                        
                        <table style="width: 100%; border-collapse: collapse;">
                            <tr>
                                <td style="padding: 8px 0; color: #6B7280;">Service:</td>
                                <td style="padding: 8px 0; color: #1F2937; font-weight: 600;">{booking.service_name}</td>
                            </tr>
                            <tr>
                                <td style="padding: 8px 0; color: #6B7280;">Instructor:</td>
                                <td style="padding: 8px 0; color: #1F2937; font-weight: 600;">{booking.instructor.full_name}</td>
                            </tr>
                            <tr>
                                <td style="padding: 8px 0; color: #6B7280;">Date:</td>
                                <td style="padding: 8px 0; color: #1F2937; font-weight: 600;">{formatted_date}</td>
                            </tr>
                            <tr>
                                <td style="padding: 8px 0; color: #6B7280;">Time:</td>
                                <td style="padding: 8px 0; color: #1F2937; font-weight: 600;">{formatted_time}</td>
                            </tr>
                            <tr>
                                <td style="padding: 8px 0; color: #6B7280;">Duration:</td>
                                <td style="padding: 8px 0; color: #1F2937; font-weight: 600;">{booking.duration_minutes} minutes</td>
                            </tr>
                            <tr>
                                <td style="padding: 8px 0; color: #6B7280;">Location:</td>
                                <td style="padding: 8px 0; color: #1F2937; font-weight: 600;">{booking.location_type_display}</td>
                            </tr>
                            {f'''<tr>
                                <td style="padding: 8px 0; color: #6B7280;">Address:</td>
                                <td style="padding: 8px 0; color: #1F2937; font-weight: 600;">{booking.meeting_location}</td>
                            </tr>''' if booking.meeting_location else ''}
                            <tr>
                                <td style="padding: 8px 0; color: #6B7280;">Total Price:</td>
                                <td style="padding: 8px 0; color: #1F2937; font-weight: 600;">${booking.total_price:.2f}</td>
                            </tr>
                        </table>
                    </div>
                    
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{self.frontend_url}/dashboard/student/bookings" 
                           style="background-color: #4F46E5; color: white; padding: 12px 30px; text-decoration: none; border-radius: 6px; display: inline-block; font-weight: 600;">
                            View Booking Details
                        </a>
                    </div>
                    
                    <div style="background-color: #FEF3C7; padding: 15px; border-radius: 6px; margin: 20px 0;">
                        <p style="color: #92400E; margin: 0; font-size: 14px;">
                            <strong>Reminder:</strong> We'll send you a reminder email 24 hours before your lesson.
                        </p>
                    </div>
                    
                    <hr style="border: none; border-top: 1px solid #E5E7EB; margin: 30px 0;">
                    
                    <p style="color: #6B7280; font-size: 14px;">
                        Need to make changes? You can manage your booking from your dashboard. 
                        Please note our cancellation policy.
                    </p>
                    
                    <p style="color: #6B7280; font-size: 14px;">
                        If you have any questions, please don't hesitate to contact us.
                    </p>
                    
                    <p style="color: #4B5563; margin-top: 30px;">
                        Best regards,<br>
                        The {BRAND_NAME} Team
                    </p>
                </div>
                
                <div style="text-align: center; padding: 20px; color: #6B7280; font-size: 12px;">
                    <p>© {datetime.now().year} {BRAND_NAME}. All rights reserved.</p>
                    <p>
                        <a href="{self.frontend_url}/help" style="color: #4F46E5; text-decoration: none;">Help Center</a> |
                        <a href="{self.frontend_url}/terms" style="color: #4F46E5; text-decoration: none;">Terms of Service</a> |
                        <a href="{self.frontend_url}/privacy" style="color: #4F46E5; text-decoration: none;">Privacy Policy</a>
                    </p>
                </div>
            </body>
            </html>
            """
            
            # Send email
            response = self.email_service.send_email(
                to_email=booking.student.email,
                subject=subject,
                html_content=html_content
            )
            
            logger.info(f"Student confirmation email sent for booking {booking.id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send student confirmation email: {str(e)}")
            return False
    
    async def _send_instructor_booking_notification(self, booking: Booking) -> bool:
        """Send new booking notification to instructor."""
        try:
            subject = f"New Booking: {booking.service_name} with {booking.student.full_name}"
            
            # Format booking time
            booking_datetime = datetime.combine(booking.booking_date, booking.start_time)
            formatted_date = booking_datetime.strftime("%A, %B %d, %Y")
            formatted_time = booking_datetime.strftime("%-I:%M %p")
            
            # Build email content
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
            </head>
            <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
                <div style="background-color: #10B981; padding: 30px; text-align: center; border-radius: 10px 10px 0 0;">
                    <h1 style="color: white; margin: 0; font-size: 28px;">{BRAND_NAME}</h1>
                    <p style="color: #D1FAE5; margin: 10px 0 0 0;">You have a new booking!</p>
                </div>
                
                <div style="background-color: #f8f9fa; padding: 40px; border-radius: 0 0 10px 10px;">
                    <h2 style="color: #1F2937; margin-bottom: 20px;">New Booking Alert</h2>
                    
                    <p style="color: #4B5563; font-size: 16px;">Hi {booking.instructor.full_name},</p>
                    
                    <p style="color: #4B5563;">You have a new confirmed booking!</p>
                    
                    <div style="background-color: white; padding: 25px; border-radius: 8px; margin: 25px 0; border: 1px solid #E5E7EB;">
                        <h3 style="color: #1F2937; margin-top: 0; margin-bottom: 15px;">Booking Details</h3>
                        
                        <table style="width: 100%; border-collapse: collapse;">
                            <tr>
                                <td style="padding: 8px 0; color: #6B7280;">Student:</td>
                                <td style="padding: 8px 0; color: #1F2937; font-weight: 600;">{booking.student.full_name}</td>
                            </tr>
                            <tr>
                                <td style="padding: 8px 0; color: #6B7280;">Service:</td>
                                <td style="padding: 8px 0; color: #1F2937; font-weight: 600;">{booking.service_name}</td>
                            </tr>
                            <tr>
                                <td style="padding: 8px 0; color: #6B7280;">Date:</td>
                                <td style="padding: 8px 0; color: #1F2937; font-weight: 600;">{formatted_date}</td>
                            </tr>
                            <tr>
                                <td style="padding: 8px 0; color: #6B7280;">Time:</td>
                                <td style="padding: 8px 0; color: #1F2937; font-weight: 600;">{formatted_time}</td>
                            </tr>
                            <tr>
                                <td style="padding: 8px 0; color: #6B7280;">Duration:</td>
                                <td style="padding: 8px 0; color: #1F2937; font-weight: 600;">{booking.duration_minutes} minutes</td>
                            </tr>
                            <tr>
                                <td style="padding: 8px 0; color: #6B7280;">Location:</td>
                                <td style="padding: 8px 0; color: #1F2937; font-weight: 600;">{booking.location_type_display}</td>
                            </tr>
                            {f'''<tr>
                                <td style="padding: 8px 0; color: #6B7280;">Student Note:</td>
                                <td style="padding: 8px 0; color: #1F2937; font-style: italic;">"{booking.student_note}"</td>
                            </tr>''' if booking.student_note else ''}
                            <tr>
                                <td style="padding: 8px 0; color: #6B7280;">Earnings:</td>
                                <td style="padding: 8px 0; color: #1F2937; font-weight: 600;">${booking.total_price:.2f}</td>
                            </tr>
                        </table>
                    </div>
                    
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{self.frontend_url}/dashboard/instructor/bookings/{booking.id}" 
                           style="background-color: #10B981; color: white; padding: 12px 30px; text-decoration: none; border-radius: 6px; display: inline-block; font-weight: 600;">
                            View Full Details
                        </a>
                    </div>
                    
                    <hr style="border: none; border-top: 1px solid #E5E7EB; margin: 30px 0;">
                    
                    <p style="color: #6B7280; font-size: 14px;">
                        This booking has been automatically confirmed. The student has been notified.
                    </p>
                    
                    <p style="color: #4B5563; margin-top: 30px;">
                        Happy teaching!<br>
                        The {BRAND_NAME} Team
                    </p>
                </div>
                
                <div style="text-align: center; padding: 20px; color: #6B7280; font-size: 12px;">
                    <p>© {datetime.now().year} {BRAND_NAME}. All rights reserved.</p>
                </div>
            </body>
            </html>
            """
            
            # Send email
            response = self.email_service.send_email(
                to_email=booking.instructor.email,
                subject=subject,
                html_content=html_content
            )
            
            logger.info(f"Instructor notification email sent for booking {booking.id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send instructor notification email: {str(e)}")
            return False
    
    async def _send_student_cancellation_notification(
        self, 
        booking: Booking, 
        reason: Optional[str], 
        cancelled_by: str
    ) -> bool:
        """Send cancellation notification to student when instructor cancels."""
        try:
            subject = f"Booking Cancelled: {booking.service_name}"
            
            booking_datetime = datetime.combine(booking.booking_date, booking.start_time)
            formatted_date = booking_datetime.strftime("%A, %B %d, %Y")
            formatted_time = booking_datetime.strftime("%-I:%M %p")
            
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
                <div style="background-color: #EF4444; padding: 30px; text-align: center; border-radius: 10px 10px 0 0;">
                    <h1 style="color: white; margin: 0;">{BRAND_NAME}</h1>
                    <p style="color: #FEE2E2; margin: 10px 0 0 0;">Booking Cancelled</p>
                </div>
                
                <div style="background-color: #f8f9fa; padding: 40px; border-radius: 0 0 10px 10px;">
                    <h2 style="color: #1F2937;">Booking Cancellation</h2>
                    
                    <p>Hi {booking.student.full_name},</p>
                    
                    <p>We're sorry to inform you that your upcoming lesson has been cancelled by the instructor.</p>
                    
                    <div style="background-color: white; padding: 20px; border-radius: 8px; margin: 20px 0; border: 1px solid #E5E7EB;">
                        <h3 style="color: #1F2937; margin-top: 0;">Cancelled Booking Details</h3>
                        <p><strong>Service:</strong> {booking.service_name}</p>
                        <p><strong>Instructor:</strong> {booking.instructor.full_name}</p>
                        <p><strong>Date:</strong> {formatted_date}</p>
                        <p><strong>Time:</strong> {formatted_time}</p>
                        {f'<p><strong>Reason:</strong> {reason}</p>' if reason else ''}
                    </div>
                    
                    <div style="background-color: #DBEAFE; padding: 15px; border-radius: 6px; margin: 20px 0;">
                        <p style="color: #1E40AF; margin: 0;">
                            <strong>What's Next?</strong> You can search for another instructor and book a new lesson at your convenience.
                        </p>
                    </div>
                    
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{self.frontend_url}/instructors" 
                           style="background-color: #4F46E5; color: white; padding: 12px 30px; text-decoration: none; border-radius: 6px; display: inline-block;">
                            Find Another Instructor
                        </a>
                    </div>
                    
                    <p style="color: #6B7280; font-size: 14px;">
                        We apologize for any inconvenience. If you have questions, please contact our support team.
                    </p>
                    
                    <p style="margin-top: 30px;">
                        Best regards,<br>
                        The {BRAND_NAME} Team
                    </p>
                </div>
            </body>
            </html>
            """
            
            response = self.email_service.send_email(
                to_email=booking.student.email,
                subject=subject,
                html_content=html_content
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to send student cancellation notification: {str(e)}")
            return False
    
    async def _send_instructor_cancellation_notification(
        self, 
        booking: Booking, 
        reason: Optional[str], 
        cancelled_by: str
    ) -> bool:
        """Send cancellation notification to instructor when student cancels."""
        try:
            subject = f"Booking Cancelled: {booking.service_name}"
            
            booking_datetime = datetime.combine(booking.booking_date, booking.start_time)
            formatted_date = booking_datetime.strftime("%A, %B %d, %Y")
            formatted_time = booking_datetime.strftime("%-I:%M %p")
            
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
                <div style="background-color: #F59E0B; padding: 30px; text-align: center; border-radius: 10px 10px 0 0;">
                    <h1 style="color: white; margin: 0;">{BRAND_NAME}</h1>
                    <p style="color: #FEF3C7; margin: 10px 0 0 0;">Booking Cancelled</p>
                </div>
                
                <div style="background-color: #f8f9fa; padding: 40px; border-radius: 0 0 10px 10px;">
                    <h2 style="color: #1F2937;">Booking Cancellation</h2>
                    
                    <p>Hi {booking.instructor.full_name},</p>
                    
                    <p>Your upcoming lesson has been cancelled by the student.</p>
                    
                    <div style="background-color: white; padding: 20px; border-radius: 8px; margin: 20px 0; border: 1px solid #E5E7EB;">
                        <h3 style="color: #1F2937; margin-top: 0;">Cancelled Booking Details</h3>
                        <p><strong>Student:</strong> {booking.student.full_name}</p>
                        <p><strong>Service:</strong> {booking.service_name}</p>
                        <p><strong>Date:</strong> {formatted_date}</p>
                        <p><strong>Time:</strong> {formatted_time}</p>
                        {f'<p><strong>Reason:</strong> {reason}</p>' if reason else ''}
                    </div>
                    
                    <div style="background-color: #FEF3C7; padding: 15px; border-radius: 6px;">
                        <p style="color: #92400E; margin: 0;">
                            Your time slot has been automatically freed up and is now available for other students to book.
                        </p>
                    </div>
                    
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{self.frontend_url}/dashboard/instructor" 
                           style="background-color: #4F46E5; color: white; padding: 12px 30px; text-decoration: none; border-radius: 6px; display: inline-block;">
                            View Dashboard
                        </a>
                    </div>
                    
                    <p style="margin-top: 30px;">
                        Best regards,<br>
                        The {BRAND_NAME} Team
                    </p>
                </div>
            </body>
            </html>
            """
            
            response = self.email_service.send_email(
                to_email=booking.instructor.email,
                subject=subject,
                html_content=html_content
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to send instructor cancellation notification: {str(e)}")
            return False
    
    async def _send_student_cancellation_confirmation(self, booking: Booking) -> bool:
        """Send cancellation confirmation to student after they cancel."""
        try:
            subject = f"Cancellation Confirmed: {booking.service_name}"
            
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
                <div style="background-color: #6B7280; padding: 30px; text-align: center; border-radius: 10px 10px 0 0;">
                    <h1 style="color: white; margin: 0;">{BRAND_NAME}</h1>
                </div>
                
                <div style="background-color: #f8f9fa; padding: 40px; border-radius: 0 0 10px 10px;">
                    <h2 style="color: #1F2937;">Cancellation Confirmed</h2>
                    
                    <p>Hi {booking.student.full_name},</p>
                    
                    <p>Your booking has been successfully cancelled.</p>
                    
                    <p>We hope to see you again soon!</p>
                    
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{self.frontend_url}/instructors" 
                           style="background-color: #4F46E5; color: white; padding: 12px 30px; text-decoration: none; border-radius: 6px; display: inline-block;">
                            Book Another Lesson
                        </a>
                    </div>
                    
                    <p style="margin-top: 30px;">
                        Best regards,<br>
                        The {BRAND_NAME} Team
                    </p>
                </div>
            </body>
            </html>
            """
            
            response = self.email_service.send_email(
                to_email=booking.student.email,
                subject=subject,
                html_content=html_content
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to send cancellation confirmation: {str(e)}")
            return False
    
    async def _send_instructor_cancellation_confirmation(self, booking: Booking) -> bool:
        """Send cancellation confirmation to instructor after they cancel."""
        # Similar to student confirmation
        return await self._send_student_cancellation_confirmation(booking)
    
    async def _send_student_reminder(self, booking: Booking) -> bool:
        """Send 24-hour reminder to student."""
        try:
            subject = f"Reminder: {booking.service_name} Tomorrow"
            
            booking_datetime = datetime.combine(booking.booking_date, booking.start_time)
            formatted_time = booking_datetime.strftime("%-I:%M %p")
            
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
                <div style="background-color: #3B82F6; padding: 30px; text-align: center; border-radius: 10px 10px 0 0;">
                    <h1 style="color: white; margin: 0;">{BRAND_NAME}</h1>
                    <p style="color: #DBEAFE; margin: 10px 0 0 0;">Lesson Reminder</p>
                </div>
                
                <div style="background-color: #f8f9fa; padding: 40px; border-radius: 0 0 10px 10px;">
                    <h2 style="color: #1F2937;">Your lesson is tomorrow!</h2>
                    
                    <p>Hi {booking.student.full_name},</p>
                    
                    <p>This is a friendly reminder about your upcoming lesson.</p>
                    
                    <div style="background-color: white; padding: 20px; border-radius: 8px; margin: 20px 0; border: 1px solid #E5E7EB;">
                        <h3 style="color: #1F2937; margin-top: 0;">Tomorrow's Lesson</h3>
                        <p><strong>Service:</strong> {booking.service_name}</p>
                        <p><strong>Instructor:</strong> {booking.instructor.full_name}</p>
                        <p><strong>Time:</strong> {formatted_time}</p>
                        <p><strong>Duration:</strong> {booking.duration_minutes} minutes</p>
                        <p><strong>Location:</strong> {booking.location_type_display}</p>
                        {f'<p><strong>Address:</strong> {booking.meeting_location}</p>' if booking.meeting_location else ''}
                    </div>
                    
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{self.frontend_url}/dashboard/student/bookings" 
                           style="background-color: #4F46E5; color: white; padding: 12px 30px; text-decoration: none; border-radius: 6px; display: inline-block;">
                            View Booking Details
                        </a>
                    </div>
                    
                    <p style="color: #6B7280; font-size: 14px;">
                        Need to cancel? Please do so at least 2 hours before your lesson.
                    </p>
                    
                    <p style="margin-top: 30px;">
                        See you tomorrow!<br>
                        The {BRAND_NAME} Team
                    </p>
                </div>
            </body>
            </html>
            """
            
            response = self.email_service.send_email(
                to_email=booking.student.email,
                subject=subject,
                html_content=html_content
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to send student reminder: {str(e)}")
            return False
    
    async def _send_instructor_reminder(self, booking: Booking) -> bool:
        """Send 24-hour reminder to instructor."""
        try:
            subject = f"Reminder: {booking.service_name} Tomorrow"
            
            booking_datetime = datetime.combine(booking.booking_date, booking.start_time)
            formatted_time = booking_datetime.strftime("%-I:%M %p")
            
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
                <div style="background-color: #8B5CF6; padding: 30px; text-align: center; border-radius: 10px 10px 0 0;">
                    <h1 style="color: white; margin: 0;">{BRAND_NAME}</h1>
                    <p style="color: #EDE9FE; margin: 10px 0 0 0;">Teaching Reminder</p>
                </div>
                
                <div style="background-color: #f8f9fa; padding: 40px; border-radius: 0 0 10px 10px;">
                    <h2 style="color: #1F2937;">You have a lesson tomorrow!</h2>
                    
                    <p>Hi {booking.instructor.full_name},</p>
                    
                    <p>This is a reminder about your upcoming lesson.</p>
                    
                    <div style="background-color: white; padding: 20px; border-radius: 8px; margin: 20px 0; border: 1px solid #E5E7EB;">
                        <h3 style="color: #1F2937; margin-top: 0;">Tomorrow's Lesson</h3>
                        <p><strong>Student:</strong> {booking.student.full_name}</p>
                        <p><strong>Service:</strong> {booking.service_name}</p>
                        <p><strong>Time:</strong> {formatted_time}</p>
                        <p><strong>Duration:</strong> {booking.duration_minutes} minutes</p>
                        <p><strong>Location:</strong> {booking.location_type_display}</p>
                        {f'<p><strong>Student Note:</strong> "{booking.student_note}"</p>' if booking.student_note else ''}
                    </div>
                    
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{self.frontend_url}/dashboard/instructor/bookings/{booking.id}" 
                           style="background-color: #8B5CF6; color: white; padding: 12px 30px; text-decoration: none; border-radius: 6px; display: inline-block;">
                            View Full Details
                        </a>
                    </div>
                    
                    <p style="margin-top: 30px;">
                        Have a great lesson!<br>
                        The {BRAND_NAME} Team
                    </p>
                </div>
            </body>
            </html>
            """
            
            response = self.email_service.send_email(
                to_email=booking.instructor.email,
                subject=subject,
                html_content=html_content
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to send instructor reminder: {str(e)}")
            return False


# Create a singleton instance for easy import
notification_service = NotificationService()