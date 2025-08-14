# backend/app/repositories/bulk_operation_repository.py
"""
BulkOperation Repository for InstaInstru Platform

REFOCUSED: This repository provides validation support AND bulk operations for availability.

This repository has been cleaned to focus on validation queries and bulk operations
needed when performing bulk availability modifications. It provides ownership
validation, booking checks, and bulk creation operations.

Key responsibilities:
- Validate slot ownership before bulk operations
- Check for existing bookings that would conflict
- Perform bulk slot creation operations
- Retrieve slot data for validation purposes
- Support cache invalidation for bulk operations

Methods removed:
- slot_exists() → Use AvailabilityRepository
- count_slots_for_date() → Use AvailabilityRepository
- get_instructor_profile() → Use ConflictCheckerRepository
- get_week_slots() → Use WeekOperationRepository
- get_booked_slot_ids() → Use SlotManagerRepository
- slot_has_active_booking() → REMOVED (violates clean architecture)

For single slot CRUD operations, use AvailabilityRepository.
"""

import logging
from datetime import date, time
from typing import Dict, List, Optional, Tuple

from sqlalchemy import and_
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from ..core.exceptions import RepositoryException
from ..models.availability import AvailabilitySlot
from ..models.booking import Booking, BookingStatus
from .base_repository import BaseRepository

logger = logging.getLogger(__name__)


class BulkOperationRepository(BaseRepository[AvailabilitySlot]):
    """
    Repository for bulk operation validation and execution.

    This repository provides validation queries to ensure bulk operations
    are safe to perform, as well as the bulk operations themselves.
    """

    def __init__(self, db: Session):
        """Initialize with AvailabilitySlot model."""
        super().__init__(db, AvailabilitySlot)
        self.logger = logging.getLogger(__name__)

    # Ownership Validation

    def get_slot_for_instructor(self, slot_id: str, instructor_id: str) -> Optional[AvailabilitySlot]:
        """
        Get a slot only if it belongs to the instructor.

        Used to validate ownership before allowing bulk operations.

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

    # Booking Validation

    def has_bookings_on_date(self, instructor_id: str, target_date: date) -> bool:
        """
        Check if instructor has any bookings on a specific date.

        UPDATED: Simplified to check bookings directly without slot join.
        This aligns with clean architecture where bookings exist independently.

        Args:
            instructor_id: The instructor ID
            target_date: The date to check

        Returns:
            True if there are confirmed/completed bookings, False otherwise
        """
        try:
            count = (
                self.db.query(Booking)
                .filter(
                    and_(
                        Booking.instructor_id == instructor_id,
                        Booking.booking_date == target_date,
                        Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
                    )
                )
                .count()
            )
            return count > 0

        except SQLAlchemyError as e:
            self.logger.error(f"Error checking bookings: {str(e)}")
            raise RepositoryException(f"Failed to check bookings: {str(e)}")

    # Data Retrieval for Validation

    def get_slots_by_ids(self, slot_ids: List[str]) -> List[Tuple[str, date, time, time]]:
        """
        Get slots with their dates for validation and cache invalidation.

        Used when bulk operations need to validate multiple slots at once.

        Args:
            slot_ids: List of slot IDs to retrieve

        Returns:
            List of tuples (slot_id, specific_date, start_time, end_time)
        """
        try:
            results = (
                self.db.query(
                    AvailabilitySlot.id,
                    AvailabilitySlot.specific_date,
                    AvailabilitySlot.start_time,
                    AvailabilitySlot.end_time,
                )
                .filter(AvailabilitySlot.id.in_(slot_ids))
                .all()
            )

            return [(row.id, row.specific_date, row.start_time, row.end_time) for row in results]

        except SQLAlchemyError as e:
            self.logger.error(f"Error getting slots by IDs: {str(e)}")
            raise RepositoryException(f"Failed to get slots: {str(e)}")

    # Cache Support

    def get_unique_dates_from_operations(self, instructor_id: str, operation_dates: List[date]) -> List[date]:
        """
        Get unique dates that actually exist for cache invalidation.

        Used to determine which cache entries need invalidation after bulk operations.

        Args:
            instructor_id: The instructor ID
            operation_dates: List of dates from operations

        Returns:
            List of unique dates that exist in database
        """
        try:
            results = (
                self.db.query(AvailabilitySlot.specific_date)
                .filter(
                    AvailabilitySlot.instructor_id == instructor_id,
                    AvailabilitySlot.specific_date.in_(operation_dates),
                )
                .distinct()
                .all()
            )

            return [row.specific_date for row in results]

        except SQLAlchemyError as e:
            self.logger.error(f"Error getting unique dates: {str(e)}")
            raise RepositoryException(f"Failed to get dates: {str(e)}")

    # Bulk Operations

    def bulk_create_slots(self, slots: List[Dict[str, any]]) -> List[AvailabilitySlot]:
        """
        Create multiple slots efficiently.

        This is the primary bulk operation for creating multiple availability slots
        in a single database transaction.

        Args:
            slots: List of slot data dictionaries with instructor_id, specific_date, start_time, end_time

        Returns:
            List of created AvailabilitySlot objects

        Raises:
            RepositoryException: If creation fails due to duplicates or constraints
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
