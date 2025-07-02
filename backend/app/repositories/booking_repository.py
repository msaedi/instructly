# backend/app/repositories/booking_repository.py
"""
Booking Repository for InstaInstru Platform

Implements all data access operations for booking management,
based on the documented query patterns from strategic testing.

This repository handles:
- Booking CRUD operations
- User-specific booking queries (student/instructor)
- Booking statistics and counting
- Conflict checking
- Date-based queries
- Booking relationships eager loading
"""

import logging
from datetime import date, time
from typing import Dict, List, Optional

from sqlalchemy.orm import Session, joinedload

from ..core.exceptions import RepositoryException
from ..models.booking import Booking, BookingStatus
from ..models.user import UserRole
from .base_repository import BaseRepository

logger = logging.getLogger(__name__)


class BookingRepository(BaseRepository[Booking]):
    """
    Repository for booking data access.

    Implements all 11 documented query patterns from strategic testing.
    """

    def __init__(self, db: Session):
        """Initialize with Booking model."""
        super().__init__(db, Booking)
        self.logger = logging.getLogger(__name__)

    # Slot Booking Queries

    def get_booking_for_slot(self, slot_id: int, active_only: bool = True) -> Optional[Booking]:
        """
        Get booking for a specific availability slot.

        Used to check if a slot is already booked.

        Args:
            slot_id: The availability slot ID
            active_only: Whether to only return confirmed/completed bookings

        Returns:
            The booking if found, None otherwise
        """
        try:
            query = self.db.query(Booking).filter(Booking.availability_slot_id == slot_id)

            if active_only:
                query = query.filter(Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]))

            return query.first()
        except Exception as e:
            self.logger.error(f"Error getting booking for slot {slot_id}: {str(e)}")
            raise RepositoryException(f"Failed to get booking for slot: {str(e)}")

    # User Booking Queries

    def get_bookings(
        self,
        user_id: Optional[int] = None,
        user_role: Optional[str] = None,
        status: Optional[BookingStatus] = None,
        date_start: Optional[date] = None,
        date_end: Optional[date] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Booking]:
        """
        Get bookings with flexible filtering and pagination.

        Generic method supporting various filter combinations.

        Args:
            user_id: Filter by user ID
            user_role: Role of the user (student/instructor)
            status: Filter by booking status
            date_start: Filter by date range start
            date_end: Filter by date range end
            skip: Number of records to skip
            limit: Maximum records to return

        Returns:
            List of bookings matching criteria
        """
        try:
            query = self.db.query(Booking).options(
                joinedload(Booking.student),
                joinedload(Booking.instructor),
                joinedload(Booking.service),
            )

            # Apply user filter based on role
            if user_id and user_role:
                if user_role == UserRole.STUDENT:
                    query = query.filter(Booking.student_id == user_id)
                elif user_role == UserRole.INSTRUCTOR:
                    query = query.filter(Booking.instructor_id == user_id)

            # Apply status filter
            if status:
                query = query.filter(Booking.status == status)

            # Apply date range filter
            if date_start:
                query = query.filter(Booking.booking_date >= date_start)
            if date_end:
                query = query.filter(Booking.booking_date <= date_end)

            # Order by date and time descending
            query = query.order_by(Booking.booking_date.desc(), Booking.start_time.desc())

            # Apply pagination
            return query.offset(skip).limit(limit).all()

        except Exception as e:
            self.logger.error(f"Error getting bookings: {str(e)}")
            raise RepositoryException(f"Failed to get bookings: {str(e)}")

    def get_student_bookings(
        self,
        student_id: int,
        status: Optional[BookingStatus] = None,
        upcoming_only: bool = False,
        limit: Optional[int] = None,
    ) -> List[Booking]:
        """
        Get bookings for a specific student.

        Args:
            student_id: The student's user ID
            status: Optional status filter
            upcoming_only: Only return future bookings
            limit: Optional result limit

        Returns:
            List of student's bookings
        """
        try:
            query = (
                self.db.query(Booking)
                .options(joinedload(Booking.instructor), joinedload(Booking.service))
                .filter(Booking.student_id == student_id)
            )

            if status:
                query = query.filter(Booking.status == status)

            if upcoming_only:
                query = query.filter(Booking.booking_date >= date.today(), Booking.status == BookingStatus.CONFIRMED)

            query = query.order_by(Booking.booking_date.desc(), Booking.start_time.desc())

            if limit:
                query = query.limit(limit)

            return query.all()

        except Exception as e:
            self.logger.error(f"Error getting student bookings: {str(e)}")
            raise RepositoryException(f"Failed to get student bookings: {str(e)}")

    def get_instructor_bookings(
        self,
        instructor_id: int,
        status: Optional[BookingStatus] = None,
        upcoming_only: bool = False,
        limit: Optional[int] = None,
    ) -> List[Booking]:
        """
        Get bookings for a specific instructor.

        Args:
            instructor_id: The instructor's user ID
            status: Optional status filter
            upcoming_only: Only return future bookings
            limit: Optional result limit

        Returns:
            List of instructor's bookings
        """
        try:
            query = (
                self.db.query(Booking)
                .options(joinedload(Booking.student), joinedload(Booking.service))
                .filter(Booking.instructor_id == instructor_id)
            )

            if status:
                query = query.filter(Booking.status == status)

            if upcoming_only:
                query = query.filter(Booking.booking_date >= date.today(), Booking.status == BookingStatus.CONFIRMED)

            query = query.order_by(Booking.booking_date.desc(), Booking.start_time.desc())

            if limit:
                query = query.limit(limit)

            return query.all()

        except Exception as e:
            self.logger.error(f"Error getting instructor bookings: {str(e)}")
            raise RepositoryException(f"Failed to get instructor bookings: {str(e)}")

    # Detailed Booking Queries

    def get_booking_with_details(self, booking_id: int) -> Optional[Booking]:
        """
        Get a booking with all relationships loaded.

        Loads all related objects for complete booking details.

        Args:
            booking_id: The booking ID

        Returns:
            The booking with all relationships, or None if not found
        """
        try:
            return (
                self.db.query(Booking)
                .options(
                    joinedload(Booking.student),
                    joinedload(Booking.instructor),
                    joinedload(Booking.service),
                    joinedload(Booking.cancelled_by),
                )
                .filter(Booking.id == booking_id)
                .first()
            )
        except Exception as e:
            self.logger.error(f"Error getting booking details: {str(e)}")
            raise RepositoryException(f"Failed to get booking details: {str(e)}")

    # Statistics Queries

    def get_instructor_bookings_for_stats(self, instructor_id: int) -> List[Booking]:
        """
        Get all bookings for an instructor for statistics calculation.

        Returns minimal data needed for stats without heavy relationships.

        Args:
            instructor_id: The instructor's user ID

        Returns:
            List of bookings for statistics
        """
        try:
            return self.db.query(Booking).filter(Booking.instructor_id == instructor_id).all()
        except Exception as e:
            self.logger.error(f"Error getting instructor stats: {str(e)}")
            raise RepositoryException(f"Failed to get instructor statistics: {str(e)}")

    # Date-based Queries

    def get_bookings_for_date(
        self, booking_date: date, status: Optional[BookingStatus] = None, with_relationships: bool = False
    ) -> List[Booking]:
        """
        Get bookings for a specific date.

        Used for reminder emails and daily views.

        Args:
            booking_date: The date to query
            status: Optional status filter
            with_relationships: Whether to eager load relationships

        Returns:
            List of bookings for the date
        """
        try:
            query = self.db.query(Booking).filter(Booking.booking_date == booking_date)

            if status:
                query = query.filter(Booking.status == status)

            if with_relationships:
                query = query.options(joinedload(Booking.student), joinedload(Booking.instructor))

            return query.all()

        except Exception as e:
            self.logger.error(f"Error getting bookings for date: {str(e)}")
            raise RepositoryException(f"Failed to get bookings for date: {str(e)}")

    def get_upcoming_bookings(self, user_id: int, user_role: str) -> List[Booking]:
        """
        Get upcoming bookings for a user ordered by date/time.

        Args:
            user_id: The user's ID
            user_role: The user's role (student/instructor)

        Returns:
            List of upcoming bookings ordered chronologically
        """
        try:
            query = (
                self.db.query(Booking)
                .options(
                    joinedload(Booking.instructor),
                    joinedload(Booking.student),
                    joinedload(Booking.service),
                )
                .filter(Booking.booking_date >= date.today(), Booking.status.in_([BookingStatus.CONFIRMED]))
            )

            if user_role == UserRole.STUDENT:
                query = query.filter(Booking.student_id == user_id)
            elif user_role == UserRole.INSTRUCTOR:
                query = query.filter(Booking.instructor_id == user_id)

            return query.order_by(Booking.booking_date, Booking.start_time).all()

        except Exception as e:
            self.logger.error(f"Error getting upcoming bookings: {str(e)}")
            raise RepositoryException(f"Failed to get upcoming bookings: {str(e)}")

    # Counting Queries

    def count_bookings(
        self,
        instructor_id: Optional[int] = None,
        student_id: Optional[int] = None,
        status: Optional[BookingStatus] = None,
    ) -> int:
        """
        Count bookings with optional filters.

        Args:
            instructor_id: Filter by instructor
            student_id: Filter by student
            status: Filter by status

        Returns:
            Number of bookings matching criteria
        """
        try:
            query = self.db.query(Booking)

            if instructor_id:
                query = query.filter(Booking.instructor_id == instructor_id)
            if student_id:
                query = query.filter(Booking.student_id == student_id)
            if status:
                query = query.filter(Booking.status == status)

            return query.count()

        except Exception as e:
            self.logger.error(f"Error counting bookings: {str(e)}")
            raise RepositoryException(f"Failed to count bookings: {str(e)}")

    def count_bookings_by_status(self, user_id: int, user_role: str) -> Dict[str, int]:
        """
        Count bookings grouped by status for a user.

        Args:
            user_id: The user's ID
            user_role: The user's role (student/instructor)

        Returns:
            Dictionary with status as key and count as value
        """
        try:
            query = self.db.query(Booking)

            if user_role == UserRole.STUDENT:
                query = query.filter(Booking.student_id == user_id)
            elif user_role == UserRole.INSTRUCTOR:
                query = query.filter(Booking.instructor_id == user_id)

            bookings = query.all()

            # Count by status
            status_counts = {}
            for status in BookingStatus:
                status_counts[status.value] = sum(1 for b in bookings if b.status == status)

            return status_counts

        except Exception as e:
            self.logger.error(f"Error counting bookings by status: {str(e)}")
            raise RepositoryException(f"Failed to count bookings by status: {str(e)}")

    # Conflict Checking

    def check_booking_conflicts(
        self,
        instructor_id: int,
        booking_date: date,
        start_time: time,
        end_time: time,
        exclude_booking_id: Optional[int] = None,
    ) -> List[Booking]:
        """
        Check for booking conflicts for an instructor.

        Finds overlapping bookings on the same date.

        Args:
            instructor_id: The instructor to check
            booking_date: The date to check
            start_time: Proposed start time
            end_time: Proposed end time
            exclude_booking_id: Booking ID to exclude from check (for updates)

        Returns:
            List of conflicting bookings
        """
        try:
            query = self.db.query(Booking).filter(
                Booking.instructor_id == instructor_id,
                Booking.booking_date == booking_date,
                Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
                # Time overlap check
                Booking.start_time < end_time,
                Booking.end_time > start_time,
            )

            if exclude_booking_id:
                query = query.filter(Booking.id != exclude_booking_id)

            return query.all()

        except Exception as e:
            self.logger.error(f"Error checking booking conflicts: {str(e)}")
            raise RepositoryException(f"Failed to check booking conflicts: {str(e)}")

    # Helper method overrides

    def _apply_eager_loading(self, query):
        """
        Override to include common relationships by default.

        For get_by_id and other single entity queries.
        """
        return query.options(
            joinedload(Booking.student),
            joinedload(Booking.instructor),
            joinedload(Booking.service),
        )

    # Additional Repository Methods (from BaseRepository)
    # The following are inherited from BaseRepository:
    # - create(**kwargs) -> Booking
    # - update(id: int, **kwargs) -> Optional[Booking]
    # - delete(id: int) -> bool
    # - get_by_id(id: int, load_relationships: bool = True) -> Optional[Booking]
    # - exists(**kwargs) -> bool
    # - count(**kwargs) -> int
    # - find_by(**kwargs) -> List[Booking]
    # - find_one_by(**kwargs) -> Optional[Booking]
    # - bulk_create(entities: List[Dict]) -> List[Booking]
    # - bulk_update(updates: List[Dict]) -> int
