"""Event handlers - process domain events from the job queue."""
import json
import logging
from typing import Callable, Dict, Optional

from sqlalchemy.orm import Session

from app.models.booking import Booking
from app.repositories.booking_repository import BookingRepository
from app.services.notification_service import NotificationService

logger = logging.getLogger(__name__)


def _load_booking(db: Session, booking_id: str) -> Optional[Booking]:
    """Load booking with relationships for notification rendering."""
    repo = BookingRepository(db)
    return repo.get_booking_with_details(booking_id)


def handle_booking_created(payload_str: str, db: Session) -> None:
    """Send booking confirmation email."""
    payload = json.loads(payload_str)

    booking = _load_booking(db, payload["booking_id"])
    if not booking:
        logger.warning("Booking %s not found for confirmation", payload["booking_id"])
        return

    notification_service = NotificationService(db)
    notification_service.send_booking_confirmation(booking)
    logger.info("Sent booking confirmation for %s", booking.id)


def handle_booking_cancelled(payload_str: str, db: Session) -> None:
    """Send cancellation notification email."""
    payload = json.loads(payload_str)

    booking = _load_booking(db, payload["booking_id"])
    if not booking:
        logger.warning("Booking %s not found for cancellation notice", payload["booking_id"])
        return

    notification_service = NotificationService(db)
    notification_service.send_cancellation_notification(
        booking=booking,
        cancelled_by=payload.get("cancelled_by"),
    )
    logger.info("Sent cancellation notification for %s", booking.id)


def handle_booking_reminder(payload_str: str, db: Session) -> None:
    """Send booking reminder email."""
    payload = json.loads(payload_str)

    booking = _load_booking(db, payload["booking_id"])
    if not booking:
        logger.warning("Booking %s not found for reminder", payload["booking_id"])
        return

    notification_service = NotificationService(db)
    reminder_type = payload.get("reminder_type") or "24h"
    notification_service.send_booking_reminder(booking, reminder_type)
    logger.info("Sent %s reminder for %s", reminder_type, booking.id)


# Registry of event type -> handler function
EVENT_HANDLERS: Dict[str, Callable[[str, Session], None]] = {
    "event:BookingCreated": handle_booking_created,
    "event:BookingCancelled": handle_booking_cancelled,
    "event:BookingReminder": handle_booking_reminder,
}


def process_event(job_type: str, payload: str, db: Session) -> bool:
    """
    Process an event job.

    Returns True if handled, False if not an event job.
    """
    if not job_type.startswith("event:"):
        return False

    handler = EVENT_HANDLERS.get(job_type)
    if not handler:
        logger.warning("No handler for event type: %s", job_type)
        return True  # Consumed but unhandled

    handler(payload, db)
    return True
