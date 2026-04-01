from __future__ import annotations

from datetime import datetime, timedelta
import logging
from typing import TYPE_CHECKING

from ...core.exceptions import ServiceException
from ...models.booking import Booking
from ...repositories.factory import RepositoryFactory
from ..base import BaseService
from .mixin_base import NotificationMixinBase


class NotificationSchedulingMixin(NotificationMixinBase):
    """Scheduled notification dispatch — daily reminder batch."""

    if TYPE_CHECKING:
        logger: logging.Logger

    @BaseService.measure_operation("send_reminder_emails")
    def send_reminder_emails(self) -> int:
        """Send 24-hour reminder emails for upcoming bookings."""
        if not self.db:
            self.logger.error("Database session required for sending reminders")
            raise ServiceException("Database session required for sending reminders")

        try:
            bookings = self._get_tomorrows_bookings()
            if not bookings:
                self.logger.info("No bookings found for tomorrow")
                return 0

            sent_count = self._send_booking_reminders(bookings)
            self.logger.info("Sent %s reminder emails for %s bookings", sent_count, len(bookings))
            return sent_count
        except Exception as exc:
            self.logger.error("Error in send_reminder_emails: %s", str(exc))
            raise ServiceException(f"Failed to send reminder emails: {str(exc)}")

    def _get_tomorrows_bookings(self) -> list[Booking]:
        """Get all confirmed bookings for tomorrow."""
        from datetime import timezone as tz

        utc_now = datetime.now(tz.utc).date()
        date_range = [
            utc_now,
            utc_now + timedelta(days=1),
            utc_now + timedelta(days=2),
        ]
        booking_repository = RepositoryFactory.create_booking_repository(self.db)
        all_bookings = booking_repository.get_bookings_by_date_range_and_status(
            date_range[0], date_range[-1], "CONFIRMED"
        )
        self.logger.info("Found %s bookings for tomorrow", len(all_bookings))
        bookings: list[Booking] = all_bookings
        return bookings

    def _send_booking_reminders(self, bookings: list[Booking]) -> int:
        """Send reminder emails for a list of bookings."""
        sent_count = 0
        for booking in bookings:
            student_sent = False
            instructor_sent = False
            try:
                student_sent = self._send_student_reminder(booking)
            except Exception as exc:
                self.logger.error(
                    "Failed to send student reminder for booking %s after retries: %s",
                    booking.id,
                    str(exc),
                )
            try:
                instructor_sent = self._send_instructor_reminder(booking)
            except Exception as exc:
                self.logger.error(
                    "Failed to send instructor reminder for booking %s after retries: %s",
                    booking.id,
                    str(exc),
                )
            if student_sent and instructor_sent:
                sent_count += 1
        return sent_count
