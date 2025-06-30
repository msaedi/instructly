# backend/app/repositories/slot_manager_repository.py
"""
SlotManager Repository for InstaInstru Platform

Implements all data access operations for slot management,
based on the documented query patterns from strategic testing.

This repository handles:
- Slot CRUD operations
- Booking status checks
- Availability relationship queries
- Bulk slot operations
- Complex slot analysis queries
"""

import logging
from datetime import date
from typing import List, Optional, Set, Tuple

from sqlalchemy.orm import Session, joinedload

from ..core.exceptions import RepositoryException
from ..models.availability import AvailabilitySlot, InstructorAvailability
from ..models.booking import Booking, BookingStatus
from .base_repository import BaseRepository

logger = logging.getLogger(__name__)


class SlotManagerRepository(BaseRepository[AvailabilitySlot]):
    """
    Repository for slot management data access.

    Implements all 13 documented query patterns from strategic testing.
    """

    def __init__(self, db: Session):
        """Initialize with AvailabilitySlot model."""
        super().__init__(db, AvailabilitySlot)
        self.logger = logging.getLogger(__name__)

    # Core Availability Queries

    def get_availability_by_id(self, availability_id: int) -> Optional[InstructorAvailability]:
        """
        Get availability entry by ID.

        Used in create_slot to validate the availability exists.
        """
        try:
            return self.db.query(InstructorAvailability).filter(InstructorAvailability.id == availability_id).first()
        except Exception as e:
            self.logger.error(f"Error getting availability {availability_id}: {str(e)}")
            raise RepositoryException(f"Failed to get availability: {str(e)}")

    # Slot Existence and Retrieval

    def slot_exists(self, availability_id: int, start_time, end_time) -> bool:
        """
        Check if an exact slot already exists.

        Prevents duplicate slot creation.
        """
        try:
            return (
                self.db.query(AvailabilitySlot)
                .filter(
                    AvailabilitySlot.availability_id == availability_id,
                    AvailabilitySlot.start_time == start_time,
                    AvailabilitySlot.end_time == end_time,
                )
                .first()
                is not None
            )
        except Exception as e:
            self.logger.error(f"Error checking slot existence: {str(e)}")
            raise RepositoryException(f"Failed to check slot existence: {str(e)}")

    def get_slot_by_id(self, slot_id: int) -> Optional[AvailabilitySlot]:
        """
        Get a slot by ID with its availability relationship.

        Override of base method to include relationship.
        """
        try:
            return (
                self.db.query(AvailabilitySlot)
                .options(joinedload(AvailabilitySlot.availability))
                .filter(AvailabilitySlot.id == slot_id)
                .first()
            )
        except Exception as e:
            self.logger.error(f"Error getting slot {slot_id}: {str(e)}")
            raise RepositoryException(f"Failed to get slot: {str(e)}")

    # Booking Status Queries

    def slot_has_booking(self, slot_id: int) -> bool:
        """
        Check if a slot has any confirmed or completed bookings.

        Critical for preventing deletion/modification of booked slots.
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
        except Exception as e:
            self.logger.error(f"Error checking slot booking status: {str(e)}")
            raise RepositoryException(f"Failed to check booking status: {str(e)}")

    def get_booking_for_slot(self, slot_id: int) -> Optional[Booking]:
        """
        Get booking details for a slot if it exists.

        Used for detailed conflict information.
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
        except Exception as e:
            self.logger.error(f"Error getting booking for slot: {str(e)}")
            raise RepositoryException(f"Failed to get booking: {str(e)}")

    # Slot Collection Queries

    def get_slots_by_availability_ordered(self, availability_id: int) -> List[AvailabilitySlot]:
        """
        Get all slots for an availability entry ordered by start time.

        Used for merging operations and gap analysis.
        """
        try:
            return (
                self.db.query(AvailabilitySlot)
                .filter(AvailabilitySlot.availability_id == availability_id)
                .order_by(AvailabilitySlot.start_time)
                .all()
            )
        except Exception as e:
            self.logger.error(f"Error getting ordered slots: {str(e)}")
            raise RepositoryException(f"Failed to get slots: {str(e)}")

    def get_booked_slot_ids(self, slot_ids: List[int]) -> Set[int]:
        """
        Get IDs of slots that have bookings from a given list.

        Used for bulk operations to preserve booked slots.
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

            return {slot_id[0] for slot_id in booked_results}
        except Exception as e:
            self.logger.error(f"Error getting booked slot IDs: {str(e)}")
            raise RepositoryException(f"Failed to get booked slots: {str(e)}")

    # Counting and Aggregate Queries

    def count_slots_for_availability(self, availability_id: int) -> int:
        """
        Count remaining slots for an availability entry.

        Used after deletion to check if availability should be cleared.
        """
        try:
            return self.db.query(AvailabilitySlot).filter(AvailabilitySlot.availability_id == availability_id).count()
        except Exception as e:
            self.logger.error(f"Error counting slots: {str(e)}")
            raise RepositoryException(f"Failed to count slots: {str(e)}")

    def availability_has_bookings(self, availability_id: int) -> bool:
        """
        Check if any slots in an availability entry have bookings.

        Used to determine if auto-merge is safe.
        """
        try:
            return (
                self.db.query(Booking)
                .join(AvailabilitySlot, Booking.availability_slot_id == AvailabilitySlot.id)
                .filter(
                    AvailabilitySlot.availability_id == availability_id,
                    Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
                )
                .count()
                > 0
            )
        except Exception as e:
            self.logger.error(f"Error checking availability bookings: {str(e)}")
            raise RepositoryException(f"Failed to check bookings: {str(e)}")

    def count_bookings_for_slots(self, slot_ids: List[int]) -> int:
        """
        Count total bookings for a list of slots.

        Used for validation and statistics.
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
        except Exception as e:
            self.logger.error(f"Error counting bookings: {str(e)}")
            raise RepositoryException(f"Failed to count bookings: {str(e)}")

    # Complex Queries

    def get_slots_for_instructor_date(self, instructor_id: int, target_date: date) -> List[AvailabilitySlot]:
        """
        Get all slots for an instructor on a specific date.

        Used for gap analysis and daily views.
        """
        try:
            return (
                self.db.query(AvailabilitySlot)
                .join(InstructorAvailability)
                .filter(
                    InstructorAvailability.instructor_id == instructor_id,
                    InstructorAvailability.date == target_date,
                )
                .order_by(AvailabilitySlot.start_time)
                .all()
            )
        except Exception as e:
            self.logger.error(f"Error getting slots for date: {str(e)}")
            raise RepositoryException(f"Failed to get slots: {str(e)}")

    def get_slots_with_booking_status(
        self, availability_id: int
    ) -> List[Tuple[AvailabilitySlot, Optional[BookingStatus]]]:
        """
        Get slots with their booking status for optimization analysis.

        Returns tuples of (slot, booking_status) where status is None if not booked.
        """
        try:
            # Get all slots
            slots = self.get_slots_by_availability_ordered(availability_id)

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

        except Exception as e:
            self.logger.error(f"Error getting slots with status: {str(e)}")
            raise RepositoryException(f"Failed to get slot status: {str(e)}")

    def get_ordered_slots_for_gap_analysis(self, instructor_id: int, target_date: date) -> List[AvailabilitySlot]:
        """
        Get slots ordered for gap analysis between consecutive slots.

        Specifically for finding gaps in availability.
        """
        # This is the same as get_slots_for_instructor_date
        # but kept separate for semantic clarity
        return self.get_slots_for_instructor_date(instructor_id, target_date)

    # Bulk Operations Support

    def delete_slots_except(self, availability_id: int, except_ids: List[int]) -> int:
        """
        Delete all slots for an availability except those in the list.

        Used when preserving booked slots during updates.

        Returns:
            Number of slots deleted
        """
        try:
            query = self.db.query(AvailabilitySlot).filter(AvailabilitySlot.availability_id == availability_id)

            if except_ids:
                query = query.filter(~AvailabilitySlot.id.in_(except_ids))

            count = query.count()
            query.delete(synchronize_session=False)
            self.db.flush()

            return count

        except Exception as e:
            self.logger.error(f"Error deleting slots: {str(e)}")
            raise RepositoryException(f"Failed to delete slots: {str(e)}")

    # Helper method overrides

    def _apply_eager_loading(self, query):
        """Override to include availability relationship by default."""
        return query.options(joinedload(AvailabilitySlot.availability))
