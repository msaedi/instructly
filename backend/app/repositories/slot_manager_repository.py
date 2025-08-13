# backend/app/repositories/slot_manager_repository.py
"""
SlotManager Repository for InstaInstru Platform

UPDATED FOR CLEAN ARCHITECTURE: Pure availability operations.

This repository handles slot-specific queries for availability management
without any booking concerns. All booking-related methods have been removed.

Key responsibilities:
- Slot CRUD operations
- Ordered slot retrieval for merging
- Date-based slot queries
- Gap analysis support

Methods removed:
- slot_has_booking()
- get_booking_for_slot()
- get_slots_with_booking_status()
- get_booked_slot_ids()
- count_bookings_for_slots()
- date_has_bookings()
"""

import logging
from datetime import date
from typing import List, Optional

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..core.exceptions import RepositoryException
from ..models.availability import AvailabilitySlot
from .base_repository import BaseRepository

logger = logging.getLogger(__name__)


class SlotManagerRepository(BaseRepository[AvailabilitySlot]):
    """
    Repository for slot management data access.

    Focuses on pure availability slot operations without any
    booking awareness. For booking-related queries, use BookingRepository.
    """

    def __init__(self, db: Session):
        """Initialize with AvailabilitySlot model."""
        super().__init__(db, AvailabilitySlot)
        self.logger = logging.getLogger(__name__)

    # Slot Retrieval

    def get_slot_by_id(self, slot_id: str) -> Optional[AvailabilitySlot]:
        """
        Get a slot by ID.

        Simple retrieval for slot data.

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

    # Slot Collection Queries

    def get_slots_by_date_ordered(self, instructor_id: str, target_date: date) -> List[AvailabilitySlot]:
        """
        Get all slots for a date ordered by start time.

        Used for slot merging and gap analysis.

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
                    AvailabilitySlot.specific_date == target_date,
                )
                .order_by(AvailabilitySlot.start_time)
                .all()
            )
        except SQLAlchemyError as e:
            self.logger.error(f"Error getting ordered slots: {str(e)}")
            raise RepositoryException(f"Failed to get slots: {str(e)}")

    def get_slots_for_instructor_date(self, instructor_id: str, target_date: date) -> List[AvailabilitySlot]:
        """
        Get all slots for an instructor on a specific date.

        Alias for get_slots_by_date_ordered for semantic clarity.

        Args:
            instructor_id: The instructor ID
            target_date: The date

        Returns:
            List of slots ordered by start time
        """
        return self.get_slots_by_date_ordered(instructor_id, target_date)

    def get_ordered_slots_for_gap_analysis(self, instructor_id: str, target_date: date) -> List[AvailabilitySlot]:
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

    def count_slots_for_date(self, instructor_id: str, target_date: date) -> int:
        """
        Count the number of slots for an instructor on a date.

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
                    AvailabilitySlot.specific_date == target_date,
                )
                .count()
            )
        except SQLAlchemyError as e:
            self.logger.error(f"Error counting slots: {str(e)}")
            raise RepositoryException(f"Failed to count slots: {str(e)}")

    def get_slots_in_date_range(self, instructor_id: str, start_date: date, end_date: date) -> List[AvailabilitySlot]:
        """
        Get all slots for an instructor within a date range.

        Args:
            instructor_id: The instructor ID
            start_date: Range start date
            end_date: Range end date

        Returns:
            List of slots ordered by date and start time
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
            self.logger.error(f"Error getting slots in date range: {str(e)}")
            raise RepositoryException(f"Failed to get slots: {str(e)}")

    def delete_slots_for_date(self, instructor_id: str, target_date: date) -> int:
        """
        Delete all slots for an instructor on a specific date.

        Args:
            instructor_id: The instructor ID
            target_date: The date

        Returns:
            Number of slots deleted
        """
        try:
            count = (
                self.db.query(AvailabilitySlot)
                .filter(
                    AvailabilitySlot.instructor_id == instructor_id,
                    AvailabilitySlot.specific_date == target_date,
                )
                .delete()
            )
            self.db.flush()
            return count
        except SQLAlchemyError as e:
            self.logger.error(f"Error deleting slots for date: {str(e)}")
            raise RepositoryException(f"Failed to delete slots: {str(e)}")

    # Bulk Operations

    def bulk_create_slots(self, slots_data: List[dict]) -> List[AvailabilitySlot]:
        """
        Bulk create multiple slots.

        Args:
            slots_data: List of slot data dictionaries

        Returns:
            List of created slots
        """
        try:
            slots = [AvailabilitySlot(**data) for data in slots_data]
            self.db.bulk_save_objects(slots, return_defaults=True)
            self.db.flush()
            return slots
        except SQLAlchemyError as e:
            self.logger.error(f"Error bulk creating slots: {str(e)}")
            raise RepositoryException(f"Failed to bulk create slots: {str(e)}")

    def bulk_delete_slots(self, slot_ids: List[int]) -> int:
        """
        Bulk delete multiple slots by ID.

        Args:
            slot_ids: List of slot IDs to delete

        Returns:
            Number of slots deleted
        """
        try:
            if not slot_ids:
                return 0

            count = (
                self.db.query(AvailabilitySlot)
                .filter(AvailabilitySlot.id.in_(slot_ids))
                .delete(synchronize_session=False)
            )
            self.db.flush()
            return count
        except SQLAlchemyError as e:
            self.logger.error(f"Error bulk deleting slots: {str(e)}")
            raise RepositoryException(f"Failed to bulk delete slots: {str(e)}")

    def refresh_slots(self, slots: List[AvailabilitySlot]) -> None:
        """Refresh slot objects with latest DB state."""
        self.db.flush()
        for slot in slots:
            self.db.refresh(slot)
