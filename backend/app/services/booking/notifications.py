from __future__ import annotations

from datetime import datetime, timezone
import logging
from types import ModuleType
from typing import TYPE_CHECKING, Optional

from ...events import BookingCreated, BookingReminder
from ...models.booking import Booking, BookingStatus
from ...models.user import User
from ..base import BaseService
from ..notification_templates import (
    INSTRUCTOR_BOOKING_CANCELLED,
    INSTRUCTOR_BOOKING_CONFIRMED,
    STUDENT_BOOKING_CANCELLED,
    STUDENT_BOOKING_CONFIRMED,
)
from ..reminder_selection import (
    is_local_tomorrow_booking,
    reminder_candidate_window,
)
from ..sms_templates import (
    BOOKING_CANCELLED_INSTRUCTOR,
    BOOKING_CANCELLED_STUDENT,
    BOOKING_CONFIRMED_INSTRUCTOR,
    BOOKING_CONFIRMED_STUDENT,
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ...events import EventPublisher
    from ...repositories.booking_repository import BookingRepository
    from ..notification_service import NotificationService
    from ..system_message_service import SystemMessageService


def _booking_service_module() -> ModuleType:
    from .. import booking_service as booking_service_module

    return booking_service_module


class BookingNotificationsMixin:
    if TYPE_CHECKING:
        repository: BookingRepository
        event_publisher: EventPublisher
        notification_service: Optional[NotificationService]
        system_message_service: SystemMessageService

        @staticmethod
        def _format_user_display_name(user: Optional[User]) -> str:
            ...

        @staticmethod
        def _format_booking_date(booking: Booking) -> str:
            ...

        @staticmethod
        def _format_booking_time(booking: Booking) -> str:
            ...

        @staticmethod
        def _resolve_service_name(booking: Booking) -> str:
            ...

        def _invalidate_booking_caches(self, booking: Booking) -> None:
            ...

    @BaseService.measure_operation("send_booking_reminders")
    def send_booking_reminders(self) -> int:
        """
        Send 24-hour reminder emails for tomorrow's bookings.

        Returns:
            Number of reminders sent
        """
        now_utc = datetime.now(timezone.utc)
        window_start, window_end = reminder_candidate_window(now_utc)
        candidates = self.repository.get_bookings_starting_between_and_status(
            window_start,
            window_end,
            BookingStatus.CONFIRMED,
        )
        bookings = [
            booking for booking in candidates if is_local_tomorrow_booking(booking, now_utc=now_utc)
        ]

        sent_count = 0

        for booking in bookings:
            try:
                # Queue reminder event for this specific booking
                self.event_publisher.publish(
                    BookingReminder(
                        booking_id=booking.id,
                        reminder_type="24h",
                    )
                )
                sent_count += 1
            except Exception as e:
                logger.error("Error queueing reminder for booking %s: %s", booking.id, str(e))

        return sent_count

    def _send_booking_notifications(self, booking: Booking, is_reschedule: bool) -> None:
        if is_reschedule or not self.notification_service:
            return
        try:
            student_name = self._format_user_display_name(getattr(booking, "student", None))
            instructor_name = self._format_user_display_name(getattr(booking, "instructor", None))
            service_name = self._resolve_service_name(booking)
            date_str = self._format_booking_date(booking)
            time_str = self._format_booking_time(booking)

            self.notification_service.notify_user_best_effort(
                user_id=booking.instructor_id,
                template=INSTRUCTOR_BOOKING_CONFIRMED,
                student_name=student_name,
                service_name=service_name,
                date=date_str,
                time=time_str,
                booking_id=booking.id,
                send_email=False,
                send_sms=True,
                sms_template=BOOKING_CONFIRMED_INSTRUCTOR,
            )
            self.notification_service.notify_user_best_effort(
                user_id=booking.student_id,
                template=STUDENT_BOOKING_CONFIRMED,
                instructor_name=instructor_name,
                service_name=service_name,
                date=date_str,
                time=time_str,
                booking_id=booking.id,
                send_email=False,
                send_sms=True,
                sms_template=BOOKING_CONFIRMED_STUDENT,
            )
        except Exception as exc:
            logger.error("Failed to send booking notifications for %s: %s", booking.id, exc)

    @BaseService.measure_operation("send_booking_confirmation_notifications")
    def send_booking_notifications_after_confirmation(self, booking_id: str) -> None:
        """Send in-app/push/SMS/email notifications after a booking is confirmed."""
        if not self.notification_service:
            return

        booking = self.repository.get_booking_with_details(booking_id)
        if not booking:
            return

        is_reschedule = bool(getattr(booking, "rescheduled_from_booking_id", None))
        self._send_booking_notifications(booking, is_reschedule)

        try:
            self.notification_service.send_booking_confirmation(booking)
        except Exception as exc:
            logger.error("Failed to send booking confirmation emails for %s: %s", booking.id, exc)

    def _send_cancellation_notifications(self, booking: Booking, cancelled_by_role: str) -> None:
        if not self.notification_service:
            return
        try:
            details = booking
            if not getattr(details, "student", None) or not getattr(details, "instructor", None):
                detailed_booking = self.repository.get_booking_with_details(booking.id)
                if detailed_booking is not None:
                    details = detailed_booking

            service_name = self._resolve_service_name(details)
            date_str = self._format_booking_date(details)

            if cancelled_by_role == "student":
                student_name = self._format_user_display_name(getattr(details, "student", None))
                self.notification_service.notify_user_best_effort(
                    user_id=details.instructor_id,
                    template=INSTRUCTOR_BOOKING_CANCELLED,
                    student_name=student_name,
                    service_name=service_name,
                    date=date_str,
                    booking_id=booking.id,
                    send_email=False,
                    send_sms=True,
                    sms_template=BOOKING_CANCELLED_INSTRUCTOR,
                )
            elif cancelled_by_role == "instructor":
                instructor_name = self._format_user_display_name(
                    getattr(details, "instructor", None)
                )
                self.notification_service.notify_user_best_effort(
                    user_id=details.student_id,
                    template=STUDENT_BOOKING_CANCELLED,
                    instructor_name=instructor_name,
                    service_name=service_name,
                    date=date_str,
                    booking_id=booking.id,
                    send_email=False,
                    send_sms=True,
                    sms_template=BOOKING_CANCELLED_STUDENT,
                )
        except Exception as exc:
            logger.error("Failed to send cancellation notifications for %s: %s", booking.id, exc)

    def _handle_post_booking_tasks(
        self, booking: Booking, is_reschedule: bool = False, old_booking: Optional[Booking] = None
    ) -> None:
        """
        Handle notifications, system messages, and cache invalidation after booking creation.

        Args:
            booking: The created booking
            is_reschedule: Whether this is a rescheduled booking
            old_booking: The original booking if this is a reschedule
        """
        booking_service_module = _booking_service_module()

        # Publish async notification event only for confirmed bookings
        if booking.status == BookingStatus.CONFIRMED:
            try:
                self.event_publisher.publish(
                    BookingCreated(
                        booking_id=booking.id,
                        student_id=booking.student_id,
                        instructor_id=booking.instructor_id,
                        created_at=booking.created_at
                        or booking_service_module.datetime.now(booking_service_module.timezone.utc),
                    )
                )
            except Exception as e:
                logger.error("Failed to enqueue booking confirmation event: %s", str(e))

        # Create system message in conversation
        try:
            service_name = "Lesson"
            if booking.instructor_service and booking.instructor_service.name:
                service_name = booking.instructor_service.name

            if is_reschedule and old_booking:
                # Create rescheduled message
                self.system_message_service.create_booking_rescheduled_message(
                    student_id=booking.student_id,
                    instructor_id=booking.instructor_id,
                    booking_id=booking.id,
                    old_date=old_booking.booking_date,
                    old_time=old_booking.start_time,
                    new_date=booking.booking_date,
                    new_time=booking.start_time,
                )
            else:
                # Create booking created message
                self.system_message_service.create_booking_created_message(
                    student_id=booking.student_id,
                    instructor_id=booking.instructor_id,
                    booking_id=booking.id,
                    service_name=service_name,
                    booking_date=booking.booking_date,
                    start_time=booking.start_time,
                )
        except Exception as e:
            logger.error("Failed to create system message for booking %s: %s", booking.id, str(e))

        self._send_booking_notifications(booking, is_reschedule)

        # Invalidate relevant caches
        self._invalidate_booking_caches(booking)
