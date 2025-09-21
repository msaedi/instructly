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

Methods removed for clean architecture:
- delete_non_booked_slots() → Use delete_slots_preserving_booked_times()
"""

from datetime import date, time
import logging
from typing import Any, Dict, List, Optional, Sequence, TypedDict, cast

from sqlalchemy import and_, text
from sqlalchemy.engine import Row
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from ..core.exceptions import RepositoryException
from ..models.availability import AvailabilitySlot
from ..models.booking import Booking, BookingStatus
from .base_repository import BaseRepository

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


class SlotStatus(TypedDict):
    id: int
    start_time: time
    end_time: time
    is_booked: bool


class WeekSlotStatus(TypedDict):
    date: date
    slot_id: int
    start_time: time
    end_time: time
    booking_status: Optional[str]
    booking_id: Optional[int]


class WeekOperationRepository(BaseRepository[AvailabilitySlot]):
    """
    Repository for week operation data access.

    Works with the single-table design where AvailabilitySlot
    contains instructor_id, specific_date, start_time, and end_time.
    """

    def __init__(self, db: Session):
        """Initialize with AvailabilitySlot model."""
        super().__init__(db, AvailabilitySlot)
        self.logger = logging.getLogger(__name__)

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

    # Slot Queries

    def get_week_slots(
        self, instructor_id: str, start_date: date, end_date: date
    ) -> List[AvailabilitySlot]:
        """
        Get all slots for a week.

        Simple direct query in single-table design.

        Args:
            instructor_id: The instructor ID
            start_date: Start of week
            end_date: End of week

        Returns:
            List of availability slots
        """
        try:
            return cast(
                List[AvailabilitySlot],
                self.db.query(AvailabilitySlot)
                .filter(
                    AvailabilitySlot.instructor_id == instructor_id,
                    AvailabilitySlot.specific_date >= start_date,
                    AvailabilitySlot.specific_date <= end_date,
                )
                .order_by(AvailabilitySlot.specific_date, AvailabilitySlot.start_time)
                .all(),
            )
        except SQLAlchemyError as e:
            self.logger.error(f"Error getting week slots: {str(e)}")
            raise RepositoryException(f"Failed to get slots: {str(e)}")

    def get_slots_with_booking_status(
        self, instructor_id: str, target_date: date
    ) -> List[SlotStatus]:
        """
        Get all slots for a date with their booking status.

        UPDATED: Uses time-based overlap to determine if slots are booked.
        No longer relies on slot IDs in bookings.

        Args:
            instructor_id: The instructor ID
            target_date: The date to check

        Returns:
            List of slot dictionaries with booking status
        """
        try:
            # Get all slots for the date
            slots = cast(
                List[AvailabilitySlot],
                self.db.query(AvailabilitySlot)
                .filter(
                    AvailabilitySlot.instructor_id == instructor_id,
                    AvailabilitySlot.specific_date == target_date,
                )
                .all(),
            )

            if not slots:
                return []

            # For each slot, check if there's an overlapping booking
            result: List[SlotStatus] = []
            for slot in slots:
                # Check if any booking overlaps with this slot
                has_booking = (
                    self.db.query(Booking)
                    .filter(
                        and_(
                            Booking.instructor_id == instructor_id,
                            Booking.booking_date == target_date,
                            Booking.start_time < slot.end_time,
                            Booking.end_time > slot.start_time,
                            Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
                        )
                    )
                    .first()
                ) is not None

                result.append(
                    {
                        "id": int(slot.id),
                        "start_time": slot.start_time,
                        "end_time": slot.end_time,
                        "is_booked": has_booking,
                    }
                )

            return result

        except SQLAlchemyError as e:
            self.logger.error(f"Error getting slots with status: {str(e)}")
            raise RepositoryException(f"Failed to get slots: {str(e)}")

    def get_week_with_booking_status(
        self, instructor_id: str, start_date: date, end_date: date
    ) -> List[WeekSlotStatus]:
        """
        Get week availability with booking status for each slot.

        UPDATED: Uses time-based overlap instead of slot ID matching.
        Each slot is checked for overlapping bookings.

        Args:
            instructor_id: The instructor ID
            start_date: Start of range
            end_date: End of range

        Returns:
            List of dicts with slot and booking information
        """
        try:
            # Use raw SQL for efficient overlap checking
            query = text(
                """
                SELECT
                    s.specific_date,
                    s.id as slot_id,
                    s.start_time,
                    s.end_time,
                    CASE
                        WHEN EXISTS (
                            SELECT 1 FROM bookings b
                            WHERE b.instructor_id = s.instructor_id
                              AND b.booking_date = s.specific_date
                              AND b.start_time < s.end_time
                              AND b.end_time > s.start_time
                              AND b.status IN ('CONFIRMED', 'COMPLETED')
                        ) THEN 'CONFIRMED'
                        ELSE NULL
                    END as booking_status,
                    (
                        SELECT b.id FROM bookings b
                        WHERE b.instructor_id = s.instructor_id
                          AND b.booking_date = s.specific_date
                          AND b.start_time < s.end_time
                          AND b.end_time > s.start_time
                          AND b.status IN ('CONFIRMED', 'COMPLETED')
                        LIMIT 1
                    ) as booking_id
                FROM availability_slots s
                WHERE s.instructor_id = :instructor_id
                  AND s.specific_date BETWEEN :start_date AND :end_date
                ORDER BY s.specific_date, s.start_time
                """
            )

            results = cast(
                Sequence[Row[Any]],
                self.db.execute(
                    query,
                    {
                        "instructor_id": instructor_id,
                        "start_date": start_date,
                        "end_date": end_date,
                    },
                ).fetchall(),
            )

            week_view: List[WeekSlotStatus] = []
            for row in results:
                mapping = row._mapping
                date_value = mapping.get("specific_date")
                start_time_value = mapping.get("start_time")
                end_time_value = mapping.get("end_time")
                if not isinstance(date_value, date):
                    continue
                if not isinstance(start_time_value, time) or not isinstance(end_time_value, time):
                    continue
                week_view.append(
                    {
                        "date": date_value,
                        "slot_id": int(mapping.get("slot_id", 0) or 0),
                        "start_time": start_time_value,
                        "end_time": end_time_value,
                        "booking_status": cast(Optional[str], mapping.get("booking_status")),
                        "booking_id": (
                            int(mapping.get("booking_id"))
                            if mapping.get("booking_id") is not None
                            else None
                        ),
                    }
                )

            return week_view

        except SQLAlchemyError as e:
            self.logger.error(f"Error getting week with status: {str(e)}")
            raise RepositoryException(f"Failed to get week status: {str(e)}")

    # Bulk Operations

    def bulk_create_slots(self, slots: Sequence[Dict[str, Any]]) -> int:
        """
        Bulk create slots using high-performance bulk_insert_mappings.

        Args:
            slots: List of slot dictionaries with instructor_id, specific_date, start_time, end_time

        Returns:
            Number of slots created
        """
        try:
            slot_records = list(slots)
            if not slot_records:
                return 0

            self.db.bulk_insert_mappings(AvailabilitySlot, slot_records)
            self.db.flush()
            return len(slot_records)

        except IntegrityError as e:
            self.logger.error(f"Integrity error bulk creating slots: {str(e)}")
            raise RepositoryException(f"Duplicate slots or invalid data: {str(e)}")
        except SQLAlchemyError as e:
            self.logger.error(f"Error bulk creating slots: {str(e)}")
            raise RepositoryException(f"Failed to bulk create slots: {str(e)}")

    def bulk_delete_slots(self, slot_ids: Sequence[int]) -> int:
        """
        Bulk delete slots by IDs.

        Uses IN clause for efficient deletion.

        Args:
            slot_ids: List of slot IDs to delete

        Returns:
            Number of slots deleted
        """
        try:
            slot_id_list = list(slot_ids)
            if not slot_id_list:
                return 0

            result = (
                self.db.query(AvailabilitySlot)
                .filter(AvailabilitySlot.id.in_(slot_id_list))
                .delete(synchronize_session=False)
            )
            self.db.flush()
            return int(result)

        except SQLAlchemyError as e:
            self.logger.error(f"Error bulk deleting slots: {str(e)}")
            raise RepositoryException(f"Failed to delete slots: {str(e)}")

    def delete_slots_preserving_booked_times(
        self, instructor_id: str, week_dates: List[date], preserve_booked: bool = True
    ) -> int:
        """
        Delete slots from a week, optionally preserving slots that have bookings.

        UPDATED: Uses time-based overlap to determine which slots to preserve.
        This maintains the architectural principle that bookings are independent.

        Args:
            instructor_id: The instructor ID
            week_dates: List of dates in the week
            preserve_booked: If True, preserve slots with overlapping bookings

        Returns:
            Number of slots deleted
        """
        try:
            if preserve_booked:
                # Use raw SQL for efficient deletion with overlap check
                query = text(
                    """
                    DELETE FROM availability_slots s
                    WHERE s.instructor_id = :instructor_id
                      AND s.specific_date = ANY(:week_dates)
                      AND NOT EXISTS (
                          SELECT 1 FROM bookings b
                          WHERE b.instructor_id = s.instructor_id
                            AND b.booking_date = s.specific_date
                            AND b.start_time < s.end_time
                            AND b.end_time > s.start_time
                            AND b.status IN ('CONFIRMED', 'COMPLETED')
                      )
                    """
                )
                result = self.db.execute(
                    query,
                    {
                        "instructor_id": instructor_id,
                        "week_dates": week_dates,
                    },
                )
                deleted_count = result.rowcount
            else:
                # Delete all slots regardless of bookings
                deleted_count = (
                    self.db.query(AvailabilitySlot)
                    .filter(
                        AvailabilitySlot.instructor_id == instructor_id,
                        AvailabilitySlot.specific_date.in_(week_dates),
                    )
                    .delete(synchronize_session=False)
                )

            self.db.flush()
            return int(deleted_count)

        except SQLAlchemyError as e:
            self.logger.error(f"Error deleting slots: {str(e)}")
            raise RepositoryException(f"Failed to delete slots: {str(e)}")
