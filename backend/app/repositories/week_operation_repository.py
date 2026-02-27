# backend/app/repositories/week_operation_repository.py
"""
WeekOperationRepository - Complex Multi-Date and Bulk Operations

This repository handles bulk operations, week patterns, and complex multi-date
queries. It complements AvailabilityRepository by handling operations that
span multiple dates or require complex business logic.

DO: Add methods for:
- Week-based bulk operations
- Pattern support queries
- Complex operations involving multiple dates
- Bulk creates/updates/deletes with special logic

DO NOT: Add methods for:
- Basic CRUD operations
- Single slot operations
- Blackout dates
- Simple queries that AvailabilityRepository can handle

"""

from datetime import date, time
import logging
from typing import Any, Dict, List, Sequence, TypedDict, cast

from sqlalchemy.engine import Row
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..core.exceptions import RepositoryException

# AvailabilitySlot removed - bitmap-only storage now
from ..models.booking import Booking, BookingStatus

logger = logging.getLogger(__name__)


class BookingTimeRange(TypedDict):
    start_time: time
    end_time: time


class WeekBookingsSummary(TypedDict):
    booked_time_ranges_by_date: Dict[str, List[BookingTimeRange]]
    total_bookings: int


class DateRangeBookingsSummary(TypedDict):
    bookings_by_date: Dict[str, List[BookingTimeRange]]
    total_bookings: int


class WeekOperationRepository:
    """
    Repository for week operation data access.

    NOTE: Slot-based operations removed. Use AvailabilityDayRepository for bitmap operations.
    """

    def __init__(self, db: Session):
        """Initialize repository."""
        self.db = db
        self.logger = logging.getLogger(__name__)

    def flush(self) -> None:
        """Flush pending ORM changes."""
        self.db.flush()

    # Week Booking Queries

    def get_week_bookings_with_slots(
        self, instructor_id: str, week_dates: Sequence[date]
    ) -> WeekBookingsSummary:
        """
        Get all bookings in a target week.

        UPDATED: No longer tracks slot IDs since bookings don't reference slots.
        Returns booking time ranges directly.

        Args:
            instructor_id: The instructor ID
            week_dates: List of dates in the week (typically Monday-Sunday)

        Returns:
            Dictionary with:
                - booked_time_ranges_by_date: Dict of date -> list of time ranges
                - total_bookings: Total count of bookings
        """
        try:
            # Direct query on bookings - no slot references
            booking_rows = cast(
                Sequence[Row[Any]],
                self.db.query(
                    Booking.booking_date,
                    Booking.start_time,
                    Booking.end_time,
                )
                .filter(
                    Booking.instructor_id == instructor_id,
                    Booking.booking_date.in_(week_dates),
                    Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
                )
                .all(),
            )

            booked_time_ranges_by_date: Dict[str, List[BookingTimeRange]] = {}

            for row in booking_rows:
                mapping = row._mapping
                booking_date = mapping.get("booking_date")
                if booking_date is None:
                    continue
                date_str = booking_date.isoformat()
                start_time_value = mapping.get("start_time")
                end_time_value = mapping.get("end_time")
                if not isinstance(start_time_value, time) or not isinstance(end_time_value, time):
                    continue
                booked_time_ranges_by_date.setdefault(date_str, []).append(
                    {"start_time": start_time_value, "end_time": end_time_value}
                )

            self.logger.info(f"Found {len(booking_rows)} bookings in target week")

            return {
                "booked_time_ranges_by_date": booked_time_ranges_by_date,
                "total_bookings": len(booking_rows),
            }

        except SQLAlchemyError as e:
            self.logger.error(f"Error getting week bookings: {str(e)}")
            raise RepositoryException(f"Failed to get week bookings: {str(e)}")

    def get_bookings_in_date_range(
        self, instructor_id: str, start_date: date, end_date: date
    ) -> DateRangeBookingsSummary:
        """
        Get all bookings in a date range for pattern operations.

        UPDATED: Returns booking times directly without slot references.

        Args:
            instructor_id: The instructor ID
            start_date: Start of date range
            end_date: End of date range

        Returns:
            Dictionary with:
                - bookings_by_date: Dict of date -> list of booking info
                - total_bookings: Total count of bookings
        """
        try:
            # Direct query on bookings
            booking_rows = cast(
                Sequence[Row[Any]],
                self.db.query(
                    Booking.booking_date,
                    Booking.start_time,
                    Booking.end_time,
                )
                .filter(
                    Booking.instructor_id == instructor_id,
                    Booking.booking_date >= start_date,
                    Booking.booking_date <= end_date,
                    Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
                )
                .all(),
            )

            bookings_by_date: Dict[str, List[BookingTimeRange]] = {}

            for row in booking_rows:
                mapping = row._mapping
                booking_date = mapping.get("booking_date")
                if booking_date is None:
                    continue
                start_time_value = mapping.get("start_time")
                end_time_value = mapping.get("end_time")
                if not isinstance(start_time_value, time) or not isinstance(end_time_value, time):
                    continue
                date_str = booking_date.isoformat()
                bookings_by_date.setdefault(date_str, []).append(
                    {
                        "start_time": start_time_value,
                        "end_time": end_time_value,
                    }
                )

            self.logger.info(
                "Found %s bookings across %s dates", len(booking_rows), len(bookings_by_date)
            )

            return {
                "bookings_by_date": bookings_by_date,
                "total_bookings": len(booking_rows),
            }

        except SQLAlchemyError as e:
            self.logger.error(f"Error getting bookings in range: {str(e)}")
            raise RepositoryException(f"Failed to get bookings: {str(e)}")
