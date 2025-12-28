# backend/app/repositories/payment_monitoring_repository.py
"""
Payment Monitoring Repository for InstaInstru Platform.

Handles data access for payment system monitoring.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from ..models.booking import Booking, BookingStatus, PaymentStatus
from ..models.payment import PaymentEvent


@dataclass
class PaymentStatData:
    """Payment status count data."""

    payment_status: Optional[str]
    count: int


@dataclass
class PaymentEventCountData:
    """Payment event type count data."""

    event_type: str
    count: int


class PaymentMonitoringRepository:
    """Repository for payment monitoring data access."""

    def __init__(self, db: Session):
        """Initialize with database session."""
        self.db = db

    def get_payment_status_counts(self, min_booking_date: datetime) -> List[PaymentStatData]:
        """
        Get booking counts by payment status for confirmed bookings.

        Args:
            min_booking_date: Only include bookings on or after this date

        Returns:
            List of payment status counts
        """
        rows = (
            self.db.query(Booking.payment_status, func.count(Booking.id).label("count"))
            .filter(
                Booking.status == BookingStatus.CONFIRMED,
                Booking.booking_date >= min_booking_date.date(),
            )
            .group_by(Booking.payment_status)
            .all()
        )

        return [PaymentStatData(payment_status=row[0], count=row[1]) for row in rows]

    def get_recent_event_counts(self, since: datetime) -> List[PaymentEventCountData]:
        """
        Get payment event counts by type since a given time.

        Args:
            since: Count events after this time

        Returns:
            List of event type counts
        """
        rows = (
            self.db.query(PaymentEvent.event_type, func.count(PaymentEvent.id).label("count"))
            .filter(PaymentEvent.created_at >= since)
            .group_by(PaymentEvent.event_type)
            .all()
        )

        return [PaymentEventCountData(event_type=row[0], count=row[1]) for row in rows]

    def count_overdue_authorizations(self, as_of_date: datetime) -> int:
        """
        Count bookings that are overdue for authorization.

        Args:
            as_of_date: Date to compare against

        Returns:
            Count of overdue bookings
        """
        result: int = (
            self.db.query(Booking)
            .filter(
                and_(
                    Booking.status == BookingStatus.CONFIRMED,
                    Booking.payment_status == PaymentStatus.SCHEDULED.value,
                    Booking.booking_date <= as_of_date.date(),
                )
            )
            .count()
        )
        return result

    def get_last_successful_authorization(self) -> Optional[PaymentEvent]:
        """
        Get the most recent successful authorization event.

        Returns:
            Last successful PaymentEvent or None
        """
        result: Optional[PaymentEvent] = (
            self.db.query(PaymentEvent)
            .filter(PaymentEvent.event_type.in_(["auth_succeeded", "auth_retry_succeeded"]))
            .order_by(PaymentEvent.created_at.desc())
            .first()
        )
        return result
