# backend/app/repositories/slot_manager_repository.py
"""
SlotManager Repository for InstaInstru Platform

UPDATED FOR WORK STREAM #10: Single-table availability design.
CLEANED: Removed duplicate methods (slot_exists, delete_slots_except, count_slots_for_date)

This repository handles slot-specific queries that require booking awareness,
optimization analysis, and gap detection. For basic slot CRUD operations,
use AvailabilityRepository instead.

Key responsibilities:
- Booking status queries for slots
- Slot optimization and gap analysis
- Complex slot queries with booking information
- Ordered slot retrieval for analysis

Methods removed (use AvailabilityRepository):
- slot_exists()
- delete_slots_except()
- count_slots_for_date()
"""

import logging
from datetime import date
from typing import List, Optional, Set, Tuple

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..core.exceptions import RepositoryException
from ..models.availability import AvailabilitySlot
from ..models.booking import Booking, BookingStatus
from .base_repository import BaseRepository

logger = logging.getLogger(__name__)


class SlotManagerRepository(BaseRepository[AvailabilitySlot]):
    """
    Repository for slot management data access with booking awareness.

    Focuses on slot-specific operations that require understanding of
    booking relationships, optimization opportunities, and gap analysis.
    Basic slot CRUD operations should use AvailabilityRepository.
    """

    def __init__(self, db: Session):
        """Initialize with AvailabilitySlot model."""
        super().__init__(db, AvailabilitySlot)
        self.logger = logging.getLogger(__name__)

    # Slot Retrieval

    def get_slot_by_id(self, slot_id: int) -> Optional[AvailabilitySlot]:
        """
        Get a slot by ID.

        Simplified - no relationship loading needed in single-table design.

        Args:
            slot_id: The slot ID

        Returns:
            The slot or None if not found
        """
        try:
            return self.db.query(AvailabilitySlot).filter(AvailabilitySlot.id == slot_id).first()
        except SQLAlchemyError as e:
            self.logger.error(f"Error getting slot {slot_id}: {str(e)}")
            raise RepositoryException(f"Failed to get slot: {str(e)}")

    # Booking Status Queries

    def slot_has_booking(self, slot_id: int) -> bool:
        """
        Check if a slot has any confirmed or completed bookings.

        Critical for preventing deletion/modification of booked slots.

        Args:
            slot_id: The slot ID

        Returns:
            True if slot has bookings, False otherwise
        """
        try:
            return (
                self.db.query(Booking)
                .filter(
                    Booking.availability_slot_id == slot_id,
                    Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
                )
                .first()
                is not None
            )
        except SQLAlchemyError as e:
            self.logger.error(f"Error checking slot booking status: {str(e)}")
            raise RepositoryException(f"Failed to check booking status: {str(e)}")

    def get_booking_for_slot(self, slot_id: int) -> Optional[Booking]:
        """
        Get booking details for a slot if it exists.

        Used for detailed conflict information.

        Args:
            slot_id: The slot ID

        Returns:
            The booking or None if not found
        """
        try:
            return (
                self.db.query(Booking)
                .filter(
                    Booking.availability_slot_id == slot_id,
                    Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
                )
                .first()
            )
        except SQLAlchemyError as e:
            self.logger.error(f"Error getting booking for slot: {str(e)}")
            raise RepositoryException(f"Failed to get booking: {str(e)}")

    # Slot Collection Queries

    def get_slots_by_date_ordered(self, instructor_id: int, target_date: date) -> List[AvailabilitySlot]:
        """
        Get all slots for a date ordered by start time.

        Replaces get_slots_by_availability_ordered in single-table design.

        Args:
            instructor_id: The instructor ID
            target_date: The date

        Returns:
            List of slots ordered by start time
        """
        try:
            return (
                self.db.query(AvailabilitySlot)
                .filter(
                    AvailabilitySlot.instructor_id == instructor_id,
                    AvailabilitySlot.date == target_date,
                )
                .order_by(AvailabilitySlot.start_time)
                .all()
            )
        except SQLAlchemyError as e:
            self.logger.error(f"Error getting ordered slots: {str(e)}")
            raise RepositoryException(f"Failed to get slots: {str(e)}")

    def get_booked_slot_ids(self, slot_ids: List[int]) -> Set[int]:
        """
        Get IDs of slots that have bookings from a given list.

        Used for bulk operations to preserve booked slots.

        Args:
            slot_ids: List of slot IDs to check

        Returns:
            Set of slot IDs that have bookings
        """
        try:
            if not slot_ids:
                return set()

            booked_results = (
                self.db.query(Booking.availability_slot_id)
                .filter(
                    Booking.availability_slot_id.in_(slot_ids),
                    Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
                )
                .all()
            )

            return {slot_id[0] for slot_id in booked_results if slot_id[0] is not None}
        except SQLAlchemyError as e:
            self.logger.error(f"Error getting booked slot IDs: {str(e)}")
            raise RepositoryException(f"Failed to get booked slots: {str(e)}")

    # Counting and Aggregate Queries

    def date_has_bookings(self, instructor_id: int, target_date: date) -> bool:
        """
        Check if any slots on a date have bookings.

        Replaces availability_has_bookings in single-table design.

        Args:
            instructor_id: The instructor ID
            target_date: The date

        Returns:
            True if any slots have bookings, False otherwise
        """
        try:
            return (
                self.db.query(Booking)
                .join(AvailabilitySlot, Booking.availability_slot_id == AvailabilitySlot.id)
                .filter(
                    AvailabilitySlot.instructor_id == instructor_id,
                    AvailabilitySlot.date == target_date,
                    Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
                )
                .count()
                > 0
            )
        except SQLAlchemyError as e:
            self.logger.error(f"Error checking date bookings: {str(e)}")
            raise RepositoryException(f"Failed to check bookings: {str(e)}")

    def count_bookings_for_slots(self, slot_ids: List[int]) -> int:
        """
        Count total bookings for a list of slots.

        Used for validation and statistics.

        Args:
            slot_ids: List of slot IDs

        Returns:
            Number of bookings
        """
        try:
            if not slot_ids:
                return 0

            return (
                self.db.query(Booking)
                .filter(
                    Booking.availability_slot_id.in_(slot_ids),
                    Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
                )
                .count()
            )
        except SQLAlchemyError as e:
            self.logger.error(f"Error counting bookings: {str(e)}")
            raise RepositoryException(f"Failed to count bookings: {str(e)}")

    # Complex Queries

    def get_slots_for_instructor_date(self, instructor_id: int, target_date: date) -> List[AvailabilitySlot]:
        """
        Get all slots for an instructor on a specific date.

        Simplified query without InstructorAvailability join.

        Args:
            instructor_id: The instructor ID
            target_date: The date

        Returns:
            List of slots ordered by start time
        """
        try:
            return (
                self.db.query(AvailabilitySlot)
                .filter(
                    AvailabilitySlot.instructor_id == instructor_id,
                    AvailabilitySlot.date == target_date,
                )
                .order_by(AvailabilitySlot.start_time)
                .all()
            )
        except SQLAlchemyError as e:
            self.logger.error(f"Error getting slots for date: {str(e)}")
            raise RepositoryException(f"Failed to get slots: {str(e)}")

    def get_slots_with_booking_status(
        self, instructor_id: int, target_date: date
    ) -> List[Tuple[AvailabilitySlot, Optional[BookingStatus]]]:
        """
        Get slots with their booking status for optimization analysis.

        Updated for single-table design with instructor_id and date.

        Args:
            instructor_id: The instructor ID
            target_date: The date

        Returns:
            List of tuples (slot, booking_status) where status is None if not booked
        """
        try:
            # Get all slots for the date
            slots = self.get_slots_by_date_ordered(instructor_id, target_date)

            if not slots:
                return []

            # Get booking statuses
            slot_ids = [s.id for s in slots]
            bookings = (
                self.db.query(Booking.availability_slot_id, Booking.status)
                .filter(
                    Booking.availability_slot_id.in_(slot_ids),
                    Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
                )
                .all()
            )

            # Create mapping
            booking_map = {booking[0]: booking[1] for booking in bookings}

            # Return slots with their status
            return [(slot, booking_map.get(slot.id)) for slot in slots]

        except SQLAlchemyError as e:
            self.logger.error(f"Error getting slots with status: {str(e)}")
            raise RepositoryException(f"Failed to get slot status: {str(e)}")

    def get_ordered_slots_for_gap_analysis(self, instructor_id: int, target_date: date) -> List[AvailabilitySlot]:
        """
        Get slots ordered for gap analysis between consecutive slots.

        Specifically for finding gaps in availability.

        Args:
            instructor_id: The instructor ID
            target_date: The date

        Returns:
            List of slots ordered by start time
        """
        # This is the same as get_slots_for_instructor_date
        # but kept separate for semantic clarity
        return self.get_slots_for_instructor_date(instructor_id, target_date)
