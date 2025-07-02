# backend/app/repositories/bulk_operation_repository.py
"""
BulkOperation Repository for InstaInstru Platform

UPDATED FOR WORK STREAM #10: Single-table availability design.

This repository now works with the simplified single-table design where
AvailabilitySlot contains both date and time information. Methods dealing
with InstructorAvailability have been removed or transformed.

Key changes:
- No more InstructorAvailability operations
- No more is_cleared status management
- Parameters changed from availability_id to instructor_id + date
- Simplified queries without complex joins
"""

import logging
from datetime import date, time
from typing import Dict, List, Optional, Set, Tuple

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from ..core.exceptions import RepositoryException
from ..models.availability import AvailabilitySlot
from ..models.booking import Booking, BookingStatus
from ..models.instructor import InstructorProfile
from .base_repository import BaseRepository

logger = logging.getLogger(__name__)


class BulkOperationRepository(BaseRepository[AvailabilitySlot]):
    """
    Repository for bulk operation data access.

    Works with the single-table design where AvailabilitySlot
    contains instructor_id, date, start_time, and end_time.
    """

    def __init__(self, db: Session):
        """Initialize with AvailabilitySlot model."""
        super().__init__(db, AvailabilitySlot)
        self.logger = logging.getLogger(__name__)

    # Slot Retrieval Queries

    def get_slots_by_ids(self, slot_ids: List[int]) -> List[Tuple[int, date, time, time]]:
        """
        Get slots with their dates for cache invalidation.

        Simplified without InstructorAvailability join.

        Args:
            slot_ids: List of slot IDs to retrieve

        Returns:
            List of tuples (slot_id, date, start_time, end_time)
        """
        try:
            results = (
                self.db.query(
                    AvailabilitySlot.id,
                    AvailabilitySlot.date,
                    AvailabilitySlot.start_time,
                    AvailabilitySlot.end_time,
                )
                .filter(AvailabilitySlot.id.in_(slot_ids))
                .all()
            )

            return [(row.id, row.date, row.start_time, row.end_time) for row in results]

        except SQLAlchemyError as e:
            self.logger.error(f"Error getting slots by IDs: {str(e)}")
            raise RepositoryException(f"Failed to get slots: {str(e)}")

    # Booking Check Queries

    def has_bookings_on_date(self, instructor_id: int, target_date: date) -> bool:
        """
        Check if any slots on a date have bookings.

        Updated for single-table design with instructor_id and date.

        Args:
            instructor_id: The instructor ID
            target_date: The date to check

        Returns:
            True if there are confirmed/completed bookings, False otherwise
        """
        try:
            count = (
                self.db.query(Booking)
                .join(AvailabilitySlot, Booking.availability_slot_id == AvailabilitySlot.id)
                .filter(
                    AvailabilitySlot.instructor_id == instructor_id,
                    AvailabilitySlot.date == target_date,
                    Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
                )
                .count()
            )
            return count > 0

        except SQLAlchemyError as e:
            self.logger.error(f"Error checking bookings: {str(e)}")
            raise RepositoryException(f"Failed to check bookings: {str(e)}")

    def slot_has_active_booking(self, slot_id: int) -> bool:
        """
        Check if a specific slot has active bookings.

        Used to validate if slot can be removed/updated.

        Args:
            slot_id: The slot ID to check

        Returns:
            True if slot has active bookings, False otherwise
        """
        try:
            booking = (
                self.db.query(Booking)
                .filter(
                    Booking.availability_slot_id == slot_id,
                    Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
                )
                .first()
            )
            return booking is not None

        except SQLAlchemyError as e:
            self.logger.error(f"Error checking slot booking: {str(e)}")
            raise RepositoryException(f"Failed to check slot booking: {str(e)}")

    def get_booked_slot_ids(self, slot_ids: List[int]) -> Set[int]:
        """
        Get IDs of slots that have active bookings.

        Used for bulk validation of remove operations.

        Args:
            slot_ids: List of slot IDs to check

        Returns:
            Set of slot IDs that have bookings
        """
        try:
            results = (
                self.db.query(Booking.availability_slot_id)
                .filter(
                    Booking.availability_slot_id.in_(slot_ids),
                    Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
                )
                .distinct()
                .all()
            )

            return {row.availability_slot_id for row in results if row.availability_slot_id is not None}

        except SQLAlchemyError as e:
            self.logger.error(f"Error getting booked slot IDs: {str(e)}")
            raise RepositoryException(f"Failed to get booked slots: {str(e)}")

    # Week Validation Queries

    def get_week_slots(self, instructor_id: int, week_start: date, week_end: date) -> List[Dict[str, any]]:
        """
        Get all slots for a week for validation.

        Simplified without InstructorAvailability join.

        Args:
            instructor_id: The instructor ID
            week_start: Start of week (Monday)
            week_end: End of week (Sunday)

        Returns:
            List of slot data organized by date
        """
        try:
            results = (
                self.db.query(
                    AvailabilitySlot.id,
                    AvailabilitySlot.date,
                    AvailabilitySlot.start_time,
                    AvailabilitySlot.end_time,
                )
                .filter(
                    AvailabilitySlot.instructor_id == instructor_id,
                    AvailabilitySlot.date >= week_start,
                    AvailabilitySlot.date <= week_end,
                )
                .order_by(AvailabilitySlot.date, AvailabilitySlot.start_time)
                .all()
            )

            return [
                {
                    "id": row.id,
                    "date": row.date,
                    "start_time": row.start_time,
                    "end_time": row.end_time,
                }
                for row in results
            ]

        except SQLAlchemyError as e:
            self.logger.error(f"Error getting week slots: {str(e)}")
            raise RepositoryException(f"Failed to get week slots: {str(e)}")

    # Ownership and Validation Queries

    def get_slot_for_instructor(self, slot_id: int, instructor_id: int) -> Optional[AvailabilitySlot]:
        """
        Get a slot only if it belongs to the instructor.

        Simplified without InstructorAvailability join.

        Args:
            slot_id: The slot ID
            instructor_id: The instructor ID to verify ownership

        Returns:
            AvailabilitySlot if owned by instructor, None otherwise
        """
        try:
            return (
                self.db.query(AvailabilitySlot)
                .filter(
                    AvailabilitySlot.id == slot_id,
                    AvailabilitySlot.instructor_id == instructor_id,
                )
                .first()
            )

        except SQLAlchemyError as e:
            self.logger.error(f"Error getting slot for instructor: {str(e)}")
            raise RepositoryException(f"Failed to get slot: {str(e)}")

    def slot_exists(self, instructor_id: int, target_date: date, start_time: time, end_time: time) -> bool:
        """
        Check if a slot already exists for given time range.

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

    # Slot Count Queries

    def count_slots_for_date(self, instructor_id: int, target_date: date) -> int:
        """
        Count remaining slots for a date.

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

    # Cache Support Queries

    def get_unique_dates_from_operations(self, instructor_id: int, operation_dates: List[date]) -> List[date]:
        """
        Get unique dates that actually exist for cache invalidation.

        Simplified to query AvailabilitySlot directly.

        Args:
            instructor_id: The instructor ID
            operation_dates: List of dates from operations

        Returns:
            List of unique dates that exist in database
        """
        try:
            results = (
                self.db.query(AvailabilitySlot.date)
                .filter(
                    AvailabilitySlot.instructor_id == instructor_id,
                    AvailabilitySlot.date.in_(operation_dates),
                )
                .distinct()
                .all()
            )

            return [row.date for row in results]

        except SQLAlchemyError as e:
            self.logger.error(f"Error getting unique dates: {str(e)}")
            raise RepositoryException(f"Failed to get dates: {str(e)}")

    # Bulk Operations

    def bulk_create_slots(self, slots: List[Dict[str, any]]) -> List[AvailabilitySlot]:
        """
        Create multiple slots efficiently.

        Updated for single-table design with instructor_id and date in each slot.

        Args:
            slots: List of slot data dictionaries with instructor_id, date, start_time, end_time

        Returns:
            List of created AvailabilitySlot objects
        """
        try:
            slot_objects = [AvailabilitySlot(**slot_data) for slot_data in slots]
            self.db.bulk_save_objects(slot_objects, return_defaults=True)
            self.db.flush()
            return slot_objects

        except IntegrityError as e:
            self.logger.error(f"Integrity error in bulk create: {str(e)}")
            raise RepositoryException(f"Duplicate slot or constraint violation: {str(e)}")
        except SQLAlchemyError as e:
            self.logger.error(f"Error bulk creating slots: {str(e)}")
            raise RepositoryException(f"Failed to bulk create slots: {str(e)}")

    # Profile Query (unchanged)

    def get_instructor_profile(self, instructor_id: int) -> Optional[InstructorProfile]:
        """
        Get instructor profile for validation.

        Used for various validation checks.

        Args:
            instructor_id: The instructor ID (user_id)

        Returns:
            InstructorProfile if exists, None otherwise
        """
        try:
            return self.db.query(InstructorProfile).filter(InstructorProfile.user_id == instructor_id).first()

        except SQLAlchemyError as e:
            self.logger.error(f"Error getting instructor profile: {str(e)}")
            raise RepositoryException(f"Failed to get profile: {str(e)}")
