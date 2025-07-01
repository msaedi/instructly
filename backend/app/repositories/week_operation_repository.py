# backend/app/repositories/week_operation_repository.py
"""
WeekOperation Repository for InstaInstru Platform

Implements all data access operations for week-based availability operations,
based on the documented query patterns from strategic testing.

This repository handles:
- Week booking queries with complex joins
- Bulk availability operations
- Slot management for date ranges
- Cleanup operations for empty entries
- Conflict checking support
- Pattern application queries
"""

import logging
from datetime import date, time
from typing import Dict, List, Set

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from ..core.exceptions import RepositoryException
from ..models.availability import AvailabilitySlot, InstructorAvailability
from ..models.booking import Booking, BookingStatus
from .base_repository import BaseRepository

logger = logging.getLogger(__name__)


class WeekOperationRepository(BaseRepository[InstructorAvailability]):
    """
    Repository for week operation data access.

    Implements all 15 documented query patterns from strategic testing.
    Primary model is InstructorAvailability but queries across multiple tables.
    """

    def __init__(self, db: Session):
        """Initialize with InstructorAvailability model as primary."""
        super().__init__(db, InstructorAvailability)
        self.logger = logging.getLogger(__name__)

    # Week Booking Queries

    def get_week_bookings_with_slots(self, instructor_id: int, week_dates: List[date]) -> Dict[str, any]:
        """
        Get all bookings in a target week with slot and availability information.

        This complex query joins Booking -> AvailabilitySlot -> InstructorAvailability
        to get complete booking information for the week.

        Args:
            instructor_id: The instructor ID
            week_dates: List of dates in the week (typically Monday-Sunday)

        Returns:
            Dictionary with:
                - booked_slot_ids: Set of slot IDs that are booked
                - availability_with_bookings: Set of availability IDs with bookings
                - booked_time_ranges_by_date: Dict of date -> list of time ranges
                - total_bookings: Total count of bookings
        """
        try:
            bookings = (
                self.db.query(
                    Booking.booking_date,
                    AvailabilitySlot.id.label("slot_id"),
                    AvailabilitySlot.start_time,
                    AvailabilitySlot.end_time,
                    InstructorAvailability.id.label("availability_id"),
                )
                .join(AvailabilitySlot, Booking.availability_slot_id == AvailabilitySlot.id)
                .join(
                    InstructorAvailability,
                    AvailabilitySlot.availability_id == InstructorAvailability.id,
                )
                .filter(
                    InstructorAvailability.instructor_id == instructor_id,
                    Booking.booking_date.in_(week_dates),
                    Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
                )
                .all()
            )

            # Process booking information
            booked_slot_ids = set()
            booked_availability_ids = set()
            booked_time_ranges_by_date = {}

            for booking in bookings:
                booked_slot_ids.add(booking.slot_id)
                booked_availability_ids.add(booking.availability_id)

                date_str = booking.booking_date.isoformat()
                if date_str not in booked_time_ranges_by_date:
                    booked_time_ranges_by_date[date_str] = []
                booked_time_ranges_by_date[date_str].append(
                    {"start_time": booking.start_time, "end_time": booking.end_time}
                )

            self.logger.info(f"Found {len(bookings)} booked slots in target week")

            return {
                "booked_slot_ids": booked_slot_ids,
                "availability_with_bookings": booked_availability_ids,
                "booked_time_ranges_by_date": booked_time_ranges_by_date,
                "total_bookings": len(bookings),
            }

        except SQLAlchemyError as e:
            self.logger.error(f"Error getting week bookings: {str(e)}")
            raise RepositoryException(f"Failed to get week bookings: {str(e)}")

    def get_bookings_in_date_range(self, instructor_id: int, start_date: date, end_date: date) -> Dict[str, any]:
        """
        Get all bookings in a date range for pattern operations.

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
            bookings = (
                self.db.query(
                    Booking.booking_date,
                    AvailabilitySlot.id.label("slot_id"),
                    AvailabilitySlot.start_time,
                    AvailabilitySlot.end_time,
                    InstructorAvailability.id.label("availability_id"),
                )
                .join(AvailabilitySlot, Booking.availability_slot_id == AvailabilitySlot.id)
                .join(
                    InstructorAvailability,
                    AvailabilitySlot.availability_id == InstructorAvailability.id,
                )
                .filter(
                    InstructorAvailability.instructor_id == instructor_id,
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

    # Availability Queries

    def get_availability_in_range(
        self, instructor_id: int, start_date: date, end_date: date
    ) -> List[InstructorAvailability]:
        """
        Bulk fetch all availability entries in a date range.

        Used for optimization in apply_pattern_to_date_range.

        Args:
            instructor_id: The instructor ID
            start_date: Start of range
            end_date: End of range

        Returns:
            List of InstructorAvailability entries with eager loaded slots
        """
        try:
            return (
                self.db.query(InstructorAvailability)
                .options(joinedload(InstructorAvailability.time_slots))
                .filter(
                    InstructorAvailability.instructor_id == instructor_id,
                    InstructorAvailability.date >= start_date,
                    InstructorAvailability.date <= end_date,
                )
                .all()
            )

        except SQLAlchemyError as e:
            self.logger.error(f"Error getting availability in range: {str(e)}")
            raise RepositoryException(f"Failed to get availability: {str(e)}")

    def get_or_create_availability(
        self, instructor_id: int, target_date: date, is_cleared: bool = False
    ) -> InstructorAvailability:
        """
        Get existing availability or create new one.

        Implements the get-or-create pattern for availability entries.

        Args:
            instructor_id: The instructor ID
            target_date: The date
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

            return availability

        except SQLAlchemyError as e:
            self.logger.error(f"Error get/create availability: {str(e)}")
            raise RepositoryException(f"Failed to manage availability: {str(e)}")

    def get_slots_with_booking_status(self, instructor_id: int, target_date: date) -> List[Dict[str, any]]:
        """
        Get all slots for a date with their booking status.

        Correctly handles one-way relationship by checking bookings table.

        Args:
            instructor_id: The instructor ID
            target_date: The date to check

        Returns:
            List of slot dictionaries with booking status
        """
        try:
            # First get all slots for the date
            slots = (
                self.db.query(AvailabilitySlot)
                .join(InstructorAvailability)
                .filter(
                    InstructorAvailability.instructor_id == instructor_id,
                    InstructorAvailability.date == target_date,
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

    def bulk_create_availability(self, entries: List[Dict[str, any]]) -> List[InstructorAvailability]:
        """
        Bulk create availability entries.

        Uses bulk_save_objects with return_defaults for efficiency.

        Args:
            entries: List of dictionaries with availability data

        Returns:
            List of created InstructorAvailability objects with IDs
        """
        try:
            availability_objects = [InstructorAvailability(**entry_data) for entry_data in entries]
            self.db.bulk_save_objects(availability_objects, return_defaults=True)
            self.db.flush()
            return availability_objects

        except IntegrityError as e:
            self.logger.error(f"Integrity error bulk creating availability: {str(e)}")
            raise RepositoryException(f"Duplicate availability entries: {str(e)}")
        except SQLAlchemyError as e:
            self.logger.error(f"Error bulk creating availability: {str(e)}")
            raise RepositoryException(f"Failed to bulk create: {str(e)}")

    def bulk_create_slots(self, slots: List[Dict[str, any]]) -> int:
        """
        Bulk create slots using high-performance bulk_insert_mappings.

        Args:
            slots: List of slot dictionaries

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

    def bulk_update_availability(self, updates: List[Dict[str, any]]) -> int:
        """
        Bulk update availability entries.

        Typically used to update is_cleared status on multiple entries.

        Args:
            updates: List of dicts with 'id' and fields to update

        Returns:
            Number of entries updated
        """
        try:
            if not updates:
                return 0

            self.db.bulk_update_mappings(InstructorAvailability, updates)
            self.db.flush()
            return len(updates)

        except SQLAlchemyError as e:
            self.logger.error(f"Error bulk updating availability: {str(e)}")
            raise RepositoryException(f"Failed to bulk update: {str(e)}")

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

    # Cleanup Operations

    def delete_non_booked_slots(self, instructor_id: int, week_dates: List[date], booked_slot_ids: Set[int]) -> int:
        """
        Delete all non-booked slots from a week.

        Used during week copy to clear slots that don't have bookings.

        Args:
            instructor_id: The instructor ID
            week_dates: List of dates in the week
            booked_slot_ids: Set of slot IDs to preserve

        Returns:
            Number of slots deleted
        """
        try:
            if booked_slot_ids:
                # Delete slots NOT in booked set
                result = (
                    self.db.query(AvailabilitySlot)
                    .filter(
                        AvailabilitySlot.availability_id.in_(
                            self.db.query(InstructorAvailability.id).filter(
                                InstructorAvailability.instructor_id == instructor_id,
                                InstructorAvailability.date.in_(week_dates),
                            )
                        ),
                        ~AvailabilitySlot.id.in_(booked_slot_ids),
                    )
                    .delete(synchronize_session=False)
                )
            else:
                # No bookings - delete all slots for the week
                result = (
                    self.db.query(AvailabilitySlot)
                    .filter(
                        AvailabilitySlot.availability_id.in_(
                            self.db.query(InstructorAvailability.id).filter(
                                InstructorAvailability.instructor_id == instructor_id,
                                InstructorAvailability.date.in_(week_dates),
                            )
                        )
                    )
                    .delete(synchronize_session=False)
                )

            self.db.flush()
            return result

        except SQLAlchemyError as e:
            self.logger.error(f"Error deleting non-booked slots: {str(e)}")
            raise RepositoryException(f"Failed to delete slots: {str(e)}")

    def delete_empty_availability_entries(self, instructor_id: int, week_dates: List[date]) -> int:
        """
        Delete availability entries that have no slots.

        Cleanup operation after deleting slots.

        Args:
            instructor_id: The instructor ID
            week_dates: List of dates to check

        Returns:
            Number of availability entries deleted
        """
        try:
            # Find availability IDs that still have slots
            subquery = (
                self.db.query(AvailabilitySlot.availability_id)
                .join(InstructorAvailability)
                .filter(
                    InstructorAvailability.instructor_id == instructor_id,
                    InstructorAvailability.date.in_(week_dates),
                )
                .distinct()
                .subquery()
            )

            # Delete availability entries not in the subquery
            result = (
                self.db.query(InstructorAvailability)
                .filter(
                    InstructorAvailability.instructor_id == instructor_id,
                    InstructorAvailability.date.in_(week_dates),
                    ~InstructorAvailability.id.in_(subquery),
                )
                .delete(synchronize_session=False)
            )

            self.db.flush()
            return result

        except SQLAlchemyError as e:
            self.logger.error(f"Error deleting empty availability: {str(e)}")
            raise RepositoryException(f"Failed to delete entries: {str(e)}")

    def delete_availability_without_slots(self, instructor_id: int, date_range: List[date]) -> int:
        """
        Delete availability entries that have no associated slots.

        More general version of delete_empty_availability_entries.

        Args:
            instructor_id: The instructor ID
            date_range: List of dates to check

        Returns:
            Number of entries deleted
        """
        try:
            # Subquery to find availability IDs with slots
            subquery = self.db.query(AvailabilitySlot.availability_id).distinct().subquery()

            # Delete entries without slots
            result = (
                self.db.query(InstructorAvailability)
                .filter(
                    InstructorAvailability.instructor_id == instructor_id,
                    InstructorAvailability.date.in_(date_range),
                    ~InstructorAvailability.id.in_(subquery),
                )
                .delete(synchronize_session=False)
            )

            self.db.flush()
            return result

        except SQLAlchemyError as e:
            self.logger.error(f"Error deleting availability without slots: {str(e)}")
            raise RepositoryException(f"Failed to cleanup: {str(e)}")

    # Validation Queries

    def slot_exists(self, availability_id: int, start_time: time, end_time: time) -> bool:
        """
        Check if a slot exists for the given time range.

        Used to avoid duplicate slot creation.

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

    def count_slots_for_availability(self, availability_id: int) -> int:
        """
        Count slots for an availability entry.

        Used to check if availability should be marked as cleared.

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
