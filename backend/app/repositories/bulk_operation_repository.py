# backend/app/repositories/bulk_operation_repository.py
"""
BulkOperation Repository – booking validation for bulk availability changes.

Provides queries to check for existing bookings that would conflict
with bulk availability modifications (e.g., clearing a full day).
"""

from datetime import date
import logging
from typing import cast

from sqlalchemy import and_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..core.exceptions import RepositoryException
from ..models.booking import Booking, BookingStatus

logger = logging.getLogger(__name__)


class BulkOperationRepository:
    """Repository for booking validation during bulk operations."""

    def __init__(self, db: Session):
        """Initialize repository."""
        self.db = db
        self.logger = logging.getLogger(__name__)

    def has_bookings_on_date(self, instructor_id: str, target_date: date) -> bool:
        """
        Check if instructor has any confirmed/completed bookings on a date.

        Args:
            instructor_id: The instructor ID
            target_date: The date to check

        Returns:
            True if there are confirmed/completed bookings, False otherwise
        """
        try:
            count = cast(
                int,
                self.db.query(Booking)
                .filter(
                    and_(
                        Booking.instructor_id == instructor_id,
                        Booking.booking_date == target_date,
                        Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
                    )
                )
                .count(),
            )
            return count > 0

        except SQLAlchemyError as e:
            self.logger.error(f"Error checking bookings: {str(e)}")
            raise RepositoryException(f"Failed to check bookings: {str(e)}")
