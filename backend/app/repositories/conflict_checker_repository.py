# backend/app/repositories/conflict_checker_repository.py
"""
ConflictChecker Repository for InstaInstru Platform

UPDATED FOR WORK STREAM #10: Single-table availability design.

This repository now works with the simplified single-table design where
AvailabilitySlot contains both date and time information. All joins through
InstructorAvailability have been removed.

Key changes:
- Removed all InstructorAvailability joins
- Using AvailabilitySlot.instructor_id and AvailabilitySlot.date directly
- Deleted 5 unused methods (40% reduction)
- Simplified queries from 3-way to 2-way joins
"""

import logging
from datetime import date
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session, joinedload

from ..core.exceptions import RepositoryException
from ..models.availability import AvailabilitySlot, BlackoutDate
from ..models.booking import Booking, BookingStatus
from ..models.instructor import InstructorProfile
from ..models.service import Service
from .base_repository import BaseRepository

logger = logging.getLogger(__name__)


class ConflictCheckerRepository(BaseRepository[Booking]):
    """
    Repository for conflict checking data access.

    Implements 8 query patterns (down from 13) after removing unused methods.
    Primary model is Booking but queries across multiple tables.
    """

    def __init__(self, db: Session):
        """Initialize with Booking model as primary."""
        super().__init__(db, Booking)
        self.logger = logging.getLogger(__name__)

    # Booking Conflict Queries

    def get_bookings_for_conflict_check(
        self, instructor_id: int, check_date: date, exclude_slot_id: Optional[int] = None
    ) -> List[Booking]:
        """
        Get bookings that could conflict with a time range on a specific date.

        SIMPLIFIED: Now directly joins Booking → AvailabilitySlot without
        going through InstructorAvailability.

        Args:
            instructor_id: The instructor to check
            check_date: The date to check for conflicts
            exclude_slot_id: Optional slot ID to exclude from results

        Returns:
            List of bookings with their related slots loaded
        """
        try:
            query = (
                self.db.query(Booking)
                .join(AvailabilitySlot, Booking.availability_slot_id == AvailabilitySlot.id)
                .filter(
                    AvailabilitySlot.instructor_id == instructor_id,
                    AvailabilitySlot.date == check_date,
                    Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
                )
            )

            if exclude_slot_id:
                query = query.filter(AvailabilitySlot.id != exclude_slot_id)

            return query.all()

        except Exception as e:
            self.logger.error(f"Error getting bookings for conflict check: {str(e)}")
            raise RepositoryException(f"Failed to get conflict bookings: {str(e)}")

    # Slot Availability Queries

    def get_slot_with_availability(self, slot_id: int) -> Optional[AvailabilitySlot]:
        """
        Get a slot with its instructor relationship eager loaded.

        SIMPLIFIED: No longer loads the intermediate availability table,
        just loads the instructor directly.

        Args:
            slot_id: The availability slot ID

        Returns:
            AvailabilitySlot with instructor loaded, or None
        """
        try:
            return (
                self.db.query(AvailabilitySlot)
                .options(joinedload(AvailabilitySlot.instructor))
                .filter(AvailabilitySlot.id == slot_id)
                .first()
            )
        except Exception as e:
            self.logger.error(f"Error getting slot with availability: {str(e)}")
            raise RepositoryException(f"Failed to get slot: {str(e)}")

    # Date-specific Booking Queries

    def get_booked_slots_for_date(self, instructor_id: int, target_date: date) -> List[Dict[str, Any]]:
        """
        Get all booked slots for an instructor on a specific date.

        SIMPLIFIED: Queries directly from AvailabilitySlot without
        InstructorAvailability join.

        Args:
            instructor_id: The instructor ID
            target_date: The date to check

        Returns:
            List of dictionaries with booking and slot information
        """
        try:
            results = (
                self.db.query(
                    AvailabilitySlot.id,
                    AvailabilitySlot.start_time,
                    AvailabilitySlot.end_time,
                    Booking.id.label("booking_id"),
                    Booking.student_id,
                    Booking.service_name,
                    Booking.status,
                )
                .join(Booking, AvailabilitySlot.id == Booking.availability_slot_id)
                .filter(
                    AvailabilitySlot.instructor_id == instructor_id,
                    AvailabilitySlot.date == target_date,
                    Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
                )
                .all()
            )

            # Convert to dictionaries
            return [
                {
                    "id": row.id,
                    "start_time": row.start_time,
                    "end_time": row.end_time,
                    "booking_id": row.booking_id,
                    "student_id": row.student_id,
                    "service_name": row.service_name,
                    "status": row.status,
                }
                for row in results
            ]

        except Exception as e:
            self.logger.error(f"Error getting booked slots for date: {str(e)}")
            raise RepositoryException(f"Failed to get booked slots: {str(e)}")

    # Week-based Queries

    def get_booked_slots_for_week(self, instructor_id: int, week_dates: List[date]) -> List[Dict[str, Any]]:
        """
        Get all booked slots for an instructor for a week.

        SIMPLIFIED: Uses AvailabilitySlot.date directly instead of
        joining through InstructorAvailability.

        Args:
            instructor_id: The instructor ID
            week_dates: List of dates in the week (typically Monday-Sunday)

        Returns:
            List of dictionaries with date and booking information
        """
        try:
            results = (
                self.db.query(
                    AvailabilitySlot.date,
                    AvailabilitySlot.id,
                    AvailabilitySlot.start_time,
                    AvailabilitySlot.end_time,
                    Booking.id.label("booking_id"),
                    Booking.student_id,
                    Booking.service_name,
                    Booking.status,
                )
                .join(Booking, AvailabilitySlot.id == Booking.availability_slot_id)
                .filter(
                    AvailabilitySlot.instructor_id == instructor_id,
                    AvailabilitySlot.date.in_(week_dates),
                    Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
                )
                .order_by(AvailabilitySlot.date, AvailabilitySlot.start_time)
                .all()
            )

            # Convert to dictionaries
            return [
                {
                    "date": row.date,
                    "id": row.id,
                    "start_time": row.start_time,
                    "end_time": row.end_time,
                    "booking_id": row.booking_id,
                    "student_id": row.student_id,
                    "service_name": row.service_name,
                    "status": row.status,
                }
                for row in results
            ]

        except Exception as e:
            self.logger.error(f"Error getting booked slots for week: {str(e)}")
            raise RepositoryException(f"Failed to get weekly bookings: {str(e)}")

    # Slot Queries

    def get_slots_for_date(self, instructor_id: int, target_date: date) -> List[AvailabilitySlot]:
        """
        Get all availability slots for an instructor on a specific date.

        SIMPLIFIED: Direct query on AvailabilitySlot table.

        Args:
            instructor_id: The instructor ID
            target_date: The date to check

        Returns:
            List of AvailabilitySlot objects
        """
        try:
            return (
                self.db.query(AvailabilitySlot)
                .filter(
                    AvailabilitySlot.instructor_id == instructor_id,
                    AvailabilitySlot.date == target_date,
                )
                .all()
            )
        except Exception as e:
            self.logger.error(f"Error getting slots for date: {str(e)}")
            raise RepositoryException(f"Failed to get slots: {str(e)}")

    # Blackout Date Queries

    def get_blackout_date(self, instructor_id: int, target_date: date) -> Optional[BlackoutDate]:
        """
        Check if a specific date is blacked out for an instructor.

        NOTE: This query is unchanged as BlackoutDate already references
        instructor directly.

        Args:
            instructor_id: The instructor ID
            target_date: The date to check

        Returns:
            BlackoutDate object if exists, None otherwise
        """
        try:
            return (
                self.db.query(BlackoutDate)
                .filter(
                    BlackoutDate.instructor_id == instructor_id,
                    BlackoutDate.date == target_date,
                )
                .first()
            )
        except Exception as e:
            self.logger.error(f"Error checking blackout date: {str(e)}")
            raise RepositoryException(f"Failed to check blackout: {str(e)}")

    # Instructor and Service Queries
    # Single source for instructor profile queries across repositories
    def get_instructor_profile(self, instructor_id: int) -> Optional[InstructorProfile]:
        """
        Get instructor profile for validation checks.

        NOTE: This query is unchanged as it doesn't involve availability.

        Args:
            instructor_id: The instructor ID (user_id)

        Returns:
            InstructorProfile if exists, None otherwise
        """
        try:
            return self.db.query(InstructorProfile).filter(InstructorProfile.user_id == instructor_id).first()
        except Exception as e:
            self.logger.error(f"Error getting instructor profile: {str(e)}")
            raise RepositoryException(f"Failed to get profile: {str(e)}")

    def get_active_service(self, service_id: int) -> Optional[Service]:
        """
        Get an active service by ID.

        NOTE: This query is unchanged as it doesn't involve availability.

        Args:
            service_id: The service ID

        Returns:
            Service if active and exists, None otherwise
        """
        try:
            return self.db.query(Service).filter(Service.id == service_id, Service.is_active == True).first()
        except Exception as e:
            self.logger.error(f"Error getting active service: {str(e)}")
            raise RepositoryException(f"Failed to get service: {str(e)}")

    # REMOVED METHODS (not used by any service):
    # - get_blackouts_in_range()
    # - get_bookings_in_range()
    # - get_instructor_availability_summary()
    # - get_detailed_bookings_for_conflict_check()
    # - get_slot_utilization_stats()
