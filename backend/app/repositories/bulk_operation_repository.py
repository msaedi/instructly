# backend/app/repositories/bulk_operation_repository.py
"""
BulkOperation Repository for InstaInstru Platform

Implements all data access operations for bulk availability operations,
based on the documented query patterns from strategic testing.

This repository handles:
- Slot retrieval and validation
- Availability management
- Booking conflict checks
- Bulk slot operations
- Cache invalidation support
- Week validation queries
"""

import logging
from datetime import date, time
from typing import Dict, List, Optional, Set, Tuple

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from ..core.exceptions import RepositoryException
from ..models.availability import AvailabilitySlot, InstructorAvailability
from ..models.booking import Booking, BookingStatus
from ..models.instructor import InstructorProfile
from .base_repository import BaseRepository

logger = logging.getLogger(__name__)


class BulkOperationRepository(BaseRepository[InstructorAvailability]):
    """
    Repository for bulk operation data access.

    Implements all 13 documented query patterns from strategic testing.
    Primary model is InstructorAvailability but queries across multiple tables.
    """

    def __init__(self, db: Session):
        """Initialize with InstructorAvailability model as primary."""
        super().__init__(db, InstructorAvailability)
        self.logger = logging.getLogger(__name__)

    # Slot Retrieval Queries

    def get_slots_by_ids(self, slot_ids: List[int]) -> List[Tuple[int, date, time, time]]:
        """
        Get slots with their dates for cache invalidation.

        Used when removing slots to determine which cache entries to invalidate.

        Args:
            slot_ids: List of slot IDs to retrieve

        Returns:
            List of tuples (slot_id, date, start_time, end_time)
        """
        try:
            results = (
                self.db.query(
                    AvailabilitySlot.id,
                    InstructorAvailability.date,
                    AvailabilitySlot.start_time,
                    AvailabilitySlot.end_time,
                )
                .join(InstructorAvailability, AvailabilitySlot.availability_id == InstructorAvailability.id)
                .filter(AvailabilitySlot.id.in_(slot_ids))
                .all()
            )

            return [(row.id, row.date, row.start_time, row.end_time) for row in results]

        except SQLAlchemyError as e:
            self.logger.error(f"Error getting slots by IDs: {str(e)}")
            raise RepositoryException(f"Failed to get slots: {str(e)}")

    def get_or_create_availability(
        self, instructor_id: int, target_date: date, is_cleared: bool = False
    ) -> InstructorAvailability:
        """
        Get existing availability or create new one for a date.

        Used in add operations to ensure availability entry exists.

        Args:
            instructor_id: The instructor ID
            target_date: The date to get/create availability for
            is_cleared: Initial cleared status if creating

        Returns:
            InstructorAvailability instance (existing or new)
        """
        try:
            availability = (
                self.db.query(InstructorAvailability)
                .filter(
                    InstructorAvailability.instructor_id == instructor_id,
                    InstructorAvailability.date == target_date,
                )
                .first()
            )

            if not availability:
                availability = InstructorAvailability(
                    instructor_id=instructor_id, date=target_date, is_cleared=is_cleared
                )
                self.db.add(availability)
                self.db.flush()
            else:
                # Update is_cleared if needed
                if availability.is_cleared and not is_cleared:
                    availability.is_cleared = False
                    self.db.flush()

            return availability

        except SQLAlchemyError as e:
            self.logger.error(f"Error getting/creating availability: {str(e)}")
            raise RepositoryException(f"Failed to manage availability: {str(e)}")

    # Booking Check Queries

    def has_bookings_on_date(self, availability_id: int) -> bool:
        """
        Check if any slots for this availability have bookings.

        Used to determine if auto-merge should be applied.

        Args:
            availability_id: The availability ID to check

        Returns:
            True if there are confirmed/completed bookings, False otherwise
        """
        try:
            count = (
                self.db.query(Booking)
                .join(AvailabilitySlot, Booking.availability_slot_id == AvailabilitySlot.id)
                .filter(
                    AvailabilitySlot.availability_id == availability_id,
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

            return {row.availability_slot_id for row in results}

        except SQLAlchemyError as e:
            self.logger.error(f"Error getting booked slot IDs: {str(e)}")
            raise RepositoryException(f"Failed to get booked slots: {str(e)}")

    def availability_has_bookings(self, availability_id: int) -> bool:
        """
        Check if an availability entry has any bookings.

        Alias for has_bookings_on_date for consistency.
        """
        return self.has_bookings_on_date(availability_id)

    # Week Validation Queries

    def get_week_slots(self, instructor_id: int, week_start: date, week_end: date) -> List[Dict[str, any]]:
        """
        Get all slots for a week for validation.

        Used in week validation to compare current vs saved state.

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
                    InstructorAvailability.date,
                    AvailabilitySlot.start_time,
                    AvailabilitySlot.end_time,
                )
                .join(InstructorAvailability, AvailabilitySlot.availability_id == InstructorAvailability.id)
                .filter(
                    InstructorAvailability.instructor_id == instructor_id,
                    InstructorAvailability.date >= week_start,
                    InstructorAvailability.date <= week_end,
                )
                .order_by(InstructorAvailability.date, AvailabilitySlot.start_time)
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

        Used for update/remove operations to verify ownership.

        Args:
            slot_id: The slot ID
            instructor_id: The instructor ID to verify ownership

        Returns:
            AvailabilitySlot if owned by instructor, None otherwise
        """
        try:
            return (
                self.db.query(AvailabilitySlot)
                .join(InstructorAvailability)
                .filter(
                    AvailabilitySlot.id == slot_id,
                    InstructorAvailability.instructor_id == instructor_id,
                )
                .first()
            )

        except SQLAlchemyError as e:
            self.logger.error(f"Error getting slot for instructor: {str(e)}")
            raise RepositoryException(f"Failed to get slot: {str(e)}")

    def slot_exists(self, availability_id: int, start_time: time, end_time: time) -> bool:
        """
        Check if a slot already exists for given time range.

        Used to prevent duplicate slots.

        Args:
            availability_id: The availability ID
            start_time: Slot start time
            end_time: Slot end time

        Returns:
            True if slot exists, False otherwise
        """
        try:
            exists = (
                self.db.query(AvailabilitySlot)
                .filter(
                    AvailabilitySlot.availability_id == availability_id,
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

    def count_slots_for_availability(self, availability_id: int) -> int:
        """
        Count remaining slots for an availability.

        Used after delete to check if availability should be cleared.

        Args:
            availability_id: The availability ID

        Returns:
            Number of slots
        """
        try:
            return self.db.query(AvailabilitySlot).filter(AvailabilitySlot.availability_id == availability_id).count()

        except SQLAlchemyError as e:
            self.logger.error(f"Error counting slots: {str(e)}")
            raise RepositoryException(f"Failed to count slots: {str(e)}")

    # Cache Support Queries

    def get_unique_dates_from_operations(self, instructor_id: int, operation_dates: List[date]) -> List[date]:
        """
        Get unique dates that actually exist for cache invalidation.

        Used to determine which cache entries to invalidate.

        Args:
            instructor_id: The instructor ID
            operation_dates: List of dates from operations

        Returns:
            List of unique dates that exist in database
        """
        try:
            results = (
                self.db.query(InstructorAvailability.date)
                .filter(
                    InstructorAvailability.instructor_id == instructor_id,
                    InstructorAvailability.date.in_(operation_dates),
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

        Used for batch insertion in bulk operations.

        Args:
            slots: List of slot data dictionaries

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

    def update_availability_cleared_status(self, availability_id: int, is_cleared: bool) -> bool:
        """
        Update the cleared status of an availability.

        Used when all slots are removed from a date.

        Args:
            availability_id: The availability ID
            is_cleared: New cleared status

        Returns:
            True if updated, False if not found
        """
        try:
            result = (
                self.db.query(InstructorAvailability)
                .filter(InstructorAvailability.id == availability_id)
                .update({"is_cleared": is_cleared})
            )
            self.db.flush()
            return result > 0

        except SQLAlchemyError as e:
            self.logger.error(f"Error updating cleared status: {str(e)}")
            raise RepositoryException(f"Failed to update status: {str(e)}")

    # Profile Query (might be shared with other repositories)

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
