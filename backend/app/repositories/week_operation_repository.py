# backend/app/repositories/week_operation_repository.py
"""
WeekOperation Repository for InstaInstru Platform

UPDATED FOR WORK STREAM #10: Single-table availability design.

This repository now works with the simplified single-table design where
AvailabilitySlot contains both date and time information. The complex
two-table operations have been removed, resulting in MUCH simpler code.

Key simplifications:
- No more InstructorAvailability operations
- No more empty entry cleanup
- Direct slot queries without complex joins
- No more two-step processes
"""

import logging
from datetime import date, time
from typing import Dict, List, Set

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
    contains instructor_id, date, start_time, and end_time.
    """

    def __init__(self, db: Session):
        """Initialize with AvailabilitySlot model."""
        super().__init__(db, AvailabilitySlot)
        self.logger = logging.getLogger(__name__)

    # Week Booking Queries

    def get_week_bookings_with_slots(self, instructor_id: int, week_dates: List[date]) -> Dict[str, any]:
        """
        Get all bookings in a target week.

        Simplified query without complex joins through InstructorAvailability.

        Args:
            instructor_id: The instructor ID
            week_dates: List of dates in the week (typically Monday-Sunday)

        Returns:
            Dictionary with:
                - booked_slot_ids: Set of slot IDs that are booked
                - booked_time_ranges_by_date: Dict of date -> list of time ranges
                - total_bookings: Total count of bookings
        """
        try:
            # Direct query on bookings - no complex joins needed!
            bookings = (
                self.db.query(
                    Booking.booking_date,
                    Booking.availability_slot_id.label("slot_id"),
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
            booked_slot_ids = set()
            booked_time_ranges_by_date = {}

            for booking in bookings:
                if booking.slot_id:  # Some bookings might not have slot_id
                    booked_slot_ids.add(booking.slot_id)

                date_str = booking.booking_date.isoformat()
                if date_str not in booked_time_ranges_by_date:
                    booked_time_ranges_by_date[date_str] = []
                booked_time_ranges_by_date[date_str].append(
                    {"start_time": booking.start_time, "end_time": booking.end_time}
                )

            self.logger.info(f"Found {len(bookings)} booked slots in target week")

            return {
                "booked_slot_ids": booked_slot_ids,
                "booked_time_ranges_by_date": booked_time_ranges_by_date,
                "total_bookings": len(bookings),
            }

        except SQLAlchemyError as e:
            self.logger.error(f"Error getting week bookings: {str(e)}")
            raise RepositoryException(f"Failed to get week bookings: {str(e)}")

    def get_bookings_in_date_range(self, instructor_id: int, start_date: date, end_date: date) -> Dict[str, any]:
        """
        Get all bookings in a date range for pattern operations.

        Simplified without complex joins.

        Args:
            instructor_id: The instructor ID
            start_date: Start of date range
            end_date: End of date range

        Returns:
            Dictionary with:
                - bookings_by_date: Dict of date -> list of booking info
                - booked_slot_ids: Set of all booked slot IDs
                - total_bookings: Total count of bookings
        """
        try:
            # Direct query on bookings
            bookings = (
                self.db.query(
                    Booking.booking_date,
                    Booking.availability_slot_id.label("slot_id"),
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
            booked_slot_ids = set()

            for booking in bookings:
                date_str = booking.booking_date.isoformat()
                if date_str not in bookings_by_date:
                    bookings_by_date[date_str] = []

                bookings_by_date[date_str].append(
                    {
                        "slot_id": booking.slot_id,
                        "start_time": booking.start_time,
                        "end_time": booking.end_time,
                    }
                )
                if booking.slot_id:
                    booked_slot_ids.add(booking.slot_id)

            self.logger.info(f"Found {len(bookings)} bookings across {len(bookings_by_date)} dates")

            return {
                "bookings_by_date": bookings_by_date,
                "booked_slot_ids": booked_slot_ids,
                "total_bookings": len(bookings),
            }

        except SQLAlchemyError as e:
            self.logger.error(f"Error getting bookings in range: {str(e)}")
            raise RepositoryException(f"Failed to get bookings: {str(e)}")

    # Slot Queries

    def get_week_slots(self, instructor_id: int, start_date: date, end_date: date) -> List[AvailabilitySlot]:
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
                    AvailabilitySlot.date >= start_date,
                    AvailabilitySlot.date <= end_date,
                )
                .order_by(AvailabilitySlot.date, AvailabilitySlot.start_time)
                .all()
            )
        except SQLAlchemyError as e:
            self.logger.error(f"Error getting week slots: {str(e)}")
            raise RepositoryException(f"Failed to get slots: {str(e)}")

    def get_slots_with_booking_status(self, instructor_id: int, target_date: date) -> List[Dict[str, any]]:
        """
        Get all slots for a date with their booking status.

        Simplified query without InstructorAvailability join.

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
                    AvailabilitySlot.date == target_date,
                )
                .all()
            )

            if not slots:
                return []

            # Get booked slot IDs
            slot_ids = [s.id for s in slots]
            booked_results = (
                self.db.query(Booking.availability_slot_id)
                .filter(
                    Booking.availability_slot_id.in_(slot_ids),
                    Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
                )
                .all()
            )
            booked_slot_ids = {row.availability_slot_id for row in booked_results}

            # Return slot info with booking status
            return [
                {
                    "id": slot.id,
                    "start_time": slot.start_time,
                    "end_time": slot.end_time,
                    "is_booked": slot.id in booked_slot_ids,
                }
                for slot in slots
            ]

        except SQLAlchemyError as e:
            self.logger.error(f"Error getting slots with status: {str(e)}")
            raise RepositoryException(f"Failed to get slots: {str(e)}")

    # Bulk Operations

    def bulk_create_slots(self, slots: List[Dict[str, any]]) -> int:
        """
        Bulk create slots using high-performance bulk_insert_mappings.

        Args:
            slots: List of slot dictionaries with instructor_id, date, start_time, end_time

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

    def delete_slots_by_dates(self, instructor_id: int, dates: List[date]) -> int:
        """
        Delete all slots for specific dates.

        Direct deletion in single-table design.

        Args:
            instructor_id: The instructor ID
            dates: List of dates to clear

        Returns:
            Number of slots deleted
        """
        try:
            if not dates:
                return 0

            result = (
                self.db.query(AvailabilitySlot)
                .filter(
                    AvailabilitySlot.instructor_id == instructor_id,
                    AvailabilitySlot.date.in_(dates),
                )
                .delete(synchronize_session=False)
            )
            self.db.flush()
            return result

        except SQLAlchemyError as e:
            self.logger.error(f"Error deleting slots by dates: {str(e)}")
            raise RepositoryException(f"Failed to delete slots: {str(e)}")

    def delete_non_booked_slots(self, instructor_id: int, week_dates: List[date], booked_slot_ids: Set[int]) -> int:
        """
        Delete all non-booked slots from a week.

        Simplified without InstructorAvailability joins.

        Args:
            instructor_id: The instructor ID
            week_dates: List of dates in the week
            booked_slot_ids: Set of slot IDs to preserve

        Returns:
            Number of slots deleted
        """
        try:
            query = self.db.query(AvailabilitySlot).filter(
                AvailabilitySlot.instructor_id == instructor_id,
                AvailabilitySlot.date.in_(week_dates),
            )

            if booked_slot_ids:
                # Delete slots NOT in booked set
                query = query.filter(~AvailabilitySlot.id.in_(booked_slot_ids))

            result = query.delete(synchronize_session=False)
            self.db.flush()
            return result

        except SQLAlchemyError as e:
            self.logger.error(f"Error deleting non-booked slots: {str(e)}")
            raise RepositoryException(f"Failed to delete slots: {str(e)}")

    # Validation Queries

    def slot_exists(self, instructor_id: int, target_date: date, start_time: time, end_time: time) -> bool:
        """
        Check if a slot exists for the given time range.

        Updated for single-table design with instructor_id and date.

        Args:
            instructor_id: The instructor ID
            target_date: The date
            start_time: Slot start time
            end_time: Slot end time

        Returns:
            True if slot exists, False otherwise
        """
        try:
            exists = (
                self.db.query(AvailabilitySlot)
                .filter(
                    AvailabilitySlot.instructor_id == instructor_id,
                    AvailabilitySlot.date == target_date,
                    AvailabilitySlot.start_time == start_time,
                    AvailabilitySlot.end_time == end_time,
                )
                .first()
                is not None
            )
            return exists

        except SQLAlchemyError as e:
            self.logger.error(f"Error checking slot existence: {str(e)}")
            raise RepositoryException(f"Failed to check slot: {str(e)}")

    def count_slots_for_date(self, instructor_id: int, target_date: date) -> int:
        """
        Count slots for a specific date.

        Replaces count_slots_for_availability in single-table design.

        Args:
            instructor_id: The instructor ID
            target_date: The date

        Returns:
            Number of slots
        """
        try:
            return (
                self.db.query(AvailabilitySlot)
                .filter(
                    AvailabilitySlot.instructor_id == instructor_id,
                    AvailabilitySlot.date == target_date,
                )
                .count()
            )

        except SQLAlchemyError as e:
            self.logger.error(f"Error counting slots: {str(e)}")
            raise RepositoryException(f"Failed to count slots: {str(e)}")

    def check_time_conflicts(
        self, date: date, time_ranges: List[Dict[str, time]], booked_ranges: List[Dict[str, time]]
    ) -> List[Dict[str, any]]:
        """
        Check for time conflicts between ranges.

        This is primarily business logic but included as it was documented
        in the query patterns. Processes in memory rather than in database.

        Args:
            date: The date being checked (for context)
            time_ranges: List of proposed time ranges
            booked_ranges: List of existing booked ranges

        Returns:
            List of conflicts found
        """
        conflicts = []

        for proposed in time_ranges:
            for booked in booked_ranges:
                # Check if ranges overlap
                if proposed["start_time"] < booked["end_time"] and proposed["end_time"] > booked["start_time"]:
                    conflicts.append(
                        {
                            "proposed_start": proposed["start_time"],
                            "proposed_end": proposed["end_time"],
                            "booked_start": booked["start_time"],
                            "booked_end": booked["end_time"],
                            "date": date,
                        }
                    )

        return conflicts
