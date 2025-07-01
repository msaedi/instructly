# backend/app/repositories/conflict_checker_repository.py
"""
ConflictChecker Repository for InstaInstru Platform

Implements all data access operations for conflict checking and validation,
based on the documented query patterns from strategic testing.

This repository handles:
- Booking conflict detection queries
- Slot availability checking
- Weekly booking aggregation
- Blackout date validation
- Instructor profile and service queries
- Complex availability summaries
"""

import logging
from datetime import date
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, case, func
from sqlalchemy.orm import Session, joinedload

from ..core.exceptions import RepositoryException
from ..models.availability import AvailabilitySlot, BlackoutDate, InstructorAvailability
from ..models.booking import Booking, BookingStatus
from ..models.instructor import InstructorProfile
from ..models.service import Service
from ..models.user import User
from .base_repository import BaseRepository

logger = logging.getLogger(__name__)


class ConflictCheckerRepository(BaseRepository[Booking]):
    """
    Repository for conflict checking data access.

    Implements all 13 documented query patterns from strategic testing.
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

        Complex JOIN query across Booking, AvailabilitySlot, and InstructorAvailability.
        Used in check_booking_conflicts to find overlapping bookings.

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
                .join(
                    InstructorAvailability,
                    AvailabilitySlot.availability_id == InstructorAvailability.id,
                )
                .filter(
                    InstructorAvailability.instructor_id == instructor_id,
                    Booking.booking_date == check_date,
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
        Get a slot with its availability relationship eager loaded.

        Used in check_slot_availability to validate slot ownership.

        Args:
            slot_id: The availability slot ID

        Returns:
            AvailabilitySlot with availability loaded, or None
        """
        try:
            return (
                self.db.query(AvailabilitySlot)
                .options(joinedload(AvailabilitySlot.availability))
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

        Returns composite data from multiple tables including slot times,
        booking details, and student information.

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
                .join(
                    InstructorAvailability,
                    AvailabilitySlot.availability_id == InstructorAvailability.id,
                )
                .filter(
                    InstructorAvailability.instructor_id == instructor_id,
                    InstructorAvailability.date == target_date,
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

        Returns data grouped by date for easy processing by the service.

        Args:
            instructor_id: The instructor ID
            week_dates: List of dates in the week (typically Monday-Sunday)

        Returns:
            List of dictionaries with date and booking information
        """
        try:
            results = (
                self.db.query(
                    InstructorAvailability.date,
                    AvailabilitySlot.id,
                    AvailabilitySlot.start_time,
                    AvailabilitySlot.end_time,
                    Booking.id.label("booking_id"),
                    Booking.student_id,
                    Booking.service_name,
                    Booking.status,
                )
                .join(
                    AvailabilitySlot,
                    InstructorAvailability.id == AvailabilitySlot.availability_id,
                )
                .join(Booking, AvailabilitySlot.id == Booking.availability_slot_id)
                .filter(
                    InstructorAvailability.instructor_id == instructor_id,
                    InstructorAvailability.date.in_(week_dates),
                    Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
                )
                .order_by(InstructorAvailability.date, AvailabilitySlot.start_time)
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

        Used for finding overlapping slots and availability analysis.

        Args:
            instructor_id: The instructor ID
            target_date: The date to check

        Returns:
            List of AvailabilitySlot objects
        """
        try:
            return (
                self.db.query(AvailabilitySlot)
                .join(InstructorAvailability)
                .filter(
                    InstructorAvailability.instructor_id == instructor_id,
                    InstructorAvailability.date == target_date,
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

    def get_instructor_profile(self, instructor_id: int) -> Optional[InstructorProfile]:
        """
        Get instructor profile for validation checks.

        Used for minimum advance booking hours and other constraints.

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

        Used for service constraint validation.

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

    # Range-based Queries

    def get_blackouts_in_range(self, instructor_id: int, start_date: date, end_date: date) -> List[BlackoutDate]:
        """
        Get all blackout dates for an instructor in a date range.

        Used for comprehensive validation across multiple days.

        Args:
            instructor_id: The instructor ID
            start_date: Range start date
            end_date: Range end date

        Returns:
            List of BlackoutDate objects
        """
        try:
            return (
                self.db.query(BlackoutDate)
                .filter(BlackoutDate.instructor_id == instructor_id, BlackoutDate.date.between(start_date, end_date))
                .all()
            )
        except Exception as e:
            self.logger.error(f"Error getting blackouts in range: {str(e)}")
            raise RepositoryException(f"Failed to get blackouts: {str(e)}")

    def get_bookings_in_range(self, instructor_id: int, start_date: date, end_date: date) -> List[Booking]:
        """
        Get all bookings for an instructor in a date range.

        Used for conflict checking across multiple days.

        Args:
            instructor_id: The instructor ID
            start_date: Range start date
            end_date: Range end date

        Returns:
            List of Booking objects with related data
        """
        try:
            return (
                self.db.query(Booking)
                .join(AvailabilitySlot, Booking.availability_slot_id == AvailabilitySlot.id)
                .join(InstructorAvailability, AvailabilitySlot.availability_id == InstructorAvailability.id)
                .filter(
                    InstructorAvailability.instructor_id == instructor_id,
                    Booking.booking_date.between(start_date, end_date),
                    Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
                )
                .all()
            )
        except Exception as e:
            self.logger.error(f"Error getting bookings in range: {str(e)}")
            raise RepositoryException(f"Failed to get bookings: {str(e)}")

    # Complex Aggregation Queries

    def get_instructor_availability_summary(
        self, instructor_id: int, start_date: date, end_date: date
    ) -> List[Dict[str, Any]]:
        """
        Get comprehensive availability summary with slot counts and booking status.

        Complex aggregation query for dashboard and reporting.

        Args:
            instructor_id: The instructor ID
            start_date: Range start date
            end_date: Range end date

        Returns:
            List of dictionaries with daily summaries
        """
        try:
            results = (
                self.db.query(
                    InstructorAvailability.date,
                    func.count(AvailabilitySlot.id).label("total_slots"),
                    func.count(Booking.id).label("booked_slots"),
                    func.count(BlackoutDate.id).label("blackout_count"),
                )
                .outerjoin(AvailabilitySlot, InstructorAvailability.id == AvailabilitySlot.availability_id)
                .outerjoin(
                    Booking,
                    and_(
                        AvailabilitySlot.id == Booking.availability_slot_id,
                        Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
                    ),
                )
                .outerjoin(
                    BlackoutDate,
                    and_(BlackoutDate.instructor_id == instructor_id, BlackoutDate.date == InstructorAvailability.date),
                )
                .filter(
                    InstructorAvailability.instructor_id == instructor_id,
                    InstructorAvailability.date.between(start_date, end_date),
                )
                .group_by(InstructorAvailability.date)
                .all()
            )

            return [
                {
                    "date": row.date,
                    "total_slots": row.total_slots,
                    "booked_slots": row.booked_slots,
                    "blackout_count": row.blackout_count,
                }
                for row in results
            ]

        except Exception as e:
            self.logger.error(f"Error getting availability summary: {str(e)}")
            raise RepositoryException(f"Failed to get summary: {str(e)}")

    def get_detailed_bookings_for_conflict_check(self, instructor_id: int, check_date: date) -> List[Dict[str, Any]]:
        """
        Get bookings with full details for advanced conflict detection.

        Includes student names and service details for comprehensive conflict information.

        Args:
            instructor_id: The instructor ID
            check_date: The date to check

        Returns:
            List of dictionaries with comprehensive booking details
        """
        try:
            results = (
                self.db.query(
                    Booking.id,
                    Booking.start_time,
                    Booking.end_time,
                    Booking.service_name,
                    Booking.status,
                    User.full_name.label("student_name"),
                    Service.skill.label("service_skill"),
                    AvailabilitySlot.id.label("slot_id"),
                )
                .join(User, Booking.student_id == User.id)
                .join(Service, Booking.service_id == Service.id)
                .join(AvailabilitySlot, Booking.availability_slot_id == AvailabilitySlot.id)
                .join(InstructorAvailability, AvailabilitySlot.availability_id == InstructorAvailability.id)
                .filter(
                    InstructorAvailability.instructor_id == instructor_id,
                    Booking.booking_date == check_date,
                    Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
                )
                .all()
            )

            return [
                {
                    "id": row.id,
                    "start_time": row.start_time,
                    "end_time": row.end_time,
                    "service_name": row.service_name,
                    "status": row.status,
                    "student_name": row.student_name,
                    "service_skill": row.service_skill,
                    "slot_id": row.slot_id,
                }
                for row in results
            ]

        except Exception as e:
            self.logger.error(f"Error getting detailed bookings: {str(e)}")
            raise RepositoryException(f"Failed to get detailed bookings: {str(e)}")

    def get_slot_utilization_stats(self, instructor_id: int, days_back: int = 30) -> List[Dict[str, Any]]:
        """
        Get slot utilization statistics for the past N days.

        Used for instructor dashboard and analytics.

        Args:
            instructor_id: The instructor ID
            days_back: Number of days to look back (default 30)

        Returns:
            List of dictionaries with utilization statistics
        """
        try:
            from datetime import datetime, timedelta

            start_date = datetime.now().date() - timedelta(days=days_back)

            results = (
                self.db.query(
                    InstructorAvailability.date,
                    func.count(AvailabilitySlot.id).label("available_slots"),
                    func.sum(case((Booking.id.isnot(None), 1), else_=0)).label("booked_slots"),
                    func.avg(
                        func.extract("epoch", AvailabilitySlot.end_time - AvailabilitySlot.start_time) / 3600
                    ).label("avg_slot_duration_hours"),
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
                    InstructorAvailability.instructor_id == instructor_id,
                    InstructorAvailability.date >= start_date,
                )
                .group_by(InstructorAvailability.date)
                .all()
            )

            return [
                {
                    "date": row.date,
                    "available_slots": row.available_slots,
                    "booked_slots": int(row.booked_slots or 0),
                    "avg_slot_duration_hours": float(row.avg_slot_duration_hours or 0),
                }
                for row in results
            ]

        except Exception as e:
            self.logger.error(f"Error getting utilization stats: {str(e)}")
            raise RepositoryException(f"Failed to get stats: {str(e)}")
