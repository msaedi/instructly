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
from datetime import datetime, timedelta, timezone
from functools import wraps
import logging
import time
from typing import Any, Callable, Coroutine, Dict, List, Optional, ParamSpec, Sequence, TypeVar

from jinja2.exceptions import TemplateNotFound
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.exceptions import ServiceException
from ..models.booking import Booking
from ..models.notification import Notification
from ..models.user import User
from ..repositories.notification_repository import NotificationRepository
from ..repositories.user_repository import UserRepository
from ..services.base import BaseService
from ..services.cache_service import CacheService
from ..services.email import EmailService
from ..services.messaging import publish_to_user
from ..services.notification_preference_service import NotificationPreferenceService
from ..services.push_notification_service import PushNotificationService
from ..services.sms_service import SMSService
from ..services.sms_templates import SMSTemplate, render_sms
from ..services.template_registry import TemplateRegistry
from ..services.template_service import TemplateService
from ..services.timezone_service import TimezoneService
from .notification_templates import NotificationTemplate, render_notification

logger = logging.getLogger(__name__)

P = ParamSpec("P")
R = TypeVar("R")


def retry(
    max_attempts: int = 3, backoff_seconds: float = 1.0
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """
    Decorator for retrying failed operations with exponential backoff.

    Args:
        max_attempts: Maximum number of retry attempts
        backoff_seconds: Initial backoff time in seconds

    Returns:
        Decorated function with retry logic
    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            last_exception: Exception | None = None

            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_attempts - 1:
                        wait_time = backoff_seconds * (2**attempt)
                        logger.warning(
                            f"Attempt {attempt + 1}/{max_attempts} failed for {func.__name__}: {str(e)}. "
                            f"Retrying in {wait_time}s..."
                        )
                        time.sleep(wait_time)
                    else:
                        logger.error(
                            f"All {max_attempts} attempts failed for {func.__name__}: {str(e)}"
                        )

            if last_exception is not None:
                raise last_exception
            raise RuntimeError("Retry failed without capturing exception")

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
        cache: Any | None = None,
        template_service: Optional[TemplateService] = None,
        email_service: Optional[EmailService] = None,
        notification_repository: Optional[NotificationRepository] = None,
        push_service: Optional[PushNotificationService] = None,
        preference_service: Optional[NotificationPreferenceService] = None,
        sms_service: Optional[SMSService] = None,
    ) -> None:
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

        self.notification_repository = notification_repository or NotificationRepository(db)
        self.user_repository = UserRepository(db)
        self.push_notification_service = push_service or PushNotificationService(
            db, self.notification_repository
        )
        self.preference_service = preference_service or NotificationPreferenceService(
            db, self.notification_repository
        )
        sms_cache = cache if isinstance(cache, CacheService) else None
        self.sms_service = sms_service or SMSService(sms_cache)

        self.frontend_url = settings.frontend_url

    def __del__(self) -> None:
        """Clean up the database session if we created it."""
        if hasattr(self, "_owns_db") and self._owns_db and hasattr(self, "db"):
            self.db.close()

    def _resolve_lesson_timezone(self, booking: Booking) -> str:
        lesson_tz = getattr(booking, "lesson_timezone", None) or getattr(
            booking, "instructor_tz_at_booking", None
        )
        instructor = getattr(booking, "instructor", None)
        instructor_user = getattr(instructor, "user", None) if instructor else None
        lesson_tz = lesson_tz or getattr(instructor_user, "timezone", None)
        return lesson_tz or TimezoneService.DEFAULT_TIMEZONE

    def _get_booking_start_utc(self, booking: Booking) -> datetime:
        booking_start_utc = getattr(booking, "booking_start_utc", None)
        if isinstance(booking_start_utc, datetime):
            return booking_start_utc

        lesson_tz = self._resolve_lesson_timezone(booking)
        try:
            return TimezoneService.local_to_utc(
                booking.booking_date,
                booking.start_time,
                lesson_tz,
            )
        except ValueError as exc:
            logger.warning(
                "Failed to convert booking %s start to UTC (%s); falling back to UTC combine.",
                getattr(booking, "id", None),
                exc,
            )
            return datetime.combine(  # tz-pattern-ok: fallback for invalid legacy time
                booking.booking_date,
                booking.start_time,
                tzinfo=timezone.utc,  # tz-pattern-ok: legacy fallback
            )

    def _get_booking_local_datetime(self, booking: Booking) -> datetime:
        lesson_tz = self._resolve_lesson_timezone(booking)
        start_utc = self._get_booking_start_utc(booking)
        return TimezoneService.utc_to_local(start_utc, lesson_tz)

    @BaseService.measure_operation("send_booking_confirmation")
    def send_booking_confirmation(self, booking: Booking) -> bool:
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
                student_success = self._send_student_booking_confirmation(booking)
            except TemplateNotFound as e:
                self.logger.error(f"Template error in booking confirmation: {str(e)}")
                raise ServiceException(f"Email template error: {str(e)}")
            except Exception as e:
                self.logger.error(f"Failed to send student confirmation after retries: {str(e)}")
                student_success = False

            # Send to instructor - catch exceptions after retries
            try:
                instructor_success = self._send_instructor_booking_notification(booking)
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
                self.logger.warning(
                    f"Some booking confirmation emails failed for booking {booking.id}"
                )
                return False

        except ServiceException:
            raise  # Re-raise ServiceException
        except Exception as e:
            self.logger.error(f"Unexpected error sending booking confirmation: {str(e)}")
            raise

    @BaseService.measure_operation("send_cancellation_notification")
    def send_cancellation_notification(
        self, booking: Booking, cancelled_by: User | str | None, reason: Optional[str] = None
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

        if cancelled_by is None:
            self.logger.error("Cannot send cancellation notification: cancelled_by is None")
            return False

        try:
            self.logger.info(f"Sending cancellation emails for booking {booking.id}")

            # Determine who cancelled
            cancelled_by_role = None
            is_student_cancellation = False
            if isinstance(cancelled_by, User):
                is_student_cancellation = cancelled_by.id == booking.student_id
                cancelled_by_role = "student" if is_student_cancellation else "instructor"
            elif isinstance(cancelled_by, str):
                cancelled_by_role = cancelled_by
                is_student_cancellation = cancelled_by_role == "student"
            else:
                cancelled_by_role = "student"
                is_student_cancellation = True

            # Send appropriate emails
            if is_student_cancellation:
                # Student cancelled - notify instructor
                try:
                    success = self._send_instructor_cancellation_notification(
                        booking, reason, cancelled_by_role
                    )
                except TemplateNotFound as e:
                    raise ServiceException(f"Email template error: {str(e)}")
                except Exception as e:
                    self.logger.error(
                        f"Failed to send instructor cancellation after retries: {str(e)}"
                    )
                    success = False

                # Also send confirmation to student
                try:
                    student_success = self._send_student_cancellation_confirmation(booking)
                except TemplateNotFound as e:
                    raise ServiceException(f"Email template error: {str(e)}")
                except Exception as e:
                    self.logger.error(
                        f"Failed to send student confirmation after retries: {str(e)}"
                    )
                    student_success = False

                return success and student_success
            else:
                # Instructor cancelled - notify student
                try:
                    success = self._send_student_cancellation_notification(
                        booking, reason, cancelled_by_role
                    )
                except TemplateNotFound as e:
                    raise ServiceException(f"Email template error: {str(e)}")
                except Exception as e:
                    self.logger.error(
                        f"Failed to send student cancellation after retries: {str(e)}"
                    )
                    success = False

                # Also send confirmation to instructor
                try:
                    instructor_success = self._send_instructor_cancellation_confirmation(booking)
                except TemplateNotFound as e:
                    raise ServiceException(f"Email template error: {str(e)}")
                except Exception as e:
                    self.logger.error(
                        f"Failed to send instructor confirmation after retries: {str(e)}"
                    )
                    instructor_success = False

                return success and instructor_success

        except ServiceException:
            raise
        except Exception as e:
            self.logger.error(f"Unexpected error sending cancellation emails: {str(e)}")
            raise

    @BaseService.measure_operation("send_reminder_emails")
    def send_reminder_emails(self) -> int:
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
            bookings = self._get_tomorrows_bookings()

            if not bookings:
                self.logger.info("No bookings found for tomorrow")
                return 0

            # Send reminders
            sent_count = self._send_booking_reminders(bookings)

            self.logger.info(f"Sent {sent_count} reminder emails for {len(bookings)} bookings")
            return sent_count

        except Exception as e:
            self.logger.error(f"Error in send_reminder_emails: {str(e)}")
            raise ServiceException(f"Failed to send reminder emails: {str(e)}")

    # Private helper methods

    def _get_tomorrows_bookings(self) -> List[Booking]:
        """
        Get all confirmed bookings for tomorrow.

        Returns:
            List of bookings scheduled for tomorrow
        """
        # Get bookings for a range of dates to handle timezone differences
        from datetime import timezone as tz

        # Use UTC as reference and get a 3-day window to cover all timezones
        utc_now = datetime.now(tz.utc).date()
        date_range = [
            utc_now,  # Today in UTC (could be tomorrow in some timezones)
            utc_now + timedelta(days=1),  # Tomorrow in UTC
            utc_now + timedelta(days=2),  # Day after (could be tomorrow in other timezones)
        ]

        # Use BookingRepository method with date range for efficiency
        from ..repositories.factory import RepositoryFactory

        booking_repository = RepositoryFactory.create_booking_repository(self.db)
        # Get all bookings in the date range with a single query
        start_date = date_range[0]
        end_date = date_range[-1]
        all_bookings = booking_repository.get_bookings_by_date_range_and_status(
            start_date, end_date, "CONFIRMED"
        )

        self.logger.info(f"Found {len(all_bookings)} bookings for tomorrow")
        return all_bookings

    def _send_booking_reminders(self, bookings: List[Booking]) -> int:
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
                student_sent = self._send_student_reminder(booking)
            except Exception as e:
                self.logger.error(
                    f"Failed to send student reminder for booking {booking.id} after retries: {str(e)}"
                )

            # Try to send instructor reminder
            try:
                instructor_sent = self._send_instructor_reminder(booking)
            except Exception as e:
                self.logger.error(
                    f"Failed to send instructor reminder for booking {booking.id} after retries: {str(e)}"
                )

            if student_sent and instructor_sent:
                sent_count += 1

        return sent_count

    @BaseService.measure_operation("send_booking_reminder")
    def send_booking_reminder(self, booking: Booking, reminder_type: str = "24h") -> bool:
        """
        Send reminder emails for a single booking.

        Args:
            booking: Booking to remind
            reminder_type: Reminder type label (e.g., '24h', '1h')
        """
        try:
            student_sent = self._send_student_reminder(booking)
            instructor_sent = self._send_instructor_reminder(booking)
            if student_sent and instructor_sent:
                self.logger.info(
                    "Sent %s reminders for booking %s", reminder_type, getattr(booking, "id", None)
                )
            return student_sent and instructor_sent
        except Exception as exc:
            self.logger.error(
                "Failed to send %s reminder for booking %s: %s",
                reminder_type,
                getattr(booking, "id", None),
                exc,
            )
            return False

    # Email sending methods with retry logic

    @retry(max_attempts=3, backoff_seconds=1.0)
    def _send_student_booking_confirmation(self, booking: Booking) -> bool:
        """Send booking confirmation email to student using template."""
        student_id = getattr(booking, "student_id", None)
        if student_id and not self._should_send_email(
            student_id, "lesson_updates", "booking_confirmation_student"
        ):
            return True

        subject = f"Booking Confirmed: {booking.service_name} with {booking.instructor.first_name}"

        # Format booking time in lesson timezone
        local_dt = self._get_booking_local_datetime(booking)
        formatted_date = local_dt.strftime("%A, %B %d, %Y")
        formatted_time = local_dt.strftime("%-I:%M %p")

        # Prepare template context
        context = {
            "booking": booking,
            "formatted_date": formatted_date,
            "formatted_time": formatted_time,
            "subject": subject,
        }

        # Render template
        html_content = self.template_service.render_template(
            TemplateRegistry.BOOKING_CONFIRMATION_STUDENT, context
        )

        # Send email - let exceptions propagate for retry
        _response = self.email_service.send_email(
            to_email=booking.student.email,
            subject=subject,
            html_content=html_content,
            template=TemplateRegistry.BOOKING_CONFIRMATION_STUDENT,
        )

        self.logger.info(f"Student confirmation email sent for booking {booking.id}")
        return True

    @BaseService.measure_operation("send_booking_cancelled_payment_failed")
    def send_booking_cancelled_payment_failed(self, booking: Booking) -> bool:
        """
        Notify student and instructor that a booking was cancelled due to repeated payment authorization failures.

        This is called by background payment tasks at T-6hr when we abandon auth and cancel the booking.
        Uses a dedicated template if present; otherwise falls back to a simple rendered string.
        """
        try:
            student_id = getattr(booking, "student_id", None)
            instructor_id = getattr(booking, "instructor_id", None)

            send_student = True
            send_instructor = True

            if student_id and not self._should_send_email(
                student_id, "lesson_updates", "booking_cancelled_payment_failed_student"
            ):
                send_student = False

            if instructor_id and not self._should_send_email(
                instructor_id, "lesson_updates", "booking_cancelled_payment_failed_instructor"
            ):
                send_instructor = False

            if not send_student and not send_instructor:
                return True

            subject = "Booking Cancelled: Payment Authorization Failed"

            context = {
                "booking": booking,
                "subject": subject,
                "update_payment_url": f"{self.frontend_url}/student/payments",
            }

            html_student = None
            html_instructor = None

            # Prefer specific templates if available
            try:
                if self.template_service.template_exists(
                    "email/booking/cancelled_payment_failed_student.html"
                ):
                    html_student = self.template_service.render_template(
                        "email/booking/cancelled_payment_failed_student.html", context
                    )
            except Exception:
                html_student = None

            try:
                if self.template_service.template_exists(
                    "email/booking/cancelled_payment_failed_instructor.html"
                ):
                    html_instructor = self.template_service.render_template(
                        "email/booking/cancelled_payment_failed_instructor.html", context
                    )
            except Exception:
                html_instructor = None

            # Fallbacks using existing cancellation templates if custom ones aren't available
            if not html_student:
                fallback_student = (
                    "<p>Your upcoming lesson was cancelled because we couldn't authorize the payment after multiple attempts.</p>"
                    "<p>Please update your payment method to avoid future cancellations.</p>"
                    f"<p><a href='{self.frontend_url}/student/payments'>Update payment method</a></p>"
                )
                html_student = self.template_service.render_string(fallback_student, context)

            if not html_instructor:
                fallback_instructor = "<p>The upcoming lesson was cancelled because the student's payment could not be authorized after multiple attempts.</p>"
                html_instructor = self.template_service.render_string(fallback_instructor, context)

            # Send emails
            if (
                send_student
                and getattr(booking, "student", None)
                and getattr(booking.student, "email", None)
            ):
                self.email_service.send_email(
                    to_email=booking.student.email,
                    subject=subject,
                    html_content=html_student,
                )

            if (
                send_instructor
                and getattr(booking, "instructor", None)
                and getattr(booking.instructor, "email", None)
            ):
                self.email_service.send_email(
                    to_email=booking.instructor.email,
                    subject=subject,
                    html_content=html_instructor,
                )

            self.logger.info(
                f"Sent payment-failure cancellation notifications for booking {getattr(booking, 'id', 'unknown')}"
            )
            return True
        except Exception as e:
            self.logger.error(
                f"Failed to send payment-failure cancellation notifications for booking {getattr(booking, 'id', 'unknown')}: {e}"
            )
            return False

    @BaseService.measure_operation("send_final_payment_warning")
    def send_final_payment_warning(self, booking: Booking, hours_until_lesson: float) -> bool:
        """
        Send an urgent T-24 authorization failure email asking the student to update their card.

        This is a synchronous helper used by background tasks. Uses a dedicated template if present,
        otherwise falls back to a simple rendered string to avoid hard failures in test/dev.
        """
        try:
            student_id = getattr(booking, "student_id", None)
            if student_id and not self._should_send_email(
                student_id, "lesson_updates", "final_payment_warning"
            ):
                return True

            subject = "Action required: Update your payment method for your upcoming lesson"

            # Try a dedicated template first
            template_name = "email/payment/t24_update_card.html"
            context = {
                "booking": booking,
                "hours_until_lesson": round(hours_until_lesson, 1),
                "update_payment_url": f"{self.frontend_url}/student/payments",  # generic payments page
            }

            html_content = None
            try:
                # Prefer a specific template if available
                if self.template_service.template_exists(template_name):
                    html_content = self.template_service.render_template(template_name, context)
            except Exception:
                html_content = None

            # Fallback minimal content
            if not html_content:
                local_dt = self._get_booking_local_datetime(booking)
                formatted_date = local_dt.strftime("%B %d, %Y")
                formatted_time = local_dt.strftime("%-I:%M %p")
                fallback = (
                    "<p>We couldn't authorize your payment for your upcoming lesson. "
                    "Please update your card on file to avoid cancellation.</p>"
                    f"<p>Lesson: {booking.service_name} on {formatted_date} at {formatted_time}</p>"
                    f"<p><a href='{self.frontend_url}/student/payments'>Update payment method</a></p>"
                )
                html_content = self.template_service.render_string(fallback, context)

            self.email_service.send_email(
                to_email=booking.student.email,
                subject=subject,
                html_content=html_content,
            )
            self.logger.info(f"Sent T-24 payment warning to student for booking {booking.id}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to send T-24 payment warning for booking {booking.id}: {e}")
            return False

    @retry(max_attempts=3, backoff_seconds=1.0)
    def _send_instructor_booking_notification(self, booking: Booking) -> bool:
        """Send new booking notification to instructor using template."""
        instructor_id = getattr(booking, "instructor_id", None)
        if instructor_id and not self._should_send_email(
            instructor_id, "lesson_updates", "booking_confirmation_instructor"
        ):
            return True

        subject = f"New Booking: {booking.service_name} with {booking.student.first_name}"

        # Format booking time in lesson timezone
        local_dt = self._get_booking_local_datetime(booking)
        formatted_date = local_dt.strftime("%A, %B %d, %Y")
        formatted_time = local_dt.strftime("%-I:%M %p")

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
        html_content = self.template_service.render_template(
            TemplateRegistry.BOOKING_CONFIRMATION_INSTRUCTOR, context
        )

        # Send email - let exceptions propagate for retry
        _response = self.email_service.send_email(
            to_email=booking.instructor.email,
            subject=subject,
            html_content=html_content,
            template=TemplateRegistry.BOOKING_CONFIRMATION_INSTRUCTOR,
        )

        self.logger.info(f"Instructor notification email sent for booking {booking.id}")
        return True

    @retry(max_attempts=3, backoff_seconds=1.0)
    def _send_student_cancellation_notification(
        self, booking: Booking, reason: Optional[str], cancelled_by: str
    ) -> bool:
        """Send cancellation notification to student when instructor cancels."""
        student_id = getattr(booking, "student_id", None)
        if student_id and not self._should_send_email(
            student_id, "lesson_updates", "booking_cancellation_student"
        ):
            return True

        subject = f"Booking Cancelled: {booking.service_name}"

        local_dt = self._get_booking_local_datetime(booking)
        formatted_date = local_dt.strftime("%A, %B %d, %Y")
        formatted_time = local_dt.strftime("%-I:%M %p")

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
        html_content = self.template_service.render_template(
            TemplateRegistry.BOOKING_CANCELLATION_STUDENT, context
        )

        _response = self.email_service.send_email(
            to_email=booking.student.email,
            subject=subject,
            html_content=html_content,
            template=TemplateRegistry.BOOKING_CANCELLATION_STUDENT,
        )

        return True

    @retry(max_attempts=3, backoff_seconds=1.0)
    def _send_instructor_cancellation_notification(
        self, booking: Booking, reason: Optional[str], cancelled_by: str
    ) -> bool:
        """Send cancellation notification to instructor when student cancels."""
        instructor_id = getattr(booking, "instructor_id", None)
        if instructor_id and not self._should_send_email(
            instructor_id, "lesson_updates", "booking_cancellation_instructor"
        ):
            return True

        subject = f"Booking Cancelled: {booking.service_name}"

        local_dt = self._get_booking_local_datetime(booking)
        formatted_date = local_dt.strftime("%A, %B %d, %Y")
        formatted_time = local_dt.strftime("%-I:%M %p")

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
        html_content = self.template_service.render_template(
            TemplateRegistry.BOOKING_CANCELLATION_INSTRUCTOR, context
        )

        _response = self.email_service.send_email(
            to_email=booking.instructor.email,
            subject=subject,
            html_content=html_content,
            template=TemplateRegistry.BOOKING_CANCELLATION_INSTRUCTOR,
        )

        return True

    @retry(max_attempts=3, backoff_seconds=1.0)
    def _send_student_cancellation_confirmation(self, booking: Booking) -> bool:
        """Send cancellation confirmation to student after they cancel."""
        student_id = getattr(booking, "student_id", None)
        if student_id and not self._should_send_email(
            student_id, "lesson_updates", "booking_cancellation_confirmation_student"
        ):
            return True

        subject = f"Cancellation Confirmed: {booking.service_name}"

        # Format booking time for the confirmation
        local_dt = self._get_booking_local_datetime(booking)
        formatted_date = local_dt.strftime("%A, %B %d, %Y")
        formatted_time = local_dt.strftime("%-I:%M %p")

        # Prepare template context
        context = {
            "booking": booking,
            "formatted_date": formatted_date,
            "formatted_time": formatted_time,
            "subject": subject,
        }

        # Render template
        html_content = self.template_service.render_template(
            TemplateRegistry.BOOKING_CANCELLATION_CONFIRMATION_STUDENT, context
        )

        _response = self.email_service.send_email(
            to_email=booking.student.email,
            subject=subject,
            html_content=html_content,
            template=TemplateRegistry.BOOKING_CANCELLATION_CONFIRMATION_STUDENT,
        )

        return True

    @retry(max_attempts=3, backoff_seconds=1.0)
    def _send_instructor_cancellation_confirmation(self, booking: Booking) -> bool:
        """Send cancellation confirmation to instructor after they cancel."""
        instructor_id = getattr(booking, "instructor_id", None)
        if instructor_id and not self._should_send_email(
            instructor_id, "lesson_updates", "booking_cancellation_confirmation_instructor"
        ):
            return True

        subject = f"Cancellation Confirmed: {booking.service_name}"

        # Format booking time for the confirmation
        local_dt = self._get_booking_local_datetime(booking)
        formatted_date = local_dt.strftime("%A, %B %d, %Y")
        formatted_time = local_dt.strftime("%-I:%M %p")

        # Prepare template context
        context = {
            "booking": booking,
            "formatted_date": formatted_date,
            "formatted_time": formatted_time,
            "subject": subject,
        }

        # Render template
        html_content = self.template_service.render_template(
            TemplateRegistry.BOOKING_CANCELLATION_CONFIRMATION_INSTRUCTOR, context
        )

        _response = self.email_service.send_email(
            to_email=booking.instructor.email,
            subject=subject,
            html_content=html_content,
            template=TemplateRegistry.BOOKING_CANCELLATION_CONFIRMATION_INSTRUCTOR,
        )

        return True

    @retry(max_attempts=3, backoff_seconds=1.0)
    def _send_student_reminder(self, booking: Booking) -> bool:
        """Send 24-hour reminder to student."""
        student_id = getattr(booking, "student_id", None)
        if student_id and not self._should_send_email(
            student_id, "lesson_updates", "booking_reminder_student"
        ):
            return True

        subject = f"Reminder: {booking.service_name} Tomorrow"

        local_dt = self._get_booking_local_datetime(booking)
        formatted_time = local_dt.strftime("%-I:%M %p")

        # Prepare template context
        context = {
            "booking": booking,
            "formatted_time": formatted_time,
            "subject": subject,
        }

        # Render template
        html_content = self.template_service.render_template(
            TemplateRegistry.BOOKING_REMINDER_STUDENT, context
        )

        # Send email - let exceptions propagate for retry
        _response = self.email_service.send_email(
            to_email=booking.student.email,
            subject=subject,
            html_content=html_content,
            template=TemplateRegistry.BOOKING_REMINDER_STUDENT,
        )

        return True

    @retry(max_attempts=3, backoff_seconds=1.0)
    def _send_instructor_reminder(self, booking: Booking) -> bool:
        """Send 24-hour reminder to instructor."""
        instructor_id = getattr(booking, "instructor_id", None)
        if instructor_id and not self._should_send_email(
            instructor_id, "lesson_updates", "booking_reminder_instructor"
        ):
            return True

        subject = f"Reminder: {booking.service_name} Tomorrow"

        local_dt = self._get_booking_local_datetime(booking)
        formatted_time = local_dt.strftime("%-I:%M %p")

        # Prepare template context
        context = {
            "booking": booking,
            "formatted_time": formatted_time,
            "subject": subject,
        }

        # Render template
        html_content = self.template_service.render_template(
            TemplateRegistry.BOOKING_REMINDER_INSTRUCTOR, context
        )

        # Send email - let exceptions propagate for retry
        _response = self.email_service.send_email(
            to_email=booking.instructor.email,
            subject=subject,
            html_content=html_content,
            template=TemplateRegistry.BOOKING_REMINDER_INSTRUCTOR,
        )

        return True

    @BaseService.measure_operation("send_message_notification")
    def send_message_notification(
        self, recipient_id: str, booking: Booking, sender_id: str, message_content: str
    ) -> bool:
        """
        Send email notification for a new chat message.

        Args:
            recipient_id: ID of the user to notify
            booking: The booking object for context
            sender_id: ID of the message sender
            message_content: Content of the message

        Returns:
            bool: True if email sent successfully, False otherwise
        """
        try:
            if not self._should_send_email(recipient_id, "messages", "booking_new_message"):
                return True

            # Get recipient and sender users using repository pattern
            from ..repositories.user_repository import UserRepository

            user_repo = UserRepository(self.db)

            recipient = user_repo.get_by_id(recipient_id)
            sender = user_repo.get_by_id(sender_id)

            if not recipient or not sender:
                self.logger.error("Cannot send message notification: users not found")
                return False

            # Determine if sender is instructor or student
            sender_role = "instructor" if sender_id == booking.instructor_id else "student"

            # Create subject line
            subject = f"New message from your {sender_role} - {booking.service_name}"

            # Prepare template context
            local_dt = self._get_booking_local_datetime(booking)
            context = {
                "recipient_name": recipient.first_name,
                "sender_name": sender.first_name,
                "sender_role": sender_role,
                "booking_date": local_dt.strftime("%B %d, %Y"),
                "booking_time": local_dt.strftime("%-I:%M %p"),
                "service_name": booking.service_name,
                "message_preview": message_content[:200] + "..."
                if len(message_content) > 200
                else message_content,
                "booking_id": booking.id,
                "settings": settings,  # Include settings for frontend URL
            }

            # Render template using the template service
            html_content = self.template_service.render_template(
                TemplateRegistry.BOOKING_NEW_MESSAGE, context
            )

            # Send email
            _response = self.email_service.send_email(
                to_email=recipient.email,
                subject=subject,
                html_content=html_content,
                template=TemplateRegistry.BOOKING_NEW_MESSAGE,
            )

            if _response:
                self.logger.info(f"Message notification sent to {recipient.email}")
                return True
            else:
                self.logger.warning(f"Failed to send message notification to {recipient.email}")
                return False

        except Exception as e:
            self.logger.error(f"Error sending message notification: {str(e)}")
            return False

    @BaseService.measure_operation("send_badge_awarded_email")
    def send_badge_awarded_email(self, user: User, badge_name: str) -> bool:
        try:
            user_id = getattr(user, "id", None)
            if not user_id:
                return False
            if not self._should_send_email(user_id, "promotional", "badge_awarded"):
                return False

            subject = f"You earned the {badge_name} badge!"
            html_content = (
                f"<p>Congratulations {user.first_name or user.email},</p>"
                f"<p>You just unlocked the <strong>{badge_name}</strong> badge. Keep up the great work!</p>"
            )
            text_content = f"Congratulations {user.first_name or user.email}, you just unlocked the {badge_name} badge!"
            self.email_service.send_email(
                to_email=user.email,
                subject=subject,
                html_content=html_content,
                text_content=text_content,
            )
            return True
        except Exception as exc:
            self.logger.error("Failed to send badge award email: %s", exc)
            return False

    @BaseService.measure_operation("send_badge_digest_email")
    def send_badge_digest_email(self, user: User, items: Sequence[Dict[str, Any]]) -> bool:
        try:
            user_id = getattr(user, "id", None)
            if not user_id:
                return False
            if not self._should_send_email(user_id, "promotional", "badge_digest"):
                return False

            subject = "You're close to unlocking new badges"
            if not items:
                return False
            list_items = "".join(
                f"<li><strong>{item.get('name')}</strong>: {int(item.get('percent', 0))}% complete, "
                f"{item.get('remaining')} remaining</li>"
                for item in items
            )
            html_content = (
                f"<p>Hi {user.first_name or user.email},</p>"
                "<p>You're making great progress. Here are the badges you're closest to earning:</p>"
                f"<ul>{list_items}</ul>"
                "<p>Finish a lesson this week to keep the streak going!</p>"
            )
            text_content = "\n".join(
                f"- {item.get('name')}: {int(item.get('percent', 0))}% complete, {item.get('remaining')} remaining"
                for item in items
            )
            self.email_service.send_email(
                to_email=user.email,
                subject=subject,
                html_content=html_content,
                text_content=text_content,
            )
            return True
        except Exception as exc:
            self.logger.error("Failed to send badge digest email: %s", exc)
            return False

    def _should_send_push(self, user_id: str, category: str) -> bool:
        return self.preference_service.is_enabled(user_id, category, "push")

    def _serialize_notification(self, notification: Notification) -> Dict[str, Any]:
        created_at = (
            notification.created_at.isoformat() if notification.created_at is not None else None
        )
        return {
            "id": notification.id,
            "title": notification.title,
            "body": notification.body,
            "category": notification.category,
            "type": notification.type,
            "data": notification.data,
            "read_at": notification.read_at.isoformat() if notification.read_at else None,
            "created_at": created_at,
        }

    def _should_send_email(self, user_id: str, category: str, context: str) -> bool:
        try:
            enabled = self.preference_service.is_enabled(user_id, category, "email")
        except Exception as exc:
            self.logger.warning(
                "Email preference lookup failed; sending anyway (user_id=%s context=%s): %s",
                user_id,
                context,
                exc,
            )
            return True

        if not enabled:
            self.logger.info(
                "Email skipped due to preferences (user_id=%s category=%s context=%s)",
                user_id,
                category,
                context,
            )

        return enabled

    def _should_send_sms(self, user_id: str, category: str, context: str) -> bool:
        try:
            enabled = self.preference_service.is_enabled(user_id, category, "sms")
        except Exception as exc:
            self.logger.warning(
                "SMS preference lookup failed; skipping (user_id=%s context=%s): %s",
                user_id,
                context,
                exc,
            )
            return False

        if not enabled:
            self.logger.info(
                "SMS skipped due to preferences (user_id=%s category=%s context=%s)",
                user_id,
                category,
                context,
            )

        return enabled

    def _send_notification_email(
        self, user_id: str, template: NotificationTemplate, **template_kwargs: Any
    ) -> bool:
        if template.email_template is None:
            return False

        user_repo = UserRepository(self.db)
        user = user_repo.get_by_id(user_id)
        if not user or not getattr(user, "email", None):
            return False

        subject = template.title
        if template.email_subject_template:
            try:
                subject = template.email_subject_template.format(**template_kwargs)
            except Exception as exc:
                self.logger.warning(
                    "Failed to format email subject for %s (%s): %s",
                    template.type,
                    user_id,
                    exc,
                )

        context: Dict[str, Any] = {
            "user_name": user.first_name or user.email,
            "subject": subject,
            **template_kwargs,
        }

        try:
            html_content = self.template_service.render_template(template.email_template, context)
        except Exception as exc:
            self.logger.warning(
                "Failed to render email template for %s (%s): %s",
                template.type,
                user_id,
                exc,
            )
            return False

        try:
            self.email_service.send_email(
                to_email=user.email,
                subject=subject,
                html_content=html_content,
                template=template.email_template,
            )
            return True
        except Exception as exc:
            self.logger.warning(
                "Failed to send notification email for %s (%s): %s",
                template.type,
                user_id,
                exc,
            )
            return False

    def _run_async_task(
        self, coro_func: Callable[[], Coroutine[Any, Any, None]], error_context: str
    ) -> None:
        async def _with_error_handling() -> None:
            try:
                await coro_func()
            except Exception as exc:  # pragma: no cover - best effort logging
                self.logger.warning("Failed %s: %s", error_context, exc)

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_with_error_handling())
        except RuntimeError:
            try:
                asyncio.run(_with_error_handling())
            except Exception as exc:  # pragma: no cover - best effort logging
                self.logger.warning("Failed %s: %s", error_context, exc)

    @BaseService.measure_operation("notify_user")
    async def notify_user(
        self,
        user_id: str,
        template: NotificationTemplate,
        send_push: bool = True,
        send_email: bool = True,
        send_sms: bool = False,
        sms_template: SMSTemplate | None = None,
        **template_kwargs: Any,
    ) -> Notification:
        rendered = render_notification(template, **template_kwargs)
        notification = await self.create_notification(
            user_id=user_id,
            category=rendered["category"],
            notification_type=rendered["type"],
            title=rendered["title"],
            body=rendered["body"],
            data=rendered["data"],
            send_push=send_push,
        )

        if send_email and template.email_template is not None:
            should_send = await asyncio.to_thread(
                self._should_send_email,
                user_id,
                template.category,
                f"notify_user:{template.type}",
            )
            if should_send:
                await asyncio.to_thread(
                    self._send_notification_email, user_id, template, **template_kwargs
                )

        if send_sms and sms_template is not None and self.sms_service:
            should_send_sms = await asyncio.to_thread(
                self._should_send_sms,
                user_id,
                sms_template.category,
                f"notify_user:{template.type}:sms",
            )
            if should_send_sms:
                try:
                    message = render_sms(sms_template, **template_kwargs)
                except Exception as exc:
                    self.logger.warning(
                        "Failed to render SMS template for %s (%s): %s",
                        template.type,
                        user_id,
                        exc,
                    )
                else:
                    try:
                        await self.sms_service.send_to_user(
                            user_id=user_id,
                            message=message,
                            user_repository=self.user_repository,
                        )
                    except Exception as exc:
                        self.logger.warning(
                            "Failed to send SMS for %s (%s): %s",
                            template.type,
                            user_id,
                            exc,
                        )

        return notification

    @BaseService.measure_operation("notify_user_best_effort")
    def notify_user_best_effort(
        self,
        user_id: str,
        template: NotificationTemplate,
        send_push: bool = True,
        send_email: bool = True,
        send_sms: bool = False,
        sms_template: SMSTemplate | None = None,
        **template_kwargs: Any,
    ) -> None:
        async def _notify() -> None:
            await self.notify_user(
                user_id=user_id,
                template=template,
                send_push=send_push,
                send_email=send_email,
                send_sms=send_sms,
                sms_template=sms_template,
                **template_kwargs,
            )

        self._run_async_task(_notify, f"sending notification {template.type} to {user_id}")

    @BaseService.measure_operation("create_in_app_notification")
    async def create_notification(
        self,
        user_id: str,
        category: str,
        notification_type: str,
        title: str,
        body: str | None,
        data: Dict[str, Any] | None = None,
        send_push: bool = True,
    ) -> Notification:
        """
        Create an in-app notification, optionally send push, and broadcast SSE update.
        """

        def _create_notification_sync() -> tuple[Notification, bool]:
            push_enabled_local = False
            with self.transaction():
                notification_local = self.notification_repository.create_notification(
                    user_id=user_id,
                    category=category,
                    type=notification_type,
                    title=title,
                    body=body,
                    data=data,
                )
                if send_push:
                    push_enabled_local = self._should_send_push(user_id, category)
            return notification_local, push_enabled_local

        notification, push_enabled = await asyncio.to_thread(_create_notification_sync)

        if send_push and push_enabled:
            push_url = None
            if data and isinstance(data, dict):
                url_value = data.get("url")
                if isinstance(url_value, str):
                    push_url = url_value
            push_body = body or title
            try:
                self.push_notification_service.send_push_notification(
                    user_id=user_id,
                    title=title,
                    body=push_body,
                    url=push_url,
                    data=data,
                )
            except Exception as exc:
                self.logger.error("Push notification send failed: %s", exc)

        unread_count = await asyncio.to_thread(
            self.notification_repository.get_unread_count, user_id
        )
        await publish_to_user(
            user_id,
            {
                "type": "notification_update",
                "payload": {
                    "unread_count": unread_count,
                    "latest": self._serialize_notification(notification),
                },
            },
        )
        return notification

    @BaseService.measure_operation("get_notifications")
    def get_notifications(
        self,
        user_id: str,
        limit: int = 20,
        offset: int = 0,
        unread_only: bool = False,
    ) -> List[Notification]:
        """Get paginated notifications for a user."""
        return self.notification_repository.get_user_notifications(
            user_id=user_id,
            limit=limit,
            offset=offset,
            unread_only=unread_only,
        )

    @BaseService.measure_operation("get_notification_count")
    def get_notification_count(self, user_id: str, unread_only: bool = False) -> int:
        """Get notification count for a user."""
        return self.notification_repository.get_user_notification_count(
            user_id=user_id, unread_only=unread_only
        )

    @BaseService.measure_operation("mark_notification_read")
    def mark_as_read(self, user_id: str, notification_id: str) -> bool:
        """Mark a single notification as read."""
        with self.transaction():
            return self.notification_repository.mark_as_read_for_user(user_id, notification_id)

    @BaseService.measure_operation("mark_all_notifications_read")
    def mark_all_as_read(self, user_id: str) -> int:
        """Mark all notifications as read for a user."""
        with self.transaction():
            return self.notification_repository.mark_all_as_read(user_id)

    @BaseService.measure_operation("get_notification_unread_count")
    def get_unread_count(self, user_id: str) -> int:
        """Get unread notification count for a user."""
        return self.notification_repository.get_unread_count(user_id)

    @BaseService.measure_operation("delete_notification")
    def delete_notification(self, user_id: str, notification_id: str) -> bool:
        """Delete a notification."""
        with self.transaction():
            return self.notification_repository.delete_notification(user_id, notification_id)

    @BaseService.measure_operation("delete_all_notifications")
    def delete_all_notifications(self, user_id: str) -> int:
        """Delete all notifications for a user."""
        with self.transaction():
            return self.notification_repository.delete_all_for_user(user_id)
