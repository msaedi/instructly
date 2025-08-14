# backend/app/services/conflict_checker.py
"""
Conflict Checker Service for InstaInstru Platform

Handles all booking conflict detection and validation including:
- Checking if time slots conflict with existing bookings
- Validating booking constraints
- Finding available times
- Managing booking rules

All conflict checks now use booking's own fields (date, start_time, end_time)
without any reference to availability slots.
"""

import logging
from datetime import date, datetime, time, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from ..core.timezone_utils import get_user_today_by_id
from ..models.booking import BookingStatus
from ..repositories import RepositoryFactory
from ..repositories.conflict_checker_repository import ConflictCheckerRepository
from .base import BaseService

logger = logging.getLogger(__name__)


class ConflictChecker(BaseService):
    """
    Service for checking booking conflicts and time validation.

    This service centralizes all conflict detection logic to ensure
    consistent validation across the platform. Works entirely with
    booking data without referencing availability slots.
    """

    def __init__(self, db: Session, repository: Optional[ConflictCheckerRepository] = None):
        """
        Initialize conflict checker service.

        Args:
            db: Database session
            repository: Optional ConflictCheckerRepository instance
        """
        super().__init__(db)
        self.logger = logging.getLogger(__name__)
        self.repository = repository or RepositoryFactory.create_conflict_checker_repository(db)
        self.user_repository = RepositoryFactory.create_user_repository(db)

    @BaseService.measure_operation("check_booking_conflicts")
    def check_booking_conflicts(
        self,
        instructor_id: str,
        check_date: date,
        start_time: time,
        end_time: time,
        exclude_booking_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Check if a time range conflicts with existing bookings.

        Uses booking's own time fields for conflict detection.

        Args:
            instructor_id: The instructor to check
            check_date: The date to check
            start_time: Start time of the range to check
            end_time: End time of the range to check
            exclude_booking_id: Optional booking ID to exclude from check

        Returns:
            List of conflicts with booking details
        """
        bookings = self.repository.get_bookings_for_conflict_check(instructor_id, check_date, exclude_booking_id)

        conflicts = []
        for booking in bookings:
            # Check time overlap using booking's own fields
            if start_time < booking.end_time and end_time > booking.start_time:
                conflicts.append(
                    {
                        "booking_id": booking.id,
                        "start_time": str(booking.start_time),
                        "end_time": str(booking.end_time),
                        "student_first_name": booking.student.first_name,
                        "student_last_name": booking.student.last_name,
                        "service_name": booking.service_name,
                        "status": booking.status,
                    }
                )

        if conflicts:
            self.logger.warning(
                f"Found {len(conflicts)} booking conflicts for {instructor_id} "
                f"on {check_date} between {start_time}-{end_time}"
            )

        return conflicts

    @BaseService.measure_operation("check_time_conflicts")
    def check_time_conflicts(
        self,
        instructor_id: str,
        booking_date: date,
        start_time: time,
        end_time: time,
        exclude_booking_id: Optional[int] = None,
    ) -> bool:
        """
        Check if a time range has any conflicts.

        Simplified boolean check for quick validation.

        Args:
            instructor_id: The instructor to check
            booking_date: The date to check
            start_time: Start time of the range
            end_time: End time of the range
            exclude_booking_id: Optional booking ID to exclude

        Returns:
            True if there are conflicts, False otherwise
        """
        conflicts = self.check_booking_conflicts(instructor_id, booking_date, start_time, end_time, exclude_booking_id)
        return len(conflicts) > 0

    @BaseService.measure_operation("get_booked_times_date")
    def get_booked_times_for_date(self, instructor_id: str, target_date: date) -> List[Dict[str, Any]]:
        """
        Get all booked time ranges for an instructor on a specific date.

        Returns booking time information directly from bookings.

        Args:
            instructor_id: The instructor ID
            target_date: The date to check

        Returns:
            List of booked time ranges
        """
        bookings = self.repository.get_bookings_for_date(instructor_id, target_date)

        return [
            {
                "booking_id": booking.id,
                "start_time": booking.start_time.isoformat(),
                "end_time": booking.end_time.isoformat(),
                "student_id": booking.student_id,
                "service_name": booking.service_name,
                "status": booking.status,
            }
            for booking in bookings
            if booking.status in [BookingStatus.CONFIRMED, BookingStatus.COMPLETED]
        ]

    @BaseService.measure_operation("get_booked_times_week")
    def get_booked_times_for_week(self, instructor_id: str, week_start: date) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get all booked times for an instructor for a week.

        Args:
            instructor_id: The instructor ID
            week_start: Monday of the week

        Returns:
            Dictionary mapping dates to booked times
        """
        week_dates = [week_start + timedelta(days=i) for i in range(7)]
        bookings = self.repository.get_bookings_for_week(instructor_id, week_dates)

        # Group by date
        times_by_date = {}
        for booking in bookings:
            if booking.status not in [BookingStatus.CONFIRMED, BookingStatus.COMPLETED]:
                continue

            date_str = booking.booking_date.isoformat()
            if date_str not in times_by_date:
                times_by_date[date_str] = []

            times_by_date[date_str].append(
                {
                    "booking_id": booking.id,
                    "start_time": booking.start_time.isoformat(),
                    "end_time": booking.end_time.isoformat(),
                    "student_id": booking.student_id,
                    "service_name": booking.service_name,
                    "status": booking.status,
                }
            )

        return times_by_date

    @BaseService.measure_operation("validate_time_range")
    def validate_time_range(
        self,
        start_time: time,
        end_time: time,
        min_duration_minutes: int = 30,
        max_duration_minutes: int = 480,  # 8 hours
    ) -> Dict[str, Any]:
        """
        Validate a time range for basic constraints.

        Business logic for time validation.

        Args:
            start_time: Start time
            end_time: End time
            min_duration_minutes: Minimum allowed duration
            max_duration_minutes: Maximum allowed duration

        Returns:
            Validation result with details
        """
        # Check time order
        if end_time <= start_time:
            return {"valid": False, "reason": "End time must be after start time"}

        # Calculate duration using reference date (timezone-agnostic)
        start = datetime.combine(date.today(), start_time)  # reference calculation only
        end = datetime.combine(date.today(), end_time)  # reference calculation only
        duration = end - start
        duration_minutes = int(duration.total_seconds() / 60)

        # Check minimum duration
        if duration_minutes < min_duration_minutes:
            return {
                "valid": False,
                "reason": f"Duration must be at least {min_duration_minutes} minutes",
                "duration_minutes": duration_minutes,
            }

        # Check maximum duration
        if duration_minutes > max_duration_minutes:
            return {
                "valid": False,
                "reason": f"Duration cannot exceed {max_duration_minutes} minutes",
                "duration_minutes": duration_minutes,
            }

        return {"valid": True, "duration_minutes": duration_minutes}

    @BaseService.measure_operation("check_advance_booking")
    def check_minimum_advance_booking(
        self, instructor_id: str, booking_date: date, booking_time: time
    ) -> Dict[str, Any]:
        """
        Check if booking meets minimum advance booking requirements.

        Args:
            instructor_id: The instructor ID
            booking_date: Date of the booking
            booking_time: Time of the booking

        Returns:
            Validation result with details
        """
        # Get instructor profile
        profile = self.repository.get_instructor_profile(instructor_id)

        if not profile:
            return {"valid": False, "reason": "Instructor profile not found"}

        # Get instructor for timezone calculations
        instructor = self.user_repository.get_by_id(instructor_id)
        if not instructor:
            return {"valid": False, "reason": "Instructor not found"}

        # Calculate booking datetime in instructor's timezone
        booking_datetime = datetime.combine(booking_date, booking_time)

        # Get instructor's current time
        from ..core.timezone_utils import get_user_now

        instructor_now = get_user_now(instructor)

        # Calculate minimum booking time
        min_booking_time = instructor_now + timedelta(hours=profile.min_advance_booking_hours)

        # For comparison, we need to ensure both times are timezone-aware
        # Convert booking_datetime to instructor's timezone for fair comparison
        instructor_tz = instructor_now.tzinfo
        booking_datetime_tz = instructor_tz.localize(booking_datetime)

        if booking_datetime_tz < min_booking_time:
            hours_until_booking = (booking_datetime_tz - instructor_now).total_seconds() / 3600
            return {
                "valid": False,
                "reason": f"Bookings must be made at least {profile.min_advance_booking_hours} hours in advance (instructor timezone)",
                "min_advance_hours": profile.min_advance_booking_hours,
                "hours_until_booking": max(0, hours_until_booking),
            }

        return {"valid": True, "min_advance_hours": profile.min_advance_booking_hours}

    @BaseService.measure_operation("check_blackout")
    def check_blackout_date(self, instructor_id: str, target_date: date) -> bool:
        """
        Check if a date is blacked out for an instructor.

        Args:
            instructor_id: The instructor ID
            target_date: The date to check

        Returns:
            True if date is blacked out
        """
        blackout = self.repository.get_blackout_date(instructor_id, target_date)
        return blackout is not None

    @BaseService.measure_operation("validate_constraints")
    def validate_booking_constraints(
        self,
        instructor_id: str,
        booking_date: date,
        start_time: time,
        end_time: time,
        service_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Comprehensive validation of booking constraints.

        Checks:
        - Time range validity
        - Minimum advance booking
        - Blackout dates
        - Existing conflicts

        Args:
            instructor_id: The instructor ID
            booking_date: Date of the booking
            start_time: Start time
            end_time: End time
            service_id: Optional service ID for additional validation

        Returns:
            Comprehensive validation result
        """
        errors = []
        warnings = []

        # Validate time range
        time_validation = self.validate_time_range(start_time, end_time)
        if not time_validation["valid"]:
            errors.append(time_validation["reason"])

        # Check if date is in the past using instructor's timezone
        instructor_today = get_user_today_by_id(instructor_id, self.db)
        if booking_date < instructor_today:
            errors.append(f"Cannot book for past dates (instructor timezone)")
        elif booking_date == instructor_today:
            # Get instructor's current time for same-day validation
            instructor = self.user_repository.get_by_id(instructor_id)
            if instructor:
                from ..core.timezone_utils import get_user_now

                instructor_now = get_user_now(instructor)
                if start_time < instructor_now.time():
                    errors.append(f"Cannot book for past time slots (instructor timezone)")

        # Check minimum advance booking
        advance_check = self.check_minimum_advance_booking(instructor_id, booking_date, start_time)
        if not advance_check["valid"]:
            errors.append(advance_check["reason"])

        # Check blackout date
        if self.check_blackout_date(instructor_id, booking_date):
            errors.append("Instructor is not available on this date")

        # Check for conflicts
        conflicts = self.check_booking_conflicts(instructor_id, booking_date, start_time, end_time)
        if conflicts:
            errors.append(f"Time slot conflicts with {len(conflicts)} existing bookings")

        # If service provided, validate service constraints
        if service_id:
            service = self.repository.get_active_service(service_id)

            if not service:
                errors.append("Service not found or no longer available")
            elif service.duration_options:
                # Check if slot duration matches any of the service duration options
                duration_minutes = time_validation.get("duration_minutes", 0)
                if duration_minutes not in service.duration_options:
                    warnings.append(
                        f"Service offers {service.duration_options} minutes, " f"but slot is {duration_minutes} minutes"
                    )

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "details": {
                "time_validation": time_validation,
                "advance_booking": advance_check,
                "conflicts": conflicts,
                "has_blackout": self.check_blackout_date(instructor_id, booking_date),
            },
        }

    @BaseService.measure_operation("find_next_available")
    def find_next_available_time(
        self,
        instructor_id: str,
        target_date: date,
        duration_minutes: int,
        earliest_time: Optional[time] = None,
        latest_time: Optional[time] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Find the next available time slot for booking.

        Searches for gaps between existing bookings.

        Args:
            instructor_id: The instructor ID
            target_date: The date to search
            duration_minutes: Required duration
            earliest_time: Earliest acceptable start time
            latest_time: Latest acceptable end time

        Returns:
            Next available time slot or None if not found
        """
        # Default time bounds
        if not earliest_time:
            earliest_time = time(9, 0)  # 9 AM
        if not latest_time:
            latest_time = time(21, 0)  # 9 PM

        # Get all bookings for the date
        bookings = self.repository.get_bookings_for_date(instructor_id, target_date)

        # Filter to confirmed/completed and sort by start time
        active_bookings = sorted(
            [b for b in bookings if b.status in [BookingStatus.CONFIRMED, BookingStatus.COMPLETED]],
            key=lambda b: b.start_time,
        )

        # Check if we can start at earliest_time
        current_time = earliest_time

        for booking in active_bookings:
            # Calculate potential end time using reference date (timezone-agnostic)
            start_dt = datetime.combine(date.today(), current_time)  # reference calculation only
            end_dt = start_dt + timedelta(minutes=duration_minutes)
            potential_end = end_dt.time()

            # Check if this slot works (before the booking)
            if potential_end <= booking.start_time and potential_end <= latest_time:
                return {
                    "start_time": current_time.isoformat(),
                    "end_time": potential_end.isoformat(),
                    "duration_minutes": duration_minutes,
                    "available": True,
                }

            # Move current time to after this booking
            current_time = booking.end_time

        # Check if there's room after all bookings using reference date (timezone-agnostic)
        start_dt = datetime.combine(date.today(), current_time)  # reference calculation only
        end_dt = start_dt + timedelta(minutes=duration_minutes)
        potential_end = end_dt.time()

        if potential_end <= latest_time:
            return {
                "start_time": current_time.isoformat(),
                "end_time": potential_end.isoformat(),
                "duration_minutes": duration_minutes,
                "available": True,
            }

        return None
