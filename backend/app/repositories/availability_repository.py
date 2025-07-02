# backend/app/repositories/availability_repository.py
"""
Availability Repository for InstaInstru Platform

UPDATED FOR WORK STREAM #10: Single-table availability design.

This repository now works with the simplified single-table design where
AvailabilitySlot contains both date and time information. The complex
two-table design (InstructorAvailability + AvailabilitySlots) has been
removed to prevent bugs and simplify operations.

Key changes:
- No more InstructorAvailability table
- No more is_cleared flag
- No more two-step operations
- Direct slot queries without joins
- Mental model: Has slots = available, No slots = not available
"""

import logging
from datetime import date, time
from typing import Dict, List, Optional

from sqlalchemy import and_, func, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from ..core.exceptions import RepositoryException
from ..models.availability import AvailabilitySlot, BlackoutDate
from ..models.booking import Booking, BookingStatus
from .base_repository import BaseRepository

logger = logging.getLogger(__name__)


class AvailabilityRepository(BaseRepository[AvailabilitySlot]):
    """
    Repository for availability management data access.

    Works with the single-table design where AvailabilitySlot
    contains instructor_id, date, start_time, and end_time.
    """

    def __init__(self, db: Session):
        """Initialize with AvailabilitySlot model."""
        super().__init__(db, AvailabilitySlot)
        self.logger = logging.getLogger(__name__)

    # Week and Date-based Queries

    def get_week_availability(self, instructor_id: int, start_date: date, end_date: date) -> List[AvailabilitySlot]:
        """
        Get all availability slots for a week.

        With single-table design, this is now a simple query without joins.

        Args:
            instructor_id: The instructor ID
            start_date: Start of date range
            end_date: End of date range

        Returns:
            List of availability slots ordered by date and start time
        """
        try:
            return (
                self.db.query(AvailabilitySlot)
                .filter(
                    and_(
                        AvailabilitySlot.instructor_id == instructor_id,
                        AvailabilitySlot.date >= start_date,
                        AvailabilitySlot.date <= end_date,
                    )
                )
                .order_by(AvailabilitySlot.date, AvailabilitySlot.start_time)
                .all()
            )
        except SQLAlchemyError as e:
            self.logger.error(f"Error getting week availability: {str(e)}")
            raise RepositoryException(f"Failed to get week availability: {str(e)}")

    def get_slots_by_date(self, instructor_id: int, target_date: date) -> List[AvailabilitySlot]:
        """
        Get all slots for a specific date.

        Simple query in single-table design.

        Args:
            instructor_id: The instructor ID
            target_date: The date to query

        Returns:
            List of slots ordered by start time
        """
        try:
            return (
                self.db.query(AvailabilitySlot)
                .filter(
                    and_(
                        AvailabilitySlot.instructor_id == instructor_id,
                        AvailabilitySlot.date == target_date,
                    )
                )
                .order_by(AvailabilitySlot.start_time)
                .all()
            )
        except SQLAlchemyError as e:
            self.logger.error(f"Error getting slots by date: {str(e)}")
            raise RepositoryException(f"Failed to get slots: {str(e)}")

    # Booking-related Queries

    def get_booked_slots_in_range(self, instructor_id: int, start_date: date, end_date: date) -> List[Booking]:
        """
        Get all bookings within a date range for an instructor.

        With single-table design, we query the Booking table directly
        without complex joins.

        Args:
            instructor_id: The instructor ID
            start_date: Start of date range
            end_date: End of date range

        Returns:
            List of confirmed/completed bookings
        """
        try:
            return (
                self.db.query(Booking)
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

        Args:
            instructor_id: The instructor ID
            target_date: The date to check

        Returns:
            List of slot IDs that have bookings
        """
        try:
            results = (
                self.db.query(Booking.availability_slot_id)
                .filter(
                    and_(
                        Booking.instructor_id == instructor_id,
                        Booking.booking_date == target_date,
                        Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
                        Booking.availability_slot_id.isnot(None),
                    )
                )
                .all()
            )

            return [id[0] for id in results if id[0] is not None]

        except SQLAlchemyError as e:
            self.logger.error(f"Error getting booked slot IDs: {str(e)}")
            raise RepositoryException(f"Failed to get booked slots: {str(e)}")

    def count_bookings_for_date(self, instructor_id: int, target_date: date) -> int:
        """
        Count confirmed/completed bookings for a specific date.

        Direct query on Booking table in single-table design.

        Args:
            instructor_id: The instructor ID
            target_date: The date to check

        Returns:
            Number of bookings
        """
        try:
            return (
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
        except SQLAlchemyError as e:
            self.logger.error(f"Error counting bookings: {str(e)}")
            raise RepositoryException(f"Failed to count bookings: {str(e)}")

    # Slot Management Queries

    def get_availability_slot_with_details(self, slot_id: int) -> Optional[AvailabilitySlot]:
        """
        Get an availability slot by ID.

        In single-table design, the slot contains all needed information
        (instructor_id, date, times) so no relationship loading needed.

        Args:
            slot_id: The availability slot ID

        Returns:
            The slot or None if not found
        """
        try:
            return self.db.query(AvailabilitySlot).filter(AvailabilitySlot.id == slot_id).first()
        except SQLAlchemyError as e:
            self.logger.error(f"Error getting availability slot details: {str(e)}")
            raise RepositoryException(f"Failed to get availability slot: {str(e)}")

    def slot_exists(self, instructor_id: int, target_date: date, start_time: time, end_time: time) -> bool:
        """
        Check if an exact slot already exists.

        Updated for single-table design with instructor_id and date parameters.

        Args:
            instructor_id: The instructor ID
            target_date: The date
            start_time: Start time
            end_time: End time

        Returns:
            True if slot exists, False otherwise
        """
        try:
            return (
                self.db.query(AvailabilitySlot)
                .filter(
                    and_(
                        AvailabilitySlot.instructor_id == instructor_id,
                        AvailabilitySlot.date == target_date,
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

    def find_time_conflicts(
        self, instructor_id: int, target_date: date, start_time: time, end_time: time
    ) -> List[AvailabilitySlot]:
        """
        Find slots that conflict with a proposed time range.

        Direct query in single-table design.

        Args:
            instructor_id: The instructor ID
            target_date: The date
            start_time: Proposed start time
            end_time: Proposed end time

        Returns:
            List of conflicting slots
        """
        try:
            return (
                self.db.query(AvailabilitySlot)
                .filter(
                    and_(
                        AvailabilitySlot.instructor_id == instructor_id,
                        AvailabilitySlot.date == target_date,
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

    def create_slot(self, instructor_id: int, target_date: date, start_time: time, end_time: time) -> AvailabilitySlot:
        """
        Create a new availability slot.

        Direct creation in single-table design.

        Args:
            instructor_id: The instructor ID
            target_date: The date
            start_time: Start time
            end_time: End time

        Returns:
            Created slot

        Raises:
            RepositoryException: If creation fails
        """
        try:
            slot = AvailabilitySlot(
                instructor_id=instructor_id,
                date=target_date,
                start_time=start_time,
                end_time=end_time,
            )
            self.db.add(slot)
            self.db.flush()
            return slot
        except IntegrityError as e:
            if "unique_instructor_date_time_slot" in str(e):
                raise RepositoryException("Slot already exists for this time")
            raise RepositoryException(f"Failed to create slot: {str(e)}")
        except SQLAlchemyError as e:
            self.logger.error(f"Error creating slot: {str(e)}")
            raise RepositoryException(f"Failed to create slot: {str(e)}")

    # Bulk Operations

    def delete_slots_except(self, instructor_id: int, target_date: date, except_ids: List[int]) -> int:
        """
        Delete all slots for a date except those in the exception list.

        Simplified query in single-table design.

        Args:
            instructor_id: The instructor ID
            target_date: The date
            except_ids: List of slot IDs to preserve

        Returns:
            Number of deleted slots
        """
        try:
            query = self.db.query(AvailabilitySlot).filter(
                and_(
                    AvailabilitySlot.instructor_id == instructor_id,
                    AvailabilitySlot.date == target_date,
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

    def delete_slots_by_date(self, instructor_id: int, target_date: date) -> int:
        """
        Delete all slots for a specific date.

        Args:
            instructor_id: The instructor ID
            target_date: The date

        Returns:
            Number of deleted slots
        """
        try:
            count = (
                self.db.query(AvailabilitySlot)
                .filter(
                    and_(
                        AvailabilitySlot.instructor_id == instructor_id,
                        AvailabilitySlot.date == target_date,
                    )
                )
                .delete(synchronize_session=False)
            )
            self.db.flush()
            return count
        except SQLAlchemyError as e:
            self.logger.error(f"Error deleting slots by date: {str(e)}")
            raise RepositoryException(f"Failed to delete slots: {str(e)}")

    # Aggregate Queries

    def count_available_slots(self, instructor_id: int, start_date: date, end_date: date) -> int:
        """
        Count total available slots in a date range.

        Simple count in single-table design.

        Args:
            instructor_id: The instructor ID
            start_date: Start of range
            end_date: End of range

        Returns:
            Number of slots
        """
        try:
            return (
                self.db.query(AvailabilitySlot)
                .filter(
                    and_(
                        AvailabilitySlot.instructor_id == instructor_id,
                        AvailabilitySlot.date >= start_date,
                        AvailabilitySlot.date <= end_date,
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

        Simplified query for single-table design.

        Args:
            instructor_id: The instructor ID
            start_date: Start of range
            end_date: End of range

        Returns:
            Dict mapping date strings to slot counts
        """
        try:
            query = text(
                """
                SELECT
                    date,
                    COUNT(*) as slot_count
                FROM availability_slots
                WHERE
                    instructor_id = :instructor_id
                    AND date BETWEEN :start_date AND :end_date
                GROUP BY date
                ORDER BY date
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

        Simplified join in single-table design.

        Args:
            instructor_id: The instructor ID
            start_date: Start of range
            end_date: End of range

        Returns:
            List of dicts with slot and booking information
        """
        try:
            results = (
                self.db.query(
                    AvailabilitySlot.date,
                    AvailabilitySlot.id.label("slot_id"),
                    AvailabilitySlot.start_time,
                    AvailabilitySlot.end_time,
                    Booking.status.label("booking_status"),
                    Booking.id.label("booking_id"),
                )
                .outerjoin(
                    Booking,
                    and_(
                        AvailabilitySlot.id == Booking.availability_slot_id,
                        Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
                    ),
                )
                .filter(
                    and_(
                        AvailabilitySlot.instructor_id == instructor_id,
                        AvailabilitySlot.date >= start_date,
                        AvailabilitySlot.date <= end_date,
                    )
                )
                .order_by(AvailabilitySlot.date, AvailabilitySlot.start_time)
                .all()
            )

            # Convert to list of dicts
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

        Simplified queries in single-table design.

        Args:
            instructor_id: The instructor ID

        Returns:
            Dict with availability statistics
        """
        try:
            stats = (
                self.db.query(
                    func.count(AvailabilitySlot.id).label("total_slots"),
                    func.count(Booking.id).label("booked_slots"),
                    func.min(AvailabilitySlot.date).label("earliest_availability"),
                    func.max(AvailabilitySlot.date).label("latest_availability"),
                )
                .outerjoin(
                    Booking,
                    and_(
                        AvailabilitySlot.id == Booking.availability_slot_id,
                        Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
                    ),
                )
                .filter(
                    and_(
                        AvailabilitySlot.instructor_id == instructor_id,
                        AvailabilitySlot.date >= date.today(),
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

    # Blackout Date Operations (unchanged)

    def get_future_blackout_dates(self, instructor_id: int) -> List[BlackoutDate]:
        """
        Get all future blackout dates for an instructor.

        Args:
            instructor_id: The instructor ID

        Returns:
            List of blackout dates ordered by date
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

        Args:
            instructor_id: The instructor ID
            blackout_date: The date to blackout
            reason: Optional reason

        Returns:
            Created blackout date

        Raises:
            RepositoryException: If creation fails
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

        Args:
            blackout_id: The blackout ID
            instructor_id: The instructor ID (for security)

        Returns:
            True if deleted, False if not found
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
