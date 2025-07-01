# backend/app/repositories/availability_repository.py
"""
Availability Repository for InstaInstru Platform

Implements all data access operations for availability management,
based on the documented query patterns from strategic testing.

This repository handles:
- Week-based availability queries
- Date-specific availability operations
- Booking conflict checks
- Blackout date management
- Bulk operations for efficiency
- Complex joins and aggregations
"""

import logging
from datetime import date, time
from typing import Dict, List, Optional

from sqlalchemy import and_, func, or_, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from ..core.exceptions import RepositoryException
from ..models.availability import AvailabilitySlot, BlackoutDate, InstructorAvailability
from ..models.booking import Booking, BookingStatus
from .base_repository import BaseRepository

logger = logging.getLogger(__name__)


class AvailabilityRepository(BaseRepository[InstructorAvailability]):
    """
    Repository for availability management data access.

    Implements all 15+ documented query patterns from strategic testing.
    Handles complex queries involving availability, slots, and bookings.
    """

    def __init__(self, db: Session):
        """Initialize with InstructorAvailability model."""
        super().__init__(db, InstructorAvailability)
        self.logger = logging.getLogger(__name__)

    # Week and Date-based Queries

    def get_week_availability(
        self, instructor_id: int, start_date: date, end_date: date
    ) -> List[InstructorAvailability]:
        """
        Get availability entries for a week with eager loaded time slots.

        Used by get_week_availability service method.
        Orders by date for consistent results.
        """
        try:
            return (
                self.db.query(InstructorAvailability)
                .options(joinedload(InstructorAvailability.time_slots))
                .filter(
                    and_(
                        InstructorAvailability.instructor_id == instructor_id,
                        InstructorAvailability.date >= start_date,
                        InstructorAvailability.date <= end_date,
                    )
                )
                .order_by(InstructorAvailability.date)
                .all()
            )
        except SQLAlchemyError as e:
            self.logger.error(f"Error getting week availability: {str(e)}")
            raise RepositoryException(f"Failed to get week availability: {str(e)}")

    def get_availability_by_date(self, instructor_id: int, target_date: date) -> Optional[InstructorAvailability]:
        """
        Get availability for a specific date with time slots.

        Returns None if no availability found.
        """
        try:
            return (
                self.db.query(InstructorAvailability)
                .options(joinedload(InstructorAvailability.time_slots))
                .filter(
                    and_(
                        InstructorAvailability.instructor_id == instructor_id,
                        InstructorAvailability.date == target_date,
                    )
                )
                .first()
            )
        except SQLAlchemyError as e:
            self.logger.error(f"Error getting availability by date: {str(e)}")
            raise RepositoryException(f"Failed to get availability: {str(e)}")

    def get_or_create_availability(
        self, instructor_id: int, target_date: date, is_cleared: bool = False
    ) -> InstructorAvailability:
        """
        Get existing availability or create new one.

        Used when adding slots to ensure availability entry exists.
        Note: Does NOT commit, only flushes to get ID.
        """
        try:
            # Try to get existing
            availability = self.get_availability_by_date(instructor_id, target_date)

            if not availability:
                # Create new
                availability = InstructorAvailability(
                    instructor_id=instructor_id, date=target_date, is_cleared=is_cleared
                )
                self.db.add(availability)
                self.db.flush()

            return availability

        except SQLAlchemyError as e:
            self.logger.error(f"Error get/create availability: {str(e)}")
            raise RepositoryException(f"Failed to get/create availability: {str(e)}")

    # Booking-related Queries

    def get_booked_slots_in_range(self, instructor_id: int, start_date: date, end_date: date) -> List[Booking]:
        """
        Get all bookings within a date range for an instructor.

        Joins through availability slots to get booking information.
        Only returns confirmed/completed bookings.
        """
        try:
            return (
                self.db.query(Booking)
                .join(AvailabilitySlot, Booking.availability_slot_id == AvailabilitySlot.id)
                .join(InstructorAvailability, AvailabilitySlot.availability_id == InstructorAvailability.id)
                .filter(
                    and_(
                        Booking.instructor_id == instructor_id,
                        Booking.booking_date >= start_date,
                        Booking.booking_date <= end_date,
                        Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
                    )
                )
                .all()
            )
        except SQLAlchemyError as e:
            self.logger.error(f"Error getting booked slots: {str(e)}")
            raise RepositoryException(f"Failed to get booked slots: {str(e)}")

    def get_booked_slot_ids(self, instructor_id: int, target_date: date) -> List[int]:
        """
        Get IDs of slots that have bookings on a specific date.

        Used to preserve booked slots during updates.
        """
        try:
            results = (
                self.db.query(AvailabilitySlot.id)
                .join(InstructorAvailability)
                .join(Booking, Booking.availability_slot_id == AvailabilitySlot.id)
                .filter(
                    and_(
                        InstructorAvailability.instructor_id == instructor_id,
                        InstructorAvailability.date == target_date,
                        Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
                    )
                )
                .all()
            )

            return [id[0] for id in results]

        except SQLAlchemyError as e:
            self.logger.error(f"Error getting booked slot IDs: {str(e)}")
            raise RepositoryException(f"Failed to get booked slots: {str(e)}")

    def count_bookings_for_date(self, instructor_id: int, target_date: date) -> int:
        """
        Count confirmed/completed bookings for a specific date.

        Used to check if a date can be cleared.
        """
        try:
            return (
                self.db.query(Booking)
                .join(AvailabilitySlot, Booking.availability_slot_id == AvailabilitySlot.id)
                .join(InstructorAvailability, AvailabilitySlot.availability_id == InstructorAvailability.id)
                .filter(
                    and_(
                        InstructorAvailability.instructor_id == instructor_id,
                        InstructorAvailability.date == target_date,
                        Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
                    )
                )
                .count()
            )
        except SQLAlchemyError as e:
            self.logger.error(f"Error counting bookings: {str(e)}")
            raise RepositoryException(f"Failed to count bookings: {str(e)}")

    # Slot Management Queries

    def get_slots_by_availability_id(self, availability_id: int) -> List[AvailabilitySlot]:
        """
        Get all slots for an availability entry, ordered by start time.

        Simple query for slot retrieval.
        """
        try:
            return (
                self.db.query(AvailabilitySlot)
                .filter(AvailabilitySlot.availability_id == availability_id)
                .order_by(AvailabilitySlot.start_time)
                .all()
            )
        except SQLAlchemyError as e:
            self.logger.error(f"Error getting slots: {str(e)}")
            raise RepositoryException(f"Failed to get slots: {str(e)}")

    def slot_exists(self, availability_id: int, start_time: time, end_time: time) -> bool:
        """
        Check if an exact slot already exists.

        Prevents duplicate slot creation.
        """
        try:
            return (
                self.db.query(AvailabilitySlot)
                .filter(
                    and_(
                        AvailabilitySlot.availability_id == availability_id,
                        AvailabilitySlot.start_time == start_time,
                        AvailabilitySlot.end_time == end_time,
                    )
                )
                .first()
                is not None
            )
        except SQLAlchemyError as e:
            self.logger.error(f"Error checking slot existence: {str(e)}")
            raise RepositoryException(f"Failed to check slot: {str(e)}")

    def find_overlapping_slots(self, availability_id: int, start_time: time, end_time: time) -> List[AvailabilitySlot]:
        """
        Find slots that overlap with a given time range.

        Used for conflict detection when creating/updating slots.
        """
        try:
            return (
                self.db.query(AvailabilitySlot)
                .filter(
                    and_(
                        AvailabilitySlot.availability_id == availability_id,
                        or_(
                            # New slot starts during existing slot
                            and_(AvailabilitySlot.start_time <= start_time, AvailabilitySlot.end_time > start_time),
                            # New slot ends during existing slot
                            and_(AvailabilitySlot.start_time < end_time, AvailabilitySlot.end_time >= end_time),
                            # New slot completely contains existing slot
                            and_(AvailabilitySlot.start_time >= start_time, AvailabilitySlot.end_time <= end_time),
                        ),
                    )
                )
                .all()
            )
        except SQLAlchemyError as e:
            self.logger.error(f"Error finding overlapping slots: {str(e)}")
            raise RepositoryException(f"Failed to find overlaps: {str(e)}")

    def find_time_conflicts(
        self, instructor_id: int, target_date: date, start_time: time, end_time: time
    ) -> List[AvailabilitySlot]:
        """
        Find slots that conflict with a proposed time range.

        Checks across instructor and date for any time overlaps.
        """
        try:
            return (
                self.db.query(AvailabilitySlot)
                .join(InstructorAvailability)
                .filter(
                    and_(
                        InstructorAvailability.instructor_id == instructor_id,
                        InstructorAvailability.date == target_date,
                        # Time overlap check
                        AvailabilitySlot.start_time < end_time,
                        AvailabilitySlot.end_time > start_time,
                    )
                )
                .all()
            )
        except SQLAlchemyError as e:
            self.logger.error(f"Error finding time conflicts: {str(e)}")
            raise RepositoryException(f"Failed to find conflicts: {str(e)}")

    # Bulk Operations

    def delete_slots_except(self, instructor_id: int, target_date: date, except_ids: List[int]) -> int:
        """
        Delete all slots for a date except those in the exception list.

        Used to preserve booked slots while updating availability.
        Returns count of deleted slots.
        """
        try:
            query = (
                self.db.query(AvailabilitySlot)
                .join(InstructorAvailability)
                .filter(
                    and_(
                        InstructorAvailability.instructor_id == instructor_id,
                        InstructorAvailability.date == target_date,
                    )
                )
            )

            if except_ids:
                query = query.filter(~AvailabilitySlot.id.in_(except_ids))

            count = query.count()
            query.delete(synchronize_session=False)
            self.db.flush()

            return count

        except SQLAlchemyError as e:
            self.logger.error(f"Error deleting slots: {str(e)}")
            raise RepositoryException(f"Failed to delete slots: {str(e)}")

    def delete_non_booked_slots(self, availability_id: int, booked_slot_ids: List[int]) -> int:
        """
        Delete slots that don't have bookings for an availability.

        Alternative method using availability ID directly.
        """
        try:
            query = self.db.query(AvailabilitySlot).filter(AvailabilitySlot.availability_id == availability_id)

            if booked_slot_ids:
                query = query.filter(~AvailabilitySlot.id.in_(booked_slot_ids))

            return query.delete(synchronize_session=False)

        except SQLAlchemyError as e:
            self.logger.error(f"Error deleting non-booked slots: {str(e)}")
            raise RepositoryException(f"Failed to delete slots: {str(e)}")

    def bulk_create_availability(self, instructor_id: int, dates: List[date]) -> List[InstructorAvailability]:
        """
        Bulk create availability entries for multiple dates.

        Skips dates that already have entries.
        """
        try:
            # Check which dates already exist
            existing_dates = (
                self.db.query(InstructorAvailability.date)
                .filter(
                    and_(InstructorAvailability.instructor_id == instructor_id, InstructorAvailability.date.in_(dates))
                )
                .all()
            )

            existing_set = {d[0] for d in existing_dates}

            # Create only new ones
            new_entries = []
            for target_date in dates:
                if target_date not in existing_set:
                    entry = InstructorAvailability(instructor_id=instructor_id, date=target_date, is_cleared=False)
                    new_entries.append(entry)

            if new_entries:
                self.db.bulk_save_objects(new_entries)
                self.db.flush()

            return new_entries

        except SQLAlchemyError as e:
            self.logger.error(f"Error bulk creating availability: {str(e)}")
            raise RepositoryException(f"Failed to bulk create: {str(e)}")

    # Status Updates

    def update_cleared_status(self, instructor_id: int, target_date: date, is_cleared: bool) -> bool:
        """
        Update the cleared status for a specific date.

        Returns True if updated, False if not found.
        """
        try:
            result = (
                self.db.query(InstructorAvailability)
                .filter(
                    and_(
                        InstructorAvailability.instructor_id == instructor_id,
                        InstructorAvailability.date == target_date,
                    )
                )
                .update({"is_cleared": is_cleared})
            )

            self.db.flush()
            return result > 0

        except SQLAlchemyError as e:
            self.logger.error(f"Error updating cleared status: {str(e)}")
            raise RepositoryException(f"Failed to update status: {str(e)}")

    # Aggregate Queries

    def count_available_slots(self, instructor_id: int, start_date: date, end_date: date) -> int:
        """
        Count total available slots in a date range.

        Excludes cleared days.
        """
        try:
            return (
                self.db.query(AvailabilitySlot)
                .join(InstructorAvailability)
                .filter(
                    and_(
                        InstructorAvailability.instructor_id == instructor_id,
                        InstructorAvailability.date >= start_date,
                        InstructorAvailability.date <= end_date,
                        InstructorAvailability.is_cleared == False,
                    )
                )
                .count()
            )
        except SQLAlchemyError as e:
            self.logger.error(f"Error counting slots: {str(e)}")
            raise RepositoryException(f"Failed to count slots: {str(e)}")

    def get_availability_summary(self, instructor_id: int, start_date: date, end_date: date) -> Dict[str, int]:
        """
        Get summary of availability (slot counts per date).

        Uses raw SQL for optimal performance.
        Returns dict mapping date strings to slot counts.
        """
        try:
            query = text(
                """
                SELECT
                    ia.date,
                    COUNT(aslot.id) as slot_count
                FROM instructor_availability ia
                LEFT JOIN availability_slots aslot ON ia.id = aslot.availability_id
                WHERE
                    ia.instructor_id = :instructor_id
                    AND ia.date BETWEEN :start_date AND :end_date
                    AND ia.is_cleared = false
                GROUP BY ia.date
                ORDER BY ia.date
            """
            )

            result = self.db.execute(
                query, {"instructor_id": instructor_id, "start_date": start_date, "end_date": end_date}
            )

            return {row.date.isoformat(): row.slot_count for row in result}

        except SQLAlchemyError as e:
            self.logger.error(f"Error getting summary: {str(e)}")
            raise RepositoryException(f"Failed to get summary: {str(e)}")

    # Complex Queries

    def get_week_with_booking_status(self, instructor_id: int, start_date: date, end_date: date) -> List[Dict]:
        """
        Get week availability with booking status for each slot.

        Complex query that joins availability, slots, and bookings.
        Returns structured data for each slot with its booking status.
        """
        try:
            results = (
                self.db.query(
                    InstructorAvailability.date,
                    AvailabilitySlot.id.label("slot_id"),
                    AvailabilitySlot.start_time,
                    AvailabilitySlot.end_time,
                    Booking.status.label("booking_status"),
                    Booking.id.label("booking_id"),
                )
                .outerjoin(AvailabilitySlot, InstructorAvailability.id == AvailabilitySlot.availability_id)
                .outerjoin(
                    Booking,
                    and_(
                        AvailabilitySlot.id == Booking.availability_slot_id,
                        Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
                    ),
                )
                .filter(
                    and_(
                        InstructorAvailability.instructor_id == instructor_id,
                        InstructorAvailability.date >= start_date,
                        InstructorAvailability.date <= end_date,
                        InstructorAvailability.is_cleared == False,
                    )
                )
                .order_by(InstructorAvailability.date, AvailabilitySlot.start_time)
                .all()
            )

            # Convert to list of dicts for easier use
            return [
                {
                    "date": row.date,
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

    def get_instructor_availability_stats(self, instructor_id: int) -> Dict[str, any]:
        """
        Get aggregated statistics for instructor availability.

        Includes total slots, booked slots, date ranges, etc.
        """
        try:
            stats = (
                self.db.query(
                    func.count(AvailabilitySlot.id).label("total_slots"),
                    func.count(Booking.id).label("booked_slots"),
                    func.min(InstructorAvailability.date).label("earliest_availability"),
                    func.max(InstructorAvailability.date).label("latest_availability"),
                )
                .select_from(InstructorAvailability)
                .outerjoin(AvailabilitySlot, InstructorAvailability.id == AvailabilitySlot.availability_id)
                .outerjoin(
                    Booking,
                    and_(
                        AvailabilitySlot.id == Booking.availability_slot_id,
                        Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
                    ),
                )
                .filter(
                    and_(
                        InstructorAvailability.instructor_id == instructor_id,
                        InstructorAvailability.is_cleared == False,
                        InstructorAvailability.date >= date.today(),
                    )
                )
                .first()
            )

            return {
                "total_slots": stats.total_slots or 0,
                "booked_slots": stats.booked_slots or 0,
                "earliest_availability": stats.earliest_availability,
                "latest_availability": stats.latest_availability,
                "utilization_rate": ((stats.booked_slots / stats.total_slots * 100) if stats.total_slots > 0 else 0),
            }

        except SQLAlchemyError as e:
            self.logger.error(f"Error getting stats: {str(e)}")
            raise RepositoryException(f"Failed to get stats: {str(e)}")

    # Blackout Date Operations

    def get_future_blackout_dates(self, instructor_id: int) -> List[BlackoutDate]:
        """
        Get all future blackout dates for an instructor.

        Orders by date for consistent display.
        """
        try:
            return (
                self.db.query(BlackoutDate)
                .filter(and_(BlackoutDate.instructor_id == instructor_id, BlackoutDate.date >= date.today()))
                .order_by(BlackoutDate.date)
                .all()
            )
        except SQLAlchemyError as e:
            self.logger.error(f"Error getting blackout dates: {str(e)}")
            raise RepositoryException(f"Failed to get blackout dates: {str(e)}")

    def create_blackout_date(
        self, instructor_id: int, blackout_date: date, reason: Optional[str] = None
    ) -> BlackoutDate:
        """
        Create a new blackout date.

        Note: Does not check for duplicates - that's business logic.
        """
        try:
            blackout = BlackoutDate(instructor_id=instructor_id, date=blackout_date, reason=reason)
            self.db.add(blackout)
            self.db.flush()
            return blackout

        except IntegrityError as e:
            self.logger.error(f"Integrity error creating blackout: {str(e)}")
            raise RepositoryException(f"Blackout date already exists: {str(e)}")
        except SQLAlchemyError as e:
            self.logger.error(f"Error creating blackout: {str(e)}")
            raise RepositoryException(f"Failed to create blackout: {str(e)}")

    def delete_blackout_date(self, blackout_id: int, instructor_id: int) -> bool:
        """
        Delete a blackout date.

        Includes instructor_id for security validation.
        """
        try:
            result = (
                self.db.query(BlackoutDate)
                .filter(and_(BlackoutDate.id == blackout_id, BlackoutDate.instructor_id == instructor_id))
                .delete()
            )

            self.db.flush()
            return result > 0

        except SQLAlchemyError as e:
            self.logger.error(f"Error deleting blackout: {str(e)}")
            raise RepositoryException(f"Failed to delete blackout: {str(e)}")

    # Atomic Operations

    def create_availability_with_slots(
        self, instructor_id: int, target_date: date, slots: List[Dict[str, time]]
    ) -> InstructorAvailability:
        """
        Create availability entry with slots atomically.

        Used for specific date additions.
        slots should be list of dicts with 'start_time' and 'end_time'.
        """
        try:
            # Create availability
            availability = InstructorAvailability(instructor_id=instructor_id, date=target_date, is_cleared=False)
            self.db.add(availability)
            self.db.flush()

            # Create slots
            for slot_data in slots:
                slot = AvailabilitySlot(
                    availability_id=availability.id, start_time=slot_data["start_time"], end_time=slot_data["end_time"]
                )
                self.db.add(slot)

            self.db.flush()
            return availability

        except SQLAlchemyError as e:
            self.logger.error(f"Error creating availability with slots: {str(e)}")
            raise RepositoryException(f"Failed to create availability: {str(e)}")

    # Helper method overrides

    def _apply_eager_loading(self, query):
        """Override to include time_slots relationship by default."""
        return query.options(joinedload(InstructorAvailability.time_slots))
