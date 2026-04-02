from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from jinja2.exceptions import TemplateNotFound

from ...core.exceptions import ServiceException
from ...models.booking import Booking
from ...repositories.user_repository import UserRepository
from ...utils.privacy import format_private_display_name
from ..base import BaseService
from ..email import EmailService
from ..template_registry import TemplateRegistry
from ..template_service import TemplateService
from .common_mixin import retry
from .mixin_base import NotificationMixinBase


class NotificationBookingConfirmationMixin(NotificationMixinBase):
    """Booking confirmation emails — student and instructor."""

    if TYPE_CHECKING:
        logger: logging.Logger
        email_service: EmailService
        template_service: TemplateService
        user_repository: UserRepository

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
            self.logger.info("Sending booking confirmation emails for booking %s", booking.id)

            try:
                student_success = self._send_student_booking_confirmation(booking)
            except TemplateNotFound as exc:
                self.logger.error("Template error in booking confirmation: %s", str(exc))
                raise ServiceException(f"Email template error: {str(exc)}")
            except Exception as exc:
                self.logger.error("Failed to send student confirmation after retries: %s", str(exc))
                student_success = False

            try:
                instructor_success = self._send_instructor_booking_notification(booking)
            except TemplateNotFound as exc:
                self.logger.error("Template error in booking confirmation: %s", str(exc))
                raise ServiceException(f"Email template error: {str(exc)}")
            except Exception as exc:
                self.logger.error(
                    "Failed to send instructor notification after retries: %s", str(exc)
                )
                instructor_success = False

            if student_success and instructor_success:
                self.logger.info("All booking confirmation emails sent for booking %s", booking.id)
                return True

            self.logger.warning(
                "Some booking confirmation emails failed for booking %s", booking.id
            )
            return False
        except ServiceException:
            raise
        except Exception as exc:
            self.logger.error("Unexpected error sending booking confirmation: %s", str(exc))
            raise

    @retry(max_attempts=3, backoff_seconds=1.0)
    def _send_student_booking_confirmation(self, booking: Booking) -> bool:
        """Send booking confirmation email to student using template."""
        student_id = getattr(booking, "student_id", None)
        if student_id and not self._should_send_email(
            student_id, "lesson_updates", "booking_confirmation_student"
        ):
            return True

        subject = f"Booking Confirmed: {booking.service_name} with {booking.instructor.first_name}"
        local_dt = self._get_booking_local_datetime(booking)
        formatted_date = local_dt.strftime("%A, %B %d, %Y")
        formatted_time = local_dt.strftime("%-I:%M %p")
        context = {
            "booking": booking,
            "student_display_name": format_private_display_name(
                getattr(getattr(booking, "student", None), "first_name", None),
                getattr(getattr(booking, "student", None), "last_name", None),
                default="Student",
            ),
            "formatted_date": formatted_date,
            "formatted_time": formatted_time,
            "subject": subject,
        }
        html_content = self.template_service.render_template(
            TemplateRegistry.BOOKING_CONFIRMATION_STUDENT, context
        )
        self.email_service.send_email(
            to_email=booking.student.email,
            subject=subject,
            html_content=html_content,
            template=TemplateRegistry.BOOKING_CONFIRMATION_STUDENT,
        )
        self.logger.info("Student confirmation email sent for booking %s", booking.id)
        return True

    @retry(max_attempts=3, backoff_seconds=1.0)
    def _send_instructor_booking_notification(self, booking: Booking) -> bool:
        """Send new booking notification to instructor using template."""
        instructor_id = getattr(booking, "instructor_id", None)
        if instructor_id and not self._should_send_email(
            instructor_id, "lesson_updates", "booking_confirmation_instructor"
        ):
            return True

        subject = f"New Booking: {booking.service_name} with {booking.student.first_name}"
        local_dt = self._get_booking_local_datetime(booking)
        formatted_date = local_dt.strftime("%A, %B %d, %Y")
        formatted_time = local_dt.strftime("%-I:%M %p")
        context = {
            "booking": booking,
            "student_display_name": format_private_display_name(
                getattr(getattr(booking, "student", None), "first_name", None),
                getattr(getattr(booking, "student", None), "last_name", None),
                default="Student",
            ),
            "formatted_date": formatted_date,
            "formatted_time": formatted_time,
            "subject": subject,
            "header_bg_color": "#10B981",
            "header_text_color": "#D1FAE5",
        }
        html_content = self.template_service.render_template(
            TemplateRegistry.BOOKING_CONFIRMATION_INSTRUCTOR, context
        )
        self.email_service.send_email(
            to_email=booking.instructor.email,
            subject=subject,
            html_content=html_content,
            template=TemplateRegistry.BOOKING_CONFIRMATION_INSTRUCTOR,
        )
        self.logger.info("Instructor notification email sent for booking %s", booking.id)
        return True
