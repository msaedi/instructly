from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ...models.booking import Booking
from ...utils.privacy import format_private_display_name
from ..base import BaseService
from ..email import EmailService
from ..template_registry import TemplateRegistry
from ..template_service import TemplateService
from .common_mixin import retry
from .mixin_base import NotificationMixinBase


class NotificationBookingFollowupsMixin(NotificationMixinBase):
    """Booking reminders and completion emails."""

    if TYPE_CHECKING:
        logger: logging.Logger
        email_service: EmailService
        template_service: TemplateService

    @BaseService.measure_operation("send_booking_reminder")
    def send_booking_reminder(self, booking: Booking, reminder_type: str = "24h") -> bool:
        """Send reminder emails for a single booking."""
        try:
            student_sent = self._send_student_reminder(booking, reminder_type=reminder_type)
            instructor_sent = self._send_instructor_reminder(booking, reminder_type=reminder_type)
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

    @BaseService.measure_operation("send_booking_completed_notification")
    def send_booking_completed_notification(
        self, booking: Booking, recipient: str = "both"
    ) -> bool:
        """Send booking completion emails."""
        if not booking:
            self.logger.error("Cannot send booking completion: booking is None")
            return False

        recipient_norm = (recipient or "both").lower()
        send_student = recipient_norm in {"student", "both"}
        send_instructor = recipient_norm in {"instructor", "both"}
        student_success = True
        instructor_success = True

        if send_student:
            try:
                student_success = self._send_student_completion_notification(booking)
            except Exception as exc:
                self.logger.error(
                    "Failed to send student completion for booking %s: %s",
                    booking.id,
                    exc,
                )
                student_success = False

        if send_instructor:
            try:
                instructor_success = self._send_instructor_completion_notification(booking)
            except Exception as exc:
                self.logger.error(
                    "Failed to send instructor completion for booking %s: %s",
                    booking.id,
                    exc,
                )
                instructor_success = False

        return student_success and instructor_success

    @retry(max_attempts=3, backoff_seconds=1.0)
    def _send_student_completion_notification(self, booking: Booking) -> bool:
        """Send lesson completed email to student."""
        student_id = getattr(booking, "student_id", None)
        if student_id and not self._should_send_email(
            student_id, "lesson_updates", "booking_completed_student"
        ):
            return True

        participants = self._require_booking_participants(
            booking, "send student completion notification"
        )
        if participants is None:
            return False
        student, _instructor = participants

        subject = f"Lesson Completed: {booking.service_name}"
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
            TemplateRegistry.BOOKING_COMPLETED_STUDENT, context
        )
        self.email_service.send_email(
            to_email=student.email,
            subject=subject,
            html_content=html_content,
            template=TemplateRegistry.BOOKING_COMPLETED_STUDENT,
        )
        return True

    @retry(max_attempts=3, backoff_seconds=1.0)
    def _send_instructor_completion_notification(self, booking: Booking) -> bool:
        """Send lesson completed email to instructor."""
        instructor_id = getattr(booking, "instructor_id", None)
        if instructor_id and not self._should_send_email(
            instructor_id, "lesson_updates", "booking_completed_instructor"
        ):
            return True

        participants = self._require_booking_participants(
            booking, "send instructor completion notification"
        )
        if participants is None:
            return False
        student, instructor = participants

        subject = f"Lesson Completed: {booking.service_name}"
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
            TemplateRegistry.BOOKING_COMPLETED_INSTRUCTOR, context
        )
        self.email_service.send_email(
            to_email=instructor.email,
            subject=subject,
            html_content=html_content,
            template=TemplateRegistry.BOOKING_COMPLETED_INSTRUCTOR,
        )
        return True

    @retry(max_attempts=3, backoff_seconds=1.0)
    def _send_student_reminder(self, booking: Booking, *, reminder_type: str = "24h") -> bool:
        """Send reminder to student."""
        student_id = getattr(booking, "student_id", None)
        if student_id and not self._should_send_email(
            student_id, "lesson_updates", "booking_reminder_student"
        ):
            return True

        participants = self._require_booking_participants(booking, "send student reminder")
        if participants is None:
            return False
        student, _instructor = participants

        if reminder_type == "1h":
            subject = f"Reminder: {booking.service_name} in 1 Hour"
        elif reminder_type == "24h":
            subject = f"Reminder: {booking.service_name} Tomorrow"
        else:
            subject = f"Reminder: {booking.service_name}"

        local_dt = self._get_booking_local_datetime(booking)
        context = {
            "booking": booking,
            "formatted_time": local_dt.strftime("%-I:%M %p"),
            "subject": subject,
        }
        html_content = self.template_service.render_template(
            TemplateRegistry.BOOKING_REMINDER_STUDENT, context
        )
        self.email_service.send_email(
            to_email=student.email,
            subject=subject,
            html_content=html_content,
            template=TemplateRegistry.BOOKING_REMINDER_STUDENT,
        )
        return True

    @retry(max_attempts=3, backoff_seconds=1.0)
    def _send_instructor_reminder(self, booking: Booking, *, reminder_type: str = "24h") -> bool:
        """Send reminder to instructor."""
        instructor_id = getattr(booking, "instructor_id", None)
        if instructor_id and not self._should_send_email(
            instructor_id, "lesson_updates", "booking_reminder_instructor"
        ):
            return True

        participants = self._require_booking_participants(booking, "send instructor reminder")
        if participants is None:
            return False
        student, instructor = participants

        if reminder_type == "1h":
            subject = f"Reminder: {booking.service_name} in 1 Hour"
        elif reminder_type == "24h":
            subject = f"Reminder: {booking.service_name} Tomorrow"
        else:
            subject = f"Reminder: {booking.service_name}"

        local_dt = self._get_booking_local_datetime(booking)
        context = {
            "booking": booking,
            "student_display_name": format_private_display_name(
                getattr(student, "first_name", None),
                getattr(student, "last_name", None),
                default="Student",
            ),
            "formatted_time": local_dt.strftime("%-I:%M %p"),
            "subject": subject,
        }
        html_content = self.template_service.render_template(
            TemplateRegistry.BOOKING_REMINDER_INSTRUCTOR, context
        )
        self.email_service.send_email(
            to_email=instructor.email,
            subject=subject,
            html_content=html_content,
            template=TemplateRegistry.BOOKING_REMINDER_INSTRUCTOR,
        )
        return True
