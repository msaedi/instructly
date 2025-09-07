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

from datetime import date
import logging
from typing import Dict, List

from sqlalchemy import and_, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from ..core.exceptions import RepositoryException
from ..models.availability import AvailabilitySlot
from ..models.booking import Booking, BookingStatus
from .base_repository import BaseRepository

logger = logging.getLogger(__name__)


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
        self, instructor_id: int, week_dates: List[date]
    ) -> Dict[str, any]:
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
            bookings = (
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
                .all()
            )

            # Process booking information
            booked_time_ranges_by_date = {}

            for booking in bookings:
                date_str = booking.booking_date.isoformat()
                if date_str not in booked_time_ranges_by_date:
                    booked_time_ranges_by_date[date_str] = []
                booked_time_ranges_by_date[date_str].append(
                    {"start_time": booking.start_time, "end_time": booking.end_time}
                )

            self.logger.info(f"Found {len(bookings)} bookings in target week")

            return {
                "booked_time_ranges_by_date": booked_time_ranges_by_date,
                "total_bookings": len(bookings),
            }

        except SQLAlchemyError as e:
            self.logger.error(f"Error getting week bookings: {str(e)}")
            raise RepositoryException(f"Failed to get week bookings: {str(e)}")

    def get_bookings_in_date_range(
        self, instructor_id: int, start_date: date, end_date: date
    ) -> Dict[str, any]:
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
            bookings = (
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
                .all()
            )

            # Organize booking information
            bookings_by_date = {}

            for booking in bookings:
                date_str = booking.booking_date.isoformat()
                if date_str not in bookings_by_date:
                    bookings_by_date[date_str] = []

                bookings_by_date[date_str].append(
                    {
                        "start_time": booking.start_time,
                        "end_time": booking.end_time,
                    }
                )

            self.logger.info(f"Found {len(bookings)} bookings across {len(bookings_by_date)} dates")

            return {
                "bookings_by_date": bookings_by_date,
                "total_bookings": len(bookings),
            }

        except SQLAlchemyError as e:
            self.logger.error(f"Error getting bookings in range: {str(e)}")
            raise RepositoryException(f"Failed to get bookings: {str(e)}")

    # Slot Queries

    def get_week_slots(
        self, instructor_id: int, start_date: date, end_date: date
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
            return (
                self.db.query(AvailabilitySlot)
                .filter(
                    AvailabilitySlot.instructor_id == instructor_id,
                    AvailabilitySlot.specific_date >= start_date,
                    AvailabilitySlot.specific_date <= end_date,
                )
                .order_by(AvailabilitySlot.specific_date, AvailabilitySlot.start_time)
                .all()
            )
        except SQLAlchemyError as e:
            self.logger.error(f"Error getting week slots: {str(e)}")
            raise RepositoryException(f"Failed to get slots: {str(e)}")

    def get_slots_with_booking_status(
        self, instructor_id: int, target_date: date
    ) -> List[Dict[str, any]]:
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
            slots = (
                self.db.query(AvailabilitySlot)
                .filter(
                    AvailabilitySlot.instructor_id == instructor_id,
                    AvailabilitySlot.specific_date == target_date,
                )
                .all()
            )

            if not slots:
                return []

            # For each slot, check if there's an overlapping booking
            result = []
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
                        "id": slot.id,
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
        self, instructor_id: int, start_date: date, end_date: date
    ) -> List[Dict]:
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

            results = self.db.execute(
                query,
                {
                    "instructor_id": instructor_id,
                    "start_date": start_date,
                    "end_date": end_date,
                },
            )

            # Convert to list of dicts
            return [
                {
                    "date": row.specific_date,
                    "slot_id": row.slot_id,
                    "start_time": row.start_time,
                    "end_time": row.end_time,
                    "booking_status": row.booking_status,
                    "booking_id": row.booking_id,
                }
                for row in results
            ]

        except SQLAlchemyError as e:
            self.logger.error(f"Error getting week with status: {str(e)}")
            raise RepositoryException(f"Failed to get week status: {str(e)}")

    # Bulk Operations

    def bulk_create_slots(self, slots: List[Dict[str, any]]) -> int:
        """
        Bulk create slots using high-performance bulk_insert_mappings.

        Args:
            slots: List of slot dictionaries with instructor_id, specific_date, start_time, end_time

        Returns:
            Number of slots created
        """
        try:
            if not slots:
                return 0

            self.db.bulk_insert_mappings(AvailabilitySlot, slots)
            self.db.flush()
            return len(slots)

        except IntegrityError as e:
            self.logger.error(f"Integrity error bulk creating slots: {str(e)}")
            raise RepositoryException(f"Duplicate slots or invalid data: {str(e)}")
        except SQLAlchemyError as e:
            self.logger.error(f"Error bulk creating slots: {str(e)}")
            raise RepositoryException(f"Failed to bulk create slots: {str(e)}")

    def bulk_delete_slots(self, slot_ids: List[int]) -> int:
        """
        Bulk delete slots by IDs.

        Uses IN clause for efficient deletion.

        Args:
            slot_ids: List of slot IDs to delete

        Returns:
            Number of slots deleted
        """
        try:
            if not slot_ids:
                return 0

            result = (
                self.db.query(AvailabilitySlot)
                .filter(AvailabilitySlot.id.in_(slot_ids))
                .delete(synchronize_session=False)
            )
            self.db.flush()
            return result

        except SQLAlchemyError as e:
            self.logger.error(f"Error bulk deleting slots: {str(e)}")
            raise RepositoryException(f"Failed to delete slots: {str(e)}")

    def delete_slots_preserving_booked_times(
        self, instructor_id: int, week_dates: List[date], preserve_booked: bool = True
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
            return deleted_count

        except SQLAlchemyError as e:
            self.logger.error(f"Error deleting slots: {str(e)}")
            raise RepositoryException(f"Failed to delete slots: {str(e)}")
