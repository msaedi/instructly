"""Payment-event persistence helpers."""

from datetime import date, datetime, timezone
import logging
from typing import Any, Dict, List, Optional, Sequence, cast

from sqlalchemy import func
from sqlalchemy.orm import joinedload
import ulid

from ...core.exceptions import RepositoryException
from ...models.booking import Booking
from ...models.payment import PaymentEvent, PaymentIntent
from ...services.audit_service import AuditService, Status
from .mixin_base import PaymentRepositoryMixinBase

logger = logging.getLogger(__name__)


class PaymentPaymentEventMixin(PaymentRepositoryMixinBase):
    """Payment-event queries and mutations."""

    def create_payment_event(
        self, booking_id: str, event_type: str, event_data: Optional[Dict[str, Any]] = None
    ) -> PaymentEvent:
        """
        Create a payment event for tracking payment state changes.

        Args:
            booking_id: The booking this event relates to
            event_type: Type of event (e.g., 'auth_scheduled', 'auth_succeeded')
            event_data: Optional JSON data for the event

        Returns:
            Created PaymentEvent object

        Raises:
            RepositoryException: If creation fails
        """
        try:
            event = PaymentEvent(
                id=str(ulid.ULID()),
                booking_id=booking_id,
                event_type=event_type,
                event_data=event_data or {},
            )
            try:
                event.created_at = datetime.now(timezone.utc)
            except Exception:
                logger.debug("Non-fatal error ignored", exc_info=True)
            self.db.add(event)
            self.db.flush()
            try:
                audit_action = _payment_event_to_audit_action(event_type)
                if audit_action:
                    status: Status = "failed" if _event_indicates_failure(event_type) else "success"
                    AuditService(self.db).log(
                        action=audit_action,
                        resource_type="payment",
                        resource_id=booking_id,
                        actor_type="system",
                        actor_id="payment_tasks",
                        description=f"Payment event: {event_type}",
                        metadata={
                            "event_type": event_type,
                            "event_data": event_data or {},
                            "booking_id": booking_id,
                        },
                        status=status,
                    )
            except Exception:
                logger.debug("Non-fatal error ignored", exc_info=True)
            return event
        except Exception as e:
            self.logger.error("Failed to create payment event: %s", str(e))
            raise RepositoryException(f"Failed to create payment event: {str(e)}")

    def bulk_create_payment_events(self, events: List[Dict[str, Any]]) -> List[PaymentEvent]:
        """
        Bulk insert payment events for a booking.

        Args:
            events: List of dicts containing booking_id, event_type, and optional event_data

        Returns:
            List of PaymentEvent objects (IDs populated)
        """
        if not events:
            return []
        try:
            now = datetime.now(timezone.utc)
            payment_events = [
                PaymentEvent(
                    id=str(ulid.ULID()),
                    booking_id=event["booking_id"],
                    event_type=event["event_type"],
                    event_data=event.get("event_data", {}),
                    created_at=event.get("created_at", now),
                )
                for event in events
            ]
            self.db.bulk_save_objects(payment_events)
            self.db.flush()
            return payment_events
        except Exception as e:
            self.logger.error("Failed to bulk create payment events: %s", str(e))
            raise RepositoryException(f"Failed to bulk create payment events: {str(e)}")

    def get_payment_events_for_booking(
        self,
        booking_id: str,
        *,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> List[PaymentEvent]:
        """
        Get all payment events for a booking.

        Args:
            booking_id: The booking ID
            start_time: Optional start datetime (inclusive).
            end_time: Optional end datetime (inclusive).
            limit: Optional maximum rows to return (None for no limit).

        Returns:
            List of PaymentEvent objects ordered by creation time

        Raises:
            RepositoryException: If query fails
        """
        try:
            query = (
                self.db.query(PaymentEvent)
                .options(joinedload(PaymentEvent.booking).joinedload(Booking.payment_intent))
                .filter(PaymentEvent.booking_id == booking_id)
            )
            if start_time:
                query = query.filter(PaymentEvent.created_at >= start_time)
            if end_time:
                query = query.filter(PaymentEvent.created_at <= end_time)
            query = query.order_by(PaymentEvent.created_at.asc())
            if limit is not None:
                query = query.limit(limit)
            return cast(
                List[PaymentEvent],
                query.all(),
            )
        except Exception as e:
            self.logger.error("Failed to get payment events: %s", str(e))
            raise RepositoryException(f"Failed to get payment events: {str(e)}")

    def get_payment_events_for_user(
        self,
        user_id: str,
        *,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> List[PaymentEvent]:
        """
        Get all payment events for a user (as a student).

        Args:
            user_id: The user's ID (student).
            start_time: Optional start datetime (inclusive).
            end_time: Optional end datetime (inclusive).
            limit: Optional maximum rows to return (None for no limit).

        Returns:
            List of PaymentEvent objects ordered by creation time.

        Raises:
            RepositoryException: If query fails.
        """
        try:
            query = (
                self.db.query(PaymentEvent)
                .join(Booking, PaymentEvent.booking_id == Booking.id)
                .options(joinedload(PaymentEvent.booking).joinedload(Booking.payment_intent))
                .filter(Booking.student_id == user_id)
            )
            if start_time:
                query = query.filter(PaymentEvent.created_at >= start_time)
            if end_time:
                query = query.filter(PaymentEvent.created_at <= end_time)
            query = query.order_by(PaymentEvent.created_at.asc())
            if limit is not None:
                query = query.limit(limit)
            return cast(List[PaymentEvent], query.all())
        except Exception as e:
            self.logger.error("Failed to get payment events for user: %s", str(e))
            raise RepositoryException(f"Failed to get payment events for user: {str(e)}")

    def list_payment_events_by_types(
        self,
        event_types: Sequence[str],
        *,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        limit: Optional[int] = 50,
        offset: int = 0,
        desc: bool = True,
    ) -> List[PaymentEvent]:
        """
        List payment events by event types with optional date filtering.

        Args:
            event_types: Event types to include.
            start: Optional start datetime (inclusive).
            end: Optional end datetime (inclusive).
            limit: Optional maximum rows to return (None for no limit).
            offset: Rows to skip before returning results.
            desc: Order descending by created_at when True.

        Returns:
            List of PaymentEvent objects.
        """
        try:
            query = self.db.query(PaymentEvent).filter(PaymentEvent.event_type.in_(event_types))
            if start:
                query = query.filter(PaymentEvent.created_at >= start)
            if end:
                query = query.filter(PaymentEvent.created_at <= end)

            order_by = PaymentEvent.created_at.desc() if desc else PaymentEvent.created_at.asc()
            query = query.order_by(order_by)

            offset = max(0, offset)
            if offset:
                query = query.offset(offset)
            if limit is not None:
                query = query.limit(max(0, limit))

            return cast(List[PaymentEvent], query.all())
        except Exception as e:
            self.logger.error("Failed to list payment events by type: %s", str(e))
            raise RepositoryException(f"Failed to list payment events: {str(e)}")

    def count_payment_events_by_types(
        self,
        event_types: Sequence[str],
        *,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> int:
        """Count payment events by event types with optional date filtering."""
        try:
            query = (
                self.db.query(func.count())
                .select_from(PaymentEvent)
                .filter(PaymentEvent.event_type.in_(event_types))
            )
            if start:
                query = query.filter(PaymentEvent.created_at >= start)
            if end:
                query = query.filter(PaymentEvent.created_at <= end)
            return int(query.scalar() or 0)
        except Exception as e:
            self.logger.error("Failed to count payment events by type: %s", str(e))
            raise RepositoryException(f"Failed to count payment events: {str(e)}")

    def sum_application_fee_for_booking_date_range(self, start: date, end: date) -> int:
        """Sum application fees for bookings in the given date range."""
        try:
            total = (
                self.db.query(func.coalesce(func.sum(PaymentIntent.application_fee), 0))
                .join(Booking, Booking.id == PaymentIntent.booking_id)
                .filter(Booking.booking_date >= start, Booking.booking_date <= end)
                .scalar()
            )
            return int(total or 0)
        except Exception as e:
            self.logger.error("Failed to sum application fee: %s", str(e))
            raise RepositoryException(f"Failed to sum application fee: {str(e)}")

    def get_latest_payment_event(
        self, booking_id: str, event_type: Optional[str] = None
    ) -> Optional[PaymentEvent]:
        """
        Get the latest payment event for a booking.

        Args:
            booking_id: The booking ID
            event_type: Optional specific event type to filter

        Returns:
            Latest PaymentEvent or None

        Raises:
            RepositoryException: If query fails
        """
        try:
            query = self.db.query(PaymentEvent).filter(PaymentEvent.booking_id == booking_id)

            if event_type:
                query = query.filter(PaymentEvent.event_type == event_type)

            return cast(
                Optional[PaymentEvent],
                (query.order_by(PaymentEvent.created_at.desc(), PaymentEvent.id.desc())).first(),
            )
        except Exception as e:
            self.logger.error("Failed to get latest payment event: %s", str(e))
            raise RepositoryException(f"Failed to get latest payment event: {str(e)}")


def _payment_event_to_audit_action(event_type: str) -> str | None:
    normalized = (event_type or "").lower()
    if "refund" in normalized:
        return "payment.refund"
    if "capture" in normalized:
        return "payment.capture"
    if "auth" in normalized or "authorize" in normalized:
        return "payment.authorize"
    return None


def _event_indicates_failure(event_type: str) -> bool:
    normalized = (event_type or "").lower()
    return any(token in normalized for token in ("failed", "failure", "error", "denied"))
