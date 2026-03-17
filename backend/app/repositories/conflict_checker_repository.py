# backend/app/repositories/conflict_checker_repository.py
"""
ConflictChecker Repository for InstaInstru Platform

UPDATED FOR CLEAN ARCHITECTURE: Complete separation from availability slots.

This repository now works exclusively with booking data without any
reference to availability slots. All conflict checking is done using
the self-contained booking fields (date, start_time, end_time).

Key changes:
- Removed all AvailabilitySlot joins and queries
- Using Booking fields directly for all time-based queries
- Simplified from complex joins to direct booking queries
"""

from datetime import date
import logging
from typing import List, Optional, cast

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.sql.elements import ColumnElement

from ..core.exceptions import RepositoryException
from ..models.availability import BlackoutDate
from ..models.booking import Booking, BookingStatus
from ..models.booking_payment import BookingPayment
from ..models.instructor import InstructorProfile
from ..models.service_catalog import InstructorService
from .base_repository import BaseRepository

logger = logging.getLogger(__name__)


class ConflictCheckerRepository(BaseRepository[Booking]):
    """
    Repository for conflict checking data access.

    Works exclusively with booking data and related entities
    without any reference to availability slots.
    """

    def __init__(self, db: Session):
        """Initialize with Booking model as primary."""
        super().__init__(db, Booking)
        self.logger = logging.getLogger(__name__)

    @staticmethod
    def _conflict_status_filter() -> ColumnElement[bool]:
        return or_(
            and_(
                Booking.status == BookingStatus.PENDING,
                or_(
                    BookingPayment.id.is_(None),
                    BookingPayment.auth_failure_count.is_(None),
                    BookingPayment.auth_failure_count == 0,
                ),
            ),
            Booking.status.in_(
                [
                    BookingStatus.CONFIRMED,
                    BookingStatus.COMPLETED,
                    BookingStatus.NO_SHOW,
                ]
            ),
        )

    # Booking Conflict Queries

    def get_bookings_for_conflict_check(
        self, instructor_id: str, check_date: date, exclude_booking_id: Optional[str] = None
    ) -> List[Booking]:
        """
        Get bookings that could conflict with a time range on a specific date.

        Now uses booking's own fields without any slot references.

        Args:
            instructor_id: The instructor to check
            check_date: The date to check for conflicts
            exclude_booking_id: Optional booking ID to exclude from results

        Returns:
            List of bookings with their related data loaded
        """
        try:
            query = (
                self.db.query(Booking)
                .outerjoin(BookingPayment, BookingPayment.booking_id == Booking.id)
                .options(
                    joinedload(Booking.student),
                    joinedload(Booking.instructor),
                )
                .filter(
                    Booking.instructor_id == instructor_id,
                    Booking.booking_date == check_date,
                    self._conflict_status_filter(),
                )
            )

            if exclude_booking_id:
                query = query.filter(Booking.id != exclude_booking_id)

            return cast(List[Booking], query.order_by(Booking.start_time).all())

        except Exception as e:
            self.logger.error("Error getting bookings for conflict check: %s", str(e))
            raise RepositoryException(f"Failed to get conflict bookings: {str(e)}")

    def get_student_bookings_for_conflict_check(
        self, student_id: str, check_date: date, exclude_booking_id: Optional[str] = None
    ) -> List[Booking]:
        """
        Get a student's bookings that could conflict with a requested time on a specific date.
        """
        try:
            query = (
                self.db.query(Booking)
                .outerjoin(BookingPayment, BookingPayment.booking_id == Booking.id)
                .options(
                    joinedload(Booking.instructor),
                    joinedload(Booking.student),
                )
                .filter(
                    Booking.student_id == student_id,
                    Booking.booking_date == check_date,
                    self._conflict_status_filter(),
                )
            )

            if exclude_booking_id:
                query = query.filter(Booking.id != exclude_booking_id)

            return cast(List[Booking], query.order_by(Booking.start_time).all())

        except Exception as e:
            self.logger.error("Error getting student bookings for conflict check: %s", str(e))
            raise RepositoryException(f"Failed to get student conflict bookings: {str(e)}")

    def get_bookings_for_date(self, instructor_id: str, target_date: date) -> List[Booking]:
        """
        Get all bookings for an instructor on a specific date.

        Direct query on bookings table.

        Args:
            instructor_id: The instructor ID
            target_date: The date to check

        Returns:
            List of bookings ordered by start time
        """
        try:
            return cast(
                List[Booking],
                self.db.query(Booking)
                .filter(
                    Booking.instructor_id == instructor_id,
                    Booking.booking_date == target_date,
                    Booking.status.in_(
                        [BookingStatus.PENDING, BookingStatus.CONFIRMED, BookingStatus.COMPLETED]
                    ),
                )
                .order_by(Booking.start_time)
                .all(),
            )

        except Exception as e:
            self.logger.error("Error getting bookings for date: %s", str(e))
            raise RepositoryException(f"Failed to get bookings: {str(e)}")

    def get_bookings_for_week(self, instructor_id: str, week_dates: List[date]) -> List[Booking]:
        """
        Get all bookings for an instructor for a week.

        Direct query on bookings table.

        Args:
            instructor_id: The instructor ID
            week_dates: List of dates in the week (typically Monday-Sunday)

        Returns:
            List of bookings ordered by date and time
        """
        try:
            return cast(
                List[Booking],
                self.db.query(Booking)
                .filter(
                    Booking.instructor_id == instructor_id,
                    Booking.booking_date.in_(week_dates),
                    Booking.status.in_(
                        [BookingStatus.PENDING, BookingStatus.CONFIRMED, BookingStatus.COMPLETED]
                    ),
                )
                .order_by(Booking.booking_date, Booking.start_time)
                .all(),
            )

        except Exception as e:
            self.logger.error("Error getting bookings for week: %s", str(e))
            raise RepositoryException(f"Failed to get weekly bookings: {str(e)}")

    # Blackout Date Queries (unchanged)

    def get_blackout_date(self, instructor_id: str, target_date: date) -> Optional[BlackoutDate]:
        """
        Check if a specific date is blacked out for an instructor.

        Args:
            instructor_id: The instructor ID
            target_date: The date to check

        Returns:
            BlackoutDate object if exists, None otherwise
        """
        try:
            result = (
                self.db.query(BlackoutDate)
                .filter(
                    BlackoutDate.instructor_id == instructor_id,
                    BlackoutDate.date == target_date,
                )
                .first()
            )
            return cast(Optional[BlackoutDate], result)
        except Exception as e:
            self.logger.error("Error checking blackout date: %s", str(e))
            raise RepositoryException(f"Failed to check blackout: {str(e)}")

    # Instructor and Service Queries (unchanged)

    def get_instructor_profile(self, instructor_id: str) -> Optional[InstructorProfile]:
        """
        Get instructor profile for validation checks.

        Args:
            instructor_id: The instructor ID (user_id)

        Returns:
            InstructorProfile if exists, None otherwise
        """
        try:
            result = (
                self.db.query(InstructorProfile)
                .filter(InstructorProfile.user_id == instructor_id)
                .first()
            )
            return cast(Optional[InstructorProfile], result)
        except Exception as e:
            self.logger.error("Error getting instructor profile: %s", str(e))
            raise RepositoryException(f"Failed to get profile: {str(e)}")

    def get_active_service(self, service_id: str) -> Optional[InstructorService]:
        """
        Get an active service by ID.

        Args:
            service_id: The service ID

        Returns:
            InstructorService if active and exists, None otherwise
        """
        try:
            result = (
                self.db.query(InstructorService)
                .options(
                    joinedload(InstructorService.catalog_entry),
                    joinedload(InstructorService.format_prices),
                )
                .filter(InstructorService.id == service_id, InstructorService.is_active == True)
                .first()
            )
            return cast(Optional[InstructorService], result)
        except Exception as e:
            self.logger.error("Error getting active service: %s", str(e))
            raise RepositoryException(f"Failed to get service: {str(e)}")
