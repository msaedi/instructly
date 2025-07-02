# backend/app/services/conflict_checker.py
"""
Conflict Checker Service for InstaInstru Platform

UPDATED FOR WORK STREAM #10: Single-table availability design.

Handles all booking conflict detection and validation including:
- Checking if time slots conflict with existing bookings
- Validating availability windows
- Finding available slots
- Managing booking constraints

All slot references now use the single-table design where AvailabilitySlot
contains instructor_id and date directly.
"""

import logging
from datetime import date, datetime, time, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from ..models.booking import Booking, BookingStatus
from ..repositories import RepositoryFactory
from ..repositories.conflict_checker_repository import ConflictCheckerRepository
from .base import BaseService

logger = logging.getLogger(__name__)


class ConflictChecker(BaseService):
    """
    Service for checking booking conflicts and availability validation.

    This service centralizes all conflict detection logic to ensure
    consistent validation across the platform.
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

    def check_booking_conflicts(
        self,
        instructor_id: int,
        check_date: date,
        start_time: time,
        end_time: time,
        exclude_slot_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Check if a time range conflicts with existing bookings.

        Args:
            instructor_id: The instructor to check
            check_date: The date to check
            start_time: Start time of the range to check
            end_time: End time of the range to check
            exclude_slot_id: Optional slot ID to exclude from check

        Returns:
            List of conflicts with booking details
        """
        bookings = self.repository.get_bookings_for_conflict_check(instructor_id, check_date, exclude_slot_id)

        conflicts = []
        for booking in bookings:
            slot = booking.availability_slot
            # Check if time ranges overlap (business logic stays in service)
            if start_time < slot.end_time and end_time > slot.start_time:
                conflicts.append(
                    {
                        "booking_id": booking.id,
                        "start_time": str(slot.start_time),
                        "end_time": str(slot.end_time),
                        "student_name": booking.student.full_name,
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

    def check_slot_availability(self, slot_id: int, instructor_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Check if a specific slot is available for booking.

        UPDATED: Slot now has instructor_id and date directly.

        Args:
            slot_id: The availability slot ID
            instructor_id: Optional instructor ID for ownership check

        Returns:
            Dictionary with availability status and details
        """
        # Get the slot with relationships
        slot = self.repository.get_slot_with_availability(slot_id)

        if not slot:
            return {"available": False, "reason": "Slot not found"}

        # Check instructor ownership if specified
        if instructor_id and slot.instructor_id != instructor_id:
            return {
                "available": False,
                "reason": "Slot belongs to different instructor",
            }

        # Check if already booked by querying bookings table
        booking = (
            self.db.query(Booking)
            .filter(
                Booking.availability_slot_id == slot_id,
                Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
            )
            .first()
        )

        if booking:
            return {
                "available": False,
                "reason": "Slot is already booked",
                "booking_status": booking.status,
            }

        # Check if slot is in the past
        slot_datetime = datetime.combine(slot.date, slot.start_time)
        if slot_datetime < datetime.now():
            return {"available": False, "reason": "Slot is in the past"}

        return {
            "available": True,
            "slot_info": {
                "date": slot.date.isoformat(),
                "start_time": slot.start_time.isoformat(),
                "end_time": slot.end_time.isoformat(),
                "instructor_id": slot.instructor_id,
            },
        }

    def get_booked_slots_for_date(self, instructor_id: int, target_date: date) -> List[Dict[str, Any]]:
        """
        Get all booked slots for an instructor on a specific date.

        Args:
            instructor_id: The instructor ID
            target_date: The date to check

        Returns:
            List of booked slot details
        """
        booked_slots = self.repository.get_booked_slots_for_date(instructor_id, target_date)

        return [
            {
                "slot_id": slot["id"],
                "start_time": slot["start_time"].isoformat(),
                "end_time": slot["end_time"].isoformat(),
                "booking_id": slot["booking_id"],
                "student_id": slot["student_id"],
                "service_name": slot["service_name"],
                "status": slot["status"],
            }
            for slot in booked_slots
        ]

    def get_booked_slots_for_week(self, instructor_id: int, week_start: date) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get all booked slots for an instructor for a week.

        Args:
            instructor_id: The instructor ID
            week_start: Monday of the week

        Returns:
            Dictionary mapping dates to booked slots
        """
        week_dates = [week_start + timedelta(days=i) for i in range(7)]

        booked_slots = self.repository.get_booked_slots_for_week(instructor_id, week_dates)

        # Group by date (business logic)
        slots_by_date = {}
        for slot in booked_slots:
            date_str = slot["date"].isoformat()
            if date_str not in slots_by_date:
                slots_by_date[date_str] = []

            slots_by_date[date_str].append(
                {
                    "slot_id": slot["id"],
                    "start_time": slot["start_time"].isoformat(),
                    "end_time": slot["end_time"].isoformat(),
                    "booking_id": slot["booking_id"],
                    "student_id": slot["student_id"],
                    "service_name": slot["service_name"],
                    "status": slot["status"],
                }
            )

        return slots_by_date

    def validate_time_range(
        self,
        start_time: time,
        end_time: time,
        min_duration_minutes: int = 30,
        max_duration_minutes: int = 480,  # 8 hours
    ) -> Dict[str, Any]:
        """
        Validate a time range for basic constraints.

        Business logic - stays in service.

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

        # Calculate duration
        start = datetime.combine(date.today(), start_time)
        end = datetime.combine(date.today(), end_time)
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

    def check_minimum_advance_booking(
        self, instructor_id: int, booking_date: date, booking_time: time
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

        # Calculate booking datetime
        booking_datetime = datetime.combine(booking_date, booking_time)
        min_booking_time = datetime.now() + timedelta(hours=profile.min_advance_booking_hours)

        if booking_datetime < min_booking_time:
            hours_until_booking = (booking_datetime - datetime.now()).total_seconds() / 3600
            return {
                "valid": False,
                "reason": f"Bookings must be made at least {profile.min_advance_booking_hours} hours in advance",
                "min_advance_hours": profile.min_advance_booking_hours,
                "hours_until_booking": max(0, hours_until_booking),
            }

        return {"valid": True, "min_advance_hours": profile.min_advance_booking_hours}

    def find_overlapping_slots(
        self, instructor_id: int, target_date: date, start_time: time, end_time: time
    ) -> List[Dict[str, Any]]:
        """
        Find all slots that overlap with a given time range.

        Args:
            instructor_id: The instructor ID
            target_date: The date to check
            start_time: Start time of the range
            end_time: End time of the range

        Returns:
            List of overlapping slots
        """
        slots = self.repository.get_slots_for_date(instructor_id, target_date)

        # Get all slot IDs first
        slot_ids = [slot.id for slot in slots]

        # Pre-fetch bookings for all slots in one query
        booked_slot_ids = set()
        if slot_ids:
            from ..models.booking import Booking

            bookings = (
                self.db.query(Booking.availability_slot_id)
                .filter(
                    Booking.availability_slot_id.in_(slot_ids),
                    Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
                )
                .all()
            )
            booked_slot_ids = {b[0] for b in bookings}

        # Now check overlaps (business logic)
        overlapping = []
        for slot in slots:
            # Check if slots overlap
            if slot.start_time < end_time and slot.end_time > start_time:
                overlapping.append(
                    {
                        "slot_id": slot.id,
                        "start_time": slot.start_time.isoformat(),
                        "end_time": slot.end_time.isoformat(),
                        "has_booking": slot.id in booked_slot_ids,
                    }
                )

        return overlapping

    def check_blackout_date(self, instructor_id: int, target_date: date) -> bool:
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

    def validate_booking_constraints(
        self,
        instructor_id: int,
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

        # Check if date is in the past
        if booking_date < date.today():
            errors.append("Cannot book for past dates")
        elif booking_date == date.today() and start_time < datetime.now().time():
            errors.append("Cannot book for past time slots")

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
            elif service.duration_override:
                # Check if slot duration matches service duration
                duration_minutes = time_validation.get("duration_minutes", 0)
                if duration_minutes != service.duration_override:
                    warnings.append(
                        f"Service requires {service.duration_override} minutes, "
                        f"but slot is {duration_minutes} minutes"
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
