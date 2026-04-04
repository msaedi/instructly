from __future__ import annotations

from typing import Optional

from jinja2.exceptions import TemplateNotFound

from ...core.exceptions import ServiceException
from ...models.booking import Booking
from ...models.user import User
from ...utils.privacy import format_private_display_name
from ..base import BaseService
from ..template_registry import TemplateRegistry
from .common_mixin import retry
from .mixin_base import NotificationMixinBase


class NotificationBookingCancellationMixin(NotificationMixinBase):
    """Booking cancellation emails — by role."""

    def _resolve_cancellation_actors(
        self, booking: Booking, cancelled_by: User | str | None
    ) -> tuple[str, bool]:
        if isinstance(cancelled_by, User):
            is_student_cancellation = cancelled_by.id == booking.student_id
            cancelled_by_role = "student" if is_student_cancellation else "instructor"
        elif isinstance(cancelled_by, str):
            cancelled_by_role = cancelled_by
            is_student_cancellation = cancelled_by_role == "student"
        else:
            cancelled_by_role = "student"
            is_student_cancellation = True
        return cancelled_by_role, is_student_cancellation

    def _dispatch_cancellation_emails(
        self,
        booking: Booking,
        *,
        is_student_cancellation: bool,
        cancelled_by_role: str,
        reason: Optional[str],
    ) -> bool:
        if is_student_cancellation:
            try:
                success = self._send_instructor_cancellation_notification(
                    booking, reason, cancelled_by_role
                )
            except TemplateNotFound as exc:
                raise ServiceException(f"Email template error: {str(exc)}")
            except Exception as exc:
                self.logger.error(
                    "Failed to send instructor cancellation after retries: %s", str(exc)
                )
                success = False

            try:
                student_success = self._send_student_cancellation_confirmation(booking)
            except TemplateNotFound as exc:
                raise ServiceException(f"Email template error: {str(exc)}")
            except Exception as exc:
                self.logger.error("Failed to send student confirmation after retries: %s", str(exc))
                student_success = False
            return success and student_success

        try:
            success = self._send_student_cancellation_notification(
                booking, reason, cancelled_by_role
            )
        except TemplateNotFound as exc:
            raise ServiceException(f"Email template error: {str(exc)}")
        except Exception as exc:
            self.logger.error("Failed to send student cancellation after retries: %s", str(exc))
            success = False

        try:
            instructor_success = self._send_instructor_cancellation_confirmation(booking)
        except TemplateNotFound as exc:
            raise ServiceException(f"Email template error: {str(exc)}")
        except Exception as exc:
            self.logger.error("Failed to send instructor confirmation after retries: %s", str(exc))
            instructor_success = False
        return success and instructor_success

    @BaseService.measure_operation("send_cancellation_notification")
    def send_cancellation_notification(
        self, booking: Booking, cancelled_by: User | str | None, reason: Optional[str] = None
    ) -> bool:
        """Send cancellation notification emails."""
        if not booking:
            self.logger.error("Cannot send cancellation notification: booking is None")
            return False
        if cancelled_by is None:
            self.logger.error("Cannot send cancellation notification: cancelled_by is None")
            return False

        try:
            self.logger.info("Sending cancellation emails for booking %s", booking.id)
            cancelled_by_role, is_student_cancellation = self._resolve_cancellation_actors(
                booking, cancelled_by
            )
            return self._dispatch_cancellation_emails(
                booking,
                is_student_cancellation=is_student_cancellation,
                cancelled_by_role=cancelled_by_role,
                reason=reason,
            )
        except ServiceException:
            raise
        except Exception as exc:
            self.logger.error("Unexpected error sending cancellation emails: %s", str(exc))
            raise

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

        participants = self._require_booking_participants(
            booking, "send student cancellation notification"
        )
        if participants is None:
            return False
        student, _instructor = participants

        subject = f"Booking Cancelled: {booking.service_name}"
        local_dt = self._get_booking_local_datetime(booking)
        context = {
            "booking": booking,
            "formatted_date": local_dt.strftime("%A, %B %d, %Y"),
            "formatted_time": local_dt.strftime("%-I:%M %p"),
            "reason": reason,
            "cancelled_by": cancelled_by,
            "subject": subject,
            "header_bg_color": "#EF4444",
            "header_text_color": "#FEE2E2",
        }
        html_content = self.template_service.render_template(
            TemplateRegistry.BOOKING_CANCELLATION_STUDENT, context
        )
        self.email_service.send_email(
            to_email=student.email,
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

        participants = self._require_booking_participants(
            booking, "send instructor cancellation notification"
        )
        if participants is None:
            return False
        student, instructor = participants

        subject = f"Booking Cancelled: {booking.service_name}"
        local_dt = self._get_booking_local_datetime(booking)
        context = {
            "booking": booking,
            "student_display_name": format_private_display_name(
                getattr(student, "first_name", None),
                getattr(student, "last_name", None),
                default="Student",
            ),
            "formatted_date": local_dt.strftime("%A, %B %d, %Y"),
            "formatted_time": local_dt.strftime("%-I:%M %p"),
            "reason": reason,
            "cancelled_by": cancelled_by,
            "subject": subject,
        }
        html_content = self.template_service.render_template(
            TemplateRegistry.BOOKING_CANCELLATION_INSTRUCTOR, context
        )
        self.email_service.send_email(
            to_email=instructor.email,
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

        participants = self._require_booking_participants(
            booking, "send student cancellation confirmation"
        )
        if participants is None:
            return False
        student, _instructor = participants

        subject = f"Cancellation Confirmed: {booking.service_name}"
        local_dt = self._get_booking_local_datetime(booking)
        context = {
            "booking": booking,
            "student_display_name": format_private_display_name(
                getattr(student, "first_name", None),
                getattr(student, "last_name", None),
                default="Student",
            ),
            "formatted_date": local_dt.strftime("%A, %B %d, %Y"),
            "formatted_time": local_dt.strftime("%-I:%M %p"),
            "subject": subject,
        }
        html_content = self.template_service.render_template(
            TemplateRegistry.BOOKING_CANCELLATION_CONFIRMATION_STUDENT, context
        )
        self.email_service.send_email(
            to_email=student.email,
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

        participants = self._require_booking_participants(
            booking, "send instructor cancellation confirmation"
        )
        if participants is None:
            return False
        student, instructor = participants

        subject = f"Cancellation Confirmed: {booking.service_name}"
        local_dt = self._get_booking_local_datetime(booking)
        context = {
            "booking": booking,
            "student_display_name": format_private_display_name(
                getattr(student, "first_name", None),
                getattr(student, "last_name", None),
                default="Student",
            ),
            "formatted_date": local_dt.strftime("%A, %B %d, %Y"),
            "formatted_time": local_dt.strftime("%-I:%M %p"),
            "subject": subject,
        }
        html_content = self.template_service.render_template(
            TemplateRegistry.BOOKING_CANCELLATION_CONFIRMATION_INSTRUCTOR, context
        )
        self.email_service.send_email(
            to_email=instructor.email,
            subject=subject,
            html_content=html_content,
            template=TemplateRegistry.BOOKING_CANCELLATION_CONFIRMATION_INSTRUCTOR,
        )
        return True
