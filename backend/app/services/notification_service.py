# backend/app/services/notification_service_refactored.py
"""
Notification Service for InstaInstru Platform (Template-based version)

Handles all platform notifications using Jinja2 templates instead of
embedded HTML strings. This refactored version extracts all HTML to
external templates for better maintainability.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from ..core.config import settings
from ..models.booking import Booking
from ..models.user import User
from ..services.email import email_service
from ..services.template_service import template_service

logger = logging.getLogger(__name__)


class NotificationService:
    """
    Central notification service for the platform using Jinja2 templates.

    All HTML has been extracted to templates for maintainability and
    to prevent f-string bugs.
    """

    def __init__(self, db: Session = None):
        """
        Initialize the notification service.

        Args:
            db: Optional database session for loading additional data
        """
        self.db = db
        self.email_service = email_service
        self.template_service = template_service
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
        self, booking: Booking, cancelled_by: User, reason: Optional[str] = None
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
                success = await self._send_instructor_cancellation_notification(booking, reason, "student")
                # Also send confirmation to student
                student_success = await self._send_student_cancellation_confirmation(booking)
                return success and student_success
            else:
                # Instructor cancelled - notify student
                success = await self._send_student_cancellation_notification(booking, reason, "instructor")
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

            bookings = (
                self.db.query(Booking).filter(Booking.booking_date == tomorrow, Booking.status == "CONFIRMED").all()
            )

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
        """Send booking confirmation email to student using template."""
        try:
            subject = f"Booking Confirmed: {booking.service_name} with {booking.instructor.full_name}"

            # Format booking time
            booking_datetime = datetime.combine(booking.booking_date, booking.start_time)
            formatted_date = booking_datetime.strftime("%A, %B %d, %Y")
            formatted_time = booking_datetime.strftime("%-I:%M %p")

            # Prepare template context
            context = {
                "booking": booking,
                "formatted_date": formatted_date,
                "formatted_time": formatted_time,
                "subject": subject,
            }

            # Render template
            html_content = self.template_service.render_template("email/booking/confirmation_student.html", context)

            # Send email
            response = self.email_service.send_email(
                to_email=booking.student.email,
                subject=subject,
                html_content=html_content,
            )

            logger.info(f"Student confirmation email sent for booking {booking.id}")
            return True

        except Exception as e:
            logger.error(f"Failed to send student confirmation email: {str(e)}")
            return False

    async def _send_instructor_booking_notification(self, booking: Booking) -> bool:
        """Send new booking notification to instructor using template."""
        try:
            subject = f"New Booking: {booking.service_name} with {booking.student.full_name}"

            # Format booking time
            booking_datetime = datetime.combine(booking.booking_date, booking.start_time)
            formatted_date = booking_datetime.strftime("%A, %B %d, %Y")
            formatted_time = booking_datetime.strftime("%-I:%M %p")

            # Prepare template context with custom colors for instructor
            context = {
                "booking": booking,
                "formatted_date": formatted_date,
                "formatted_time": formatted_time,
                "subject": subject,
                "header_bg_color": "#10B981",  # Green for instructor
                "header_text_color": "#D1FAE5",  # Light green
            }

            # Render template
            html_content = self.template_service.render_template("email/booking/confirmation_instructor.html", context)

            # Send email
            response = self.email_service.send_email(
                to_email=booking.instructor.email,
                subject=subject,
                html_content=html_content,
            )

            logger.info(f"Instructor notification email sent for booking {booking.id}")
            return True

        except Exception as e:
            logger.error(f"Failed to send instructor notification email: {str(e)}")
            return False

    async def _send_student_cancellation_notification(
        self, booking: Booking, reason: Optional[str], cancelled_by: str
    ) -> bool:
        """Send cancellation notification to student when instructor cancels."""
        try:
            subject = f"Booking Cancelled: {booking.service_name}"

            booking_datetime = datetime.combine(booking.booking_date, booking.start_time)
            formatted_date = booking_datetime.strftime("%A, %B %d, %Y")
            formatted_time = booking_datetime.strftime("%-I:%M %p")

            # Prepare template context with red colors for cancellation
            context = {
                "booking": booking,
                "formatted_date": formatted_date,
                "formatted_time": formatted_time,
                "reason": reason,
                "cancelled_by": cancelled_by,
                "subject": subject,
                "header_bg_color": "#EF4444",  # Red for cancellation
                "header_text_color": "#FEE2E2",  # Light red
            }

            # Render template
            html_content = self.template_service.render_template("email/booking/cancellation_student.html", context)

            response = self.email_service.send_email(
                to_email=booking.student.email,
                subject=subject,
                html_content=html_content,
            )

            return True

        except Exception as e:
            logger.error(f"Failed to send student cancellation notification: {str(e)}")
            return False

    async def _send_instructor_cancellation_notification(
        self, booking: Booking, reason: Optional[str], cancelled_by: str
    ) -> bool:
        """Send cancellation notification to instructor when student cancels."""
        try:
            subject = f"Booking Cancelled: {booking.service_name}"

            booking_datetime = datetime.combine(booking.booking_date, booking.start_time)
            formatted_date = booking_datetime.strftime("%A, %B %d, %Y")
            formatted_time = booking_datetime.strftime("%-I:%M %p")

            # Prepare template context
            context = {
                "booking": booking,
                "formatted_date": formatted_date,
                "formatted_time": formatted_time,
                "reason": reason,
                "cancelled_by": cancelled_by,
                "subject": subject,
            }

            # Render template
            html_content = self.template_service.render_template("email/booking/cancellation_instructor.html", context)

            response = self.email_service.send_email(
                to_email=booking.instructor.email,
                subject=subject,
                html_content=html_content,
            )

            return True

        except Exception as e:
            logger.error(f"Failed to send instructor cancellation notification: {str(e)}")
            return False

    async def _send_student_cancellation_confirmation(self, booking: Booking) -> bool:
        """Send cancellation confirmation to student after they cancel."""
        try:
            subject = f"Cancellation Confirmed: {booking.service_name}"

            # Format booking time for the confirmation
            booking_datetime = datetime.combine(booking.booking_date, booking.start_time)
            formatted_date = booking_datetime.strftime("%A, %B %d, %Y")
            formatted_time = booking_datetime.strftime("%-I:%M %p")

            # Prepare template context
            context = {
                "booking": booking,
                "formatted_date": formatted_date,
                "formatted_time": formatted_time,
                "subject": subject,
            }

            # Render template
            html_content = self.template_service.render_template(
                "email/booking/cancellation_confirmation_student.html", context
            )

            response = self.email_service.send_email(
                to_email=booking.student.email,
                subject=subject,
                html_content=html_content,
            )

            return True

        except Exception as e:
            logger.error(f"Failed to send cancellation confirmation: {str(e)}")
            return False

    async def _send_instructor_cancellation_confirmation(self, booking: Booking) -> bool:
        """Send cancellation confirmation to instructor after they cancel."""
        try:
            subject = f"Cancellation Confirmed: {booking.service_name}"

            # Format booking time for the confirmation
            booking_datetime = datetime.combine(booking.booking_date, booking.start_time)
            formatted_date = booking_datetime.strftime("%A, %B %d, %Y")
            formatted_time = booking_datetime.strftime("%-I:%M %p")

            # Prepare template context
            context = {
                "booking": booking,
                "formatted_date": formatted_date,
                "formatted_time": formatted_time,
                "subject": subject,
            }

            # Render template
            html_content = self.template_service.render_template(
                "email/booking/cancellation_confirmation_instructor.html", context
            )

            response = self.email_service.send_email(
                to_email=booking.instructor.email,
                subject=subject,
                html_content=html_content,
            )

            return True

        except Exception as e:
            logger.error(f"Failed to send instructor cancellation confirmation: {str(e)}")
            return False

    async def _send_student_reminder(self, booking: Booking) -> bool:
        """Send 24-hour reminder to student."""
        try:
            subject = f"Reminder: {booking.service_name} Tomorrow"

            booking_datetime = datetime.combine(booking.booking_date, booking.start_time)
            formatted_time = booking_datetime.strftime("%-I:%M %p")

            # Prepare template context
            context = {
                "booking": booking,
                "formatted_time": formatted_time,
                "subject": subject,
            }

            # Render template
            html_content = self.template_service.render_template("email/booking/reminder_student.html", context)

            response = self.email_service.send_email(
                to_email=booking.student.email,
                subject=subject,
                html_content=html_content,
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

            # Prepare template context
            context = {
                "booking": booking,
                "formatted_time": formatted_time,
                "subject": subject,
            }

            # Render template
            html_content = self.template_service.render_template("email/booking/reminder_instructor.html", context)

            response = self.email_service.send_email(
                to_email=booking.instructor.email,
                subject=subject,
                html_content=html_content,
            )

            return True

        except Exception as e:
            logger.error(f"Failed to send instructor reminder: {str(e)}")
            return False


# Create a singleton instance for easy import
notification_service = NotificationService()
