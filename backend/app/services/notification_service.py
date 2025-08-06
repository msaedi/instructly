# backend/app/services/notification_service.py
"""
Notification Service for InstaInstru Platform (Refactored)

Handles all platform notifications using Jinja2 templates with proper
error handling, metrics, and resilience patterns.

Changes from original:
- Inherits from BaseService for consistency
- Added performance metrics with @measure_operation
- Improved exception handling with specific exceptions
- Added retry logic for email sending
- Split long methods for maintainability
- Added comprehensive type hints
- Uses dependency injection for TemplateService (no singleton)
"""

import asyncio
import logging
from datetime import datetime, timedelta
from functools import wraps
from typing import Any, Callable, List, Optional

from jinja2.exceptions import TemplateNotFound
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.exceptions import ServiceException
from ..models.booking import Booking
from ..models.user import User
from ..services.base import BaseService
from ..services.email import EmailService
from ..services.template_service import TemplateService

logger = logging.getLogger(__name__)


def retry(max_attempts: int = 3, backoff_seconds: float = 1.0) -> Callable:
    """
    Decorator for retrying failed operations with exponential backoff.

    Args:
        max_attempts: Maximum number of retry attempts
        backoff_seconds: Initial backoff time in seconds

    Returns:
        Decorated function with retry logic
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            last_exception = None

            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_attempts - 1:
                        wait_time = backoff_seconds * (2**attempt)
                        logger.warning(
                            f"Attempt {attempt + 1}/{max_attempts} failed for {func.__name__}: {str(e)}. "
                            f"Retrying in {wait_time}s..."
                        )
                        await asyncio.sleep(wait_time)
                    else:
                        logger.error(f"All {max_attempts} attempts failed for {func.__name__}: {str(e)}")

            raise last_exception

        return wrapper

    return decorator


class NotificationService(BaseService):
    """
    Central notification service for the platform using Jinja2 templates.

    Inherits from BaseService for consistent architecture, metrics collection,
    and standardized error handling. Uses dependency injection for TemplateService.
    """

    def __init__(
        self,
        db: Optional[Session] = None,
        cache=None,
        template_service: Optional[TemplateService] = None,
        email_service: Optional[EmailService] = None,
    ):
        """
        Initialize the notification service.

        Args:
            db: Optional database session for loading additional data
            cache: Optional cache service (not used but kept for consistency)
            template_service: Optional TemplateService instance (will create if not provided)
            email_service: Optional EmailService instance (will create if not provided)
        """
        # Initialize BaseService with a dummy session if none provided
        # This maintains compatibility with the original interface
        if db is None:
            from app.database import SessionLocal

            db = SessionLocal()
            self._owns_db = True
        else:
            self._owns_db = False

        super().__init__(db, cache)

        # Use dependency injection for EmailService
        if email_service is None:
            # Create our own instance if not provided
            self.email_service = EmailService(db, cache)
            self._owns_email_service = True
        else:
            self.email_service = email_service
            self._owns_email_service = False

        # Use dependency injection for TemplateService
        if template_service is None:
            # Create our own instance if not provided
            self.template_service = TemplateService(db, cache)
            self._owns_template_service = True
        else:
            self.template_service = template_service
            self._owns_template_service = False

        self.frontend_url = settings.frontend_url

    def __del__(self):
        """Clean up the database session if we created it."""
        if hasattr(self, "_owns_db") and self._owns_db and hasattr(self, "db"):
            self.db.close()

    @BaseService.measure_operation("send_booking_confirmation")
    async def send_booking_confirmation(self, booking: Booking) -> bool:
        """
        Send booking confirmation emails to both student and instructor.

        Args:
            booking: The booking object with all related data loaded

        Returns:
            bool: True if all emails sent successfully, False otherwise

        Raises:
            ServiceException: If template rendering fails
        """
        if not booking:
            self.logger.error("Cannot send booking confirmation: booking is None")
            return False

        try:
            self.logger.info(f"Sending booking confirmation emails for booking {booking.id}")

            # Send to student - catch exceptions after retries
            try:
                student_success = await self._send_student_booking_confirmation(booking)
            except TemplateNotFound as e:
                self.logger.error(f"Template error in booking confirmation: {str(e)}")
                raise ServiceException(f"Email template error: {str(e)}")
            except Exception as e:
                self.logger.error(f"Failed to send student confirmation after retries: {str(e)}")
                student_success = False

            # Send to instructor - catch exceptions after retries
            try:
                instructor_success = await self._send_instructor_booking_notification(booking)
            except TemplateNotFound as e:
                self.logger.error(f"Template error in booking confirmation: {str(e)}")
                raise ServiceException(f"Email template error: {str(e)}")
            except Exception as e:
                self.logger.error(f"Failed to send instructor notification after retries: {str(e)}")
                instructor_success = False

            if student_success and instructor_success:
                self.logger.info(f"All booking confirmation emails sent for booking {booking.id}")
                return True
            else:
                self.logger.warning(f"Some booking confirmation emails failed for booking {booking.id}")
                return False

        except ServiceException:
            raise  # Re-raise ServiceException
        except Exception as e:
            self.logger.error(f"Unexpected error sending booking confirmation: {str(e)}")
            raise

    @BaseService.measure_operation("send_cancellation_notification")
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
            bool: True if all emails sent successfully, False otherwise

        Raises:
            ServiceException: If template rendering fails
        """
        if not booking:
            self.logger.error("Cannot send cancellation notification: booking is None")
            return False

        if not cancelled_by:
            self.logger.error("Cannot send cancellation notification: cancelled_by is None")
            return False

        try:
            self.logger.info(f"Sending cancellation emails for booking {booking.id}")

            # Determine who cancelled
            is_student_cancellation = cancelled_by.id == booking.student_id

            # Send appropriate emails
            if is_student_cancellation:
                # Student cancelled - notify instructor
                try:
                    success = await self._send_instructor_cancellation_notification(booking, reason, "student")
                except TemplateNotFound as e:
                    raise ServiceException(f"Email template error: {str(e)}")
                except Exception as e:
                    self.logger.error(f"Failed to send instructor cancellation after retries: {str(e)}")
                    success = False

                # Also send confirmation to student
                try:
                    student_success = await self._send_student_cancellation_confirmation(booking)
                except TemplateNotFound as e:
                    raise ServiceException(f"Email template error: {str(e)}")
                except Exception as e:
                    self.logger.error(f"Failed to send student confirmation after retries: {str(e)}")
                    student_success = False

                return success and student_success
            else:
                # Instructor cancelled - notify student
                try:
                    success = await self._send_student_cancellation_notification(booking, reason, "instructor")
                except TemplateNotFound as e:
                    raise ServiceException(f"Email template error: {str(e)}")
                except Exception as e:
                    self.logger.error(f"Failed to send student cancellation after retries: {str(e)}")
                    success = False

                # Also send confirmation to instructor
                try:
                    instructor_success = await self._send_instructor_cancellation_confirmation(booking)
                except TemplateNotFound as e:
                    raise ServiceException(f"Email template error: {str(e)}")
                except Exception as e:
                    self.logger.error(f"Failed to send instructor confirmation after retries: {str(e)}")
                    instructor_success = False

                return success and instructor_success

        except ServiceException:
            raise
        except Exception as e:
            self.logger.error(f"Unexpected error sending cancellation emails: {str(e)}")
            raise

    @BaseService.measure_operation("send_reminder_emails")
    async def send_reminder_emails(self) -> int:
        """
        Send 24-hour reminder emails for upcoming bookings.

        This should be called by a scheduled job.

        Returns:
            int: Number of reminders sent

        Raises:
            ServiceException: If database query fails
        """
        if not self.db:
            self.logger.error("Database session required for sending reminders")
            raise ServiceException("Database session required for sending reminders")

        try:
            # Get tomorrow's bookings
            bookings = await self._get_tomorrows_bookings()

            if not bookings:
                self.logger.info("No bookings found for tomorrow")
                return 0

            # Send reminders
            sent_count = await self._send_booking_reminders(bookings)

            self.logger.info(f"Sent {sent_count} reminder emails for {len(bookings)} bookings")
            return sent_count

        except Exception as e:
            self.logger.error(f"Error in send_reminder_emails: {str(e)}")
            raise ServiceException(f"Failed to send reminder emails: {str(e)}")

    # Private helper methods

    async def _get_tomorrows_bookings(self) -> List[Booking]:
        """
        Get all confirmed bookings for tomorrow.

        Returns:
            List of bookings scheduled for tomorrow
        """
        tomorrow = datetime.now().date() + timedelta(days=1)

        # repo-pattern-migrate: TODO: Migrate to repository pattern
        bookings = self.db.query(Booking).filter(Booking.booking_date == tomorrow, Booking.status == "CONFIRMED").all()

        self.logger.info(f"Found {len(bookings)} bookings for tomorrow")
        return bookings

    async def _send_booking_reminders(self, bookings: List[Booking]) -> int:
        """
        Send reminder emails for a list of bookings.

        Args:
            bookings: List of bookings to send reminders for

        Returns:
            Number of successfully sent reminders
        """
        sent_count = 0

        for booking in bookings:
            student_sent = False
            instructor_sent = False

            # Try to send student reminder
            try:
                student_sent = await self._send_student_reminder(booking)
            except Exception as e:
                self.logger.error(f"Failed to send student reminder for booking {booking.id} after retries: {str(e)}")

            # Try to send instructor reminder
            try:
                instructor_sent = await self._send_instructor_reminder(booking)
            except Exception as e:
                self.logger.error(
                    f"Failed to send instructor reminder for booking {booking.id} after retries: {str(e)}"
                )

            if student_sent and instructor_sent:
                sent_count += 1

        return sent_count

    # Email sending methods with retry logic

    @retry(max_attempts=3, backoff_seconds=1.0)
    async def _send_student_booking_confirmation(self, booking: Booking) -> bool:
        """Send booking confirmation email to student using template."""
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

        # Send email - let exceptions propagate for retry
        response = self.email_service.send_email(
            to_email=booking.student.email,
            subject=subject,
            html_content=html_content,
        )

        self.logger.info(f"Student confirmation email sent for booking {booking.id}")
        return True

    @retry(max_attempts=3, backoff_seconds=1.0)
    async def _send_instructor_booking_notification(self, booking: Booking) -> bool:
        """Send new booking notification to instructor using template."""
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

        # Send email - let exceptions propagate for retry
        response = self.email_service.send_email(
            to_email=booking.instructor.email,
            subject=subject,
            html_content=html_content,
        )

        self.logger.info(f"Instructor notification email sent for booking {booking.id}")
        return True

    @retry(max_attempts=3, backoff_seconds=1.0)
    async def _send_student_cancellation_notification(
        self, booking: Booking, reason: Optional[str], cancelled_by: str
    ) -> bool:
        """Send cancellation notification to student when instructor cancels."""
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

    @retry(max_attempts=3, backoff_seconds=1.0)
    async def _send_instructor_cancellation_notification(
        self, booking: Booking, reason: Optional[str], cancelled_by: str
    ) -> bool:
        """Send cancellation notification to instructor when student cancels."""
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

    @retry(max_attempts=3, backoff_seconds=1.0)
    async def _send_student_cancellation_confirmation(self, booking: Booking) -> bool:
        """Send cancellation confirmation to student after they cancel."""
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

    @retry(max_attempts=3, backoff_seconds=1.0)
    async def _send_instructor_cancellation_confirmation(self, booking: Booking) -> bool:
        """Send cancellation confirmation to instructor after they cancel."""
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

    @retry(max_attempts=3, backoff_seconds=1.0)
    async def _send_student_reminder(self, booking: Booking) -> bool:
        """Send 24-hour reminder to student."""
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

        # Send email - let exceptions propagate for retry
        response = self.email_service.send_email(
            to_email=booking.student.email,
            subject=subject,
            html_content=html_content,
        )

        return True

    @retry(max_attempts=3, backoff_seconds=1.0)
    async def _send_instructor_reminder(self, booking: Booking) -> bool:
        """Send 24-hour reminder to instructor."""
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

        # Send email - let exceptions propagate for retry
        response = self.email_service.send_email(
            to_email=booking.instructor.email,
            subject=subject,
            html_content=html_content,
        )

        return True
