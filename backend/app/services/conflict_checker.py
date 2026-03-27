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

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
import logging
import math
import re
from typing import Any, Dict, List, Optional, cast

from sqlalchemy.orm import Session

from ..core.timezone_utils import get_user_today_by_id
from ..models.booking import BookingStatus
from ..models.instructor import InstructorProfile
from ..repositories import RepositoryFactory
from ..repositories.conflict_checker_repository import ConflictCheckerRepository
from ..utils.time_utils import time_to_minutes
from .base import BaseService
from .config_service import (
    ConfigService,
    is_instructor_travel_format,
    is_student_travel_format,
    normalize_location_type,
)

logger = logging.getLogger(__name__)

STUDENT_PROXIMITY_WARNING_MINUTES = 30
SAME_LOCATION_DISTANCE_MILES = 0.1
EARTH_RADIUS_MILES = 3958.7613
ADDRESS_NORMALIZER_RE = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class _LocationSnapshot:
    location_type: str | None
    location_address: str | None = None
    location_place_id: str | None = None
    location_lat: float | None = None
    location_lng: float | None = None


class ConflictChecker(BaseService):
    """
    Service for checking booking conflicts and time validation.

    This service centralizes all conflict detection logic to ensure
    consistent validation across the platform. Works entirely with
    booking data without referencing availability slots.
    """

    def __init__(
        self,
        db: Session,
        repository: Optional[ConflictCheckerRepository] = None,
        config_service: Optional[ConfigService] = None,
    ):
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
        self.config_service = config_service or ConfigService(db)

    @staticmethod
    def _coerce_buffer_minutes(value: object, default: int) -> int:
        if isinstance(value, bool):
            return default
        if isinstance(value, int):
            return max(0, value)
        if isinstance(value, float):
            return max(0, int(value))
        if isinstance(value, str):
            try:
                return max(0, int(value))
            except ValueError:
                return default
        return default

    def _get_booking_location_type(self, booking: Any) -> str | None:
        location_type = getattr(booking, "location_type", None)
        if location_type is None and getattr(booking, "status", None) in (
            BookingStatus.CONFIRMED,
            BookingStatus.PENDING,
        ):
            self.logger.warning(
                "Active booking %s missing location_type",
                getattr(booking, "id", "<unknown>"),
            )
        return cast(Optional[str], location_type)

    def _get_buffer_minutes(
        self,
        existing_location_type: str | None,
        new_location_type: str | None,
        instructor_profile: InstructorProfile | None,
        *,
        travel_default: int,
        non_travel_default: int,
        perspective: str,
    ) -> int:
        if perspective == "student":
            travel_required = is_student_travel_format(
                existing_location_type
            ) or is_student_travel_format(new_location_type)
        else:
            travel_required = is_instructor_travel_format(
                existing_location_type
            ) or is_instructor_travel_format(new_location_type)

        if instructor_profile is None:
            return travel_default if travel_required else non_travel_default

        if travel_required:
            return self._coerce_buffer_minutes(
                getattr(instructor_profile, "travel_buffer_minutes", None),
                travel_default,
            )
        return self._coerce_buffer_minutes(
            getattr(instructor_profile, "non_travel_buffer_minutes", None),
            non_travel_default,
        )

    @staticmethod
    def _coerce_optional_float(value: object) -> float | None:
        if value is None or isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                return None
        try:
            return float(cast(Any, value))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _clean_optional_string(value: object) -> str | None:
        if not isinstance(value, str):
            return None
        normalized = value.strip()
        return normalized or None

    @staticmethod
    def _normalize_address(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = ADDRESS_NORMALIZER_RE.sub(" ", value.casefold()).strip()
        return normalized or None

    def _location_snapshot_from_booking(self, booking: Any) -> _LocationSnapshot:
        return _LocationSnapshot(
            location_type=normalize_location_type(getattr(booking, "location_type", None)),
            location_address=self._clean_optional_string(
                getattr(booking, "location_address", None)
            ),
            location_place_id=self._clean_optional_string(
                getattr(booking, "location_place_id", None)
            ),
            location_lat=self._coerce_optional_float(getattr(booking, "location_lat", None)),
            location_lng=self._coerce_optional_float(getattr(booking, "location_lng", None)),
        )

    def _location_snapshot_from_values(
        self,
        *,
        location_type: str | None,
        location_address: str | None = None,
        location_place_id: str | None = None,
        location_lat: float | None = None,
        location_lng: float | None = None,
    ) -> _LocationSnapshot:
        return _LocationSnapshot(
            location_type=normalize_location_type(location_type),
            location_address=self._clean_optional_string(location_address),
            location_place_id=self._clean_optional_string(location_place_id),
            location_lat=self._coerce_optional_float(location_lat),
            location_lng=self._coerce_optional_float(location_lng),
        )

    @staticmethod
    def _distance_miles(
        first_lat: float,
        first_lng: float,
        second_lat: float,
        second_lng: float,
    ) -> float:
        first_lat_rad = math.radians(first_lat)
        second_lat_rad = math.radians(second_lat)
        delta_lat = math.radians(second_lat - first_lat)
        delta_lng = math.radians(second_lng - first_lng)

        haversine = (
            math.sin(delta_lat / 2) ** 2
            + math.cos(first_lat_rad) * math.cos(second_lat_rad) * math.sin(delta_lng / 2) ** 2
        )
        angular_distance = 2 * math.atan2(math.sqrt(haversine), math.sqrt(1 - haversine))
        return EARTH_RADIUS_MILES * angular_distance

    def _same_effective_location(
        self,
        first_location: _LocationSnapshot,
        second_location: _LocationSnapshot,
    ) -> bool:
        if first_location.location_type == "online" and second_location.location_type == "online":
            return True

        if (
            first_location.location_type == "student_location"
            and second_location.location_type == "student_location"
        ):
            return True

        physical_comparison_attempted = False

        if first_location.location_place_id and second_location.location_place_id:
            physical_comparison_attempted = True
            if first_location.location_place_id == second_location.location_place_id:
                return True

        if (
            first_location.location_lat is not None
            and first_location.location_lng is not None
            and second_location.location_lat is not None
            and second_location.location_lng is not None
        ):
            physical_comparison_attempted = True
            if (
                self._distance_miles(
                    first_location.location_lat,
                    first_location.location_lng,
                    second_location.location_lat,
                    second_location.location_lng,
                )
                <= SAME_LOCATION_DISTANCE_MILES
            ):
                return True

        first_normalized_address = self._normalize_address(first_location.location_address)
        second_normalized_address = self._normalize_address(second_location.location_address)
        if first_normalized_address and second_normalized_address:
            physical_comparison_attempted = True
            if first_normalized_address == second_normalized_address:
                return True

        if physical_comparison_attempted:
            return False

        return first_location.location_type == second_location.location_type

    @staticmethod
    def _gap_between_bookings(
        first_start: time,
        first_end: time,
        second_start: time,
        second_end: time,
    ) -> int:
        first_start_minutes = time_to_minutes(first_start, is_end_time=False)
        first_end_minutes = time_to_minutes(first_end, is_end_time=True)
        second_start_minutes = time_to_minutes(second_start, is_end_time=False)
        second_end_minutes = time_to_minutes(second_end, is_end_time=True)

        if first_end_minutes <= second_start_minutes:
            return second_start_minutes - first_end_minutes

        if second_end_minutes <= first_start_minutes:
            return first_start_minutes - second_end_minutes

        overlap_minutes = min(first_end_minutes, second_end_minutes) - max(
            first_start_minutes,
            second_start_minutes,
        )
        return -overlap_minutes

    @staticmethod
    def _format_booking_time(value: time) -> str:
        return value.strftime("%I:%M %p").lstrip("0")

    @staticmethod
    def _conflicts_with_buffer(
        first_start: time,
        first_end: time,
        second_start: time,
        second_end: time,
        buffer_minutes: int,
    ) -> bool:
        first_interval = (
            time_to_minutes(first_start, is_end_time=False),
            time_to_minutes(first_end, is_end_time=True),
        )
        second_interval = (
            time_to_minutes(second_start, is_end_time=False),
            time_to_minutes(second_end, is_end_time=True),
        )
        earlier_start, earlier_end = min(first_interval, second_interval)
        later_start, _later_end = max(first_interval, second_interval)
        return bool(later_start < earlier_end + max(0, buffer_minutes))

    @BaseService.measure_operation("check_booking_conflicts")
    def check_booking_conflicts(
        self,
        instructor_id: str,
        check_date: date,
        start_time: time,
        end_time: time,
        new_location_type: str | None = None,
        exclude_booking_id: Optional[str] = None,
        instructor_profile: InstructorProfile | None = None,
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
        exclude_id = str(exclude_booking_id) if exclude_booking_id is not None else None
        bookings = self.repository.get_bookings_for_conflict_check(
            instructor_id, check_date, exclude_id
        )
        profile = instructor_profile or self.repository.get_instructor_profile(instructor_id)
        normalized_new_location_type = normalize_location_type(new_location_type)
        booking_rules_config, _updated_at = self.config_service.get_booking_rules_config()
        travel_default = self.config_service.resolve_default_buffer_minutes_from_config(
            booking_rules_config, "student_location"
        )
        non_travel_default = self.config_service.resolve_default_buffer_minutes_from_config(
            booking_rules_config, "online"
        )

        conflicts = []
        for booking in bookings:
            buffer_minutes = self._get_buffer_minutes(
                self._get_booking_location_type(booking),
                normalized_new_location_type,
                profile,
                travel_default=travel_default,
                non_travel_default=non_travel_default,
                perspective="instructor",
            )
            if self._conflicts_with_buffer(
                booking.start_time,
                booking.end_time,
                start_time,
                end_time,
                buffer_minutes,
            ):
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
                "Found %s booking conflicts for %s on %s between %s-%s",
                len(conflicts),
                instructor_id,
                check_date,
                start_time,
                end_time,
            )

        return conflicts

    @BaseService.measure_operation("check_time_conflicts")
    def check_time_conflicts(
        self,
        instructor_id: str,
        booking_date: date,
        start_time: time,
        end_time: time,
        new_location_type: str | None = None,
        exclude_booking_id: Optional[str] = None,
        instructor_profile: InstructorProfile | None = None,
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
        conflicts = self.check_booking_conflicts(
            instructor_id,
            booking_date,
            start_time,
            end_time,
            new_location_type,
            exclude_booking_id,
            instructor_profile,
        )
        return len(conflicts) > 0

    @BaseService.measure_operation("check_student_booking_conflicts")
    def check_student_booking_conflicts(
        self,
        student_id: str,
        check_date: date,
        start_time: time,
        end_time: time,
        new_location_type: str | None = None,
        exclude_booking_id: Optional[str] = None,
        instructor_profile: InstructorProfile | None = None,
    ) -> List[Dict[str, Any]]:
        exclude_id = str(exclude_booking_id) if exclude_booking_id is not None else None
        bookings = self.repository.get_student_bookings_for_conflict_check(
            student_id, check_date, exclude_id
        )

        conflicts = []
        for booking in bookings:
            if self._conflicts_with_buffer(
                booking.start_time,
                booking.end_time,
                start_time,
                end_time,
                0,
            ):
                conflicts.append(
                    {
                        "booking_id": booking.id,
                        "start_time": str(booking.start_time),
                        "end_time": str(booking.end_time),
                        "service_name": booking.service_name,
                        "status": booking.status,
                        "instructor_id": booking.instructor_id,
                    }
                )

        return conflicts

    @BaseService.measure_operation("check_student_time_conflicts")
    def check_student_time_conflicts(
        self,
        student_id: str,
        booking_date: date,
        start_time: time,
        end_time: time,
        new_location_type: str | None = None,
        exclude_booking_id: Optional[str] = None,
        instructor_profile: InstructorProfile | None = None,
    ) -> bool:
        conflicts = self.check_student_booking_conflicts(
            student_id,
            booking_date,
            start_time,
            end_time,
            new_location_type,
            exclude_booking_id,
            instructor_profile,
        )
        return len(conflicts) > 0

    @BaseService.measure_operation("check_student_proximity_warnings")
    def check_student_proximity_warnings(
        self,
        student_id: str,
        check_date: date,
        start_time: time,
        end_time: time,
        location_type: str | None = None,
        exclude_booking_id: Optional[str] = None,
        location_address: str | None = None,
        location_place_id: str | None = None,
        location_lat: float | None = None,
        location_lng: float | None = None,
    ) -> List[Dict[str, Any]]:
        exclude_id = str(exclude_booking_id) if exclude_booking_id is not None else None
        bookings = self.repository.get_student_bookings_for_conflict_check(
            student_id, check_date, exclude_id
        )
        new_location = self._location_snapshot_from_values(
            location_type=location_type,
            location_address=location_address,
            location_place_id=location_place_id,
            location_lat=location_lat,
            location_lng=location_lng,
        )

        warnings: List[Dict[str, Any]] = []
        for booking in bookings:
            gap_minutes = self._gap_between_bookings(
                booking.start_time,
                booking.end_time,
                start_time,
                end_time,
            )
            if gap_minutes < 0 or gap_minutes >= STUDENT_PROXIMITY_WARNING_MINUTES:
                continue

            if self._same_effective_location(
                self._location_snapshot_from_booking(booking),
                new_location,
            ):
                continue

            service_name = (
                self._clean_optional_string(getattr(booking, "service_name", None)) or "lesson"
            )
            warnings.append(
                {
                    "type": "proximity",
                    "message": (
                        f"You have a {service_name} lesson at "
                        f"{self._format_booking_time(booking.start_time)} at a different location."
                    ),
                    "conflicting_booking_id": str(getattr(booking, "id", "")),
                    "conflicting_service": service_name,
                    "gap_minutes": gap_minutes,
                }
            )

        return warnings

    @BaseService.measure_operation("get_booked_times_date")
    def get_booked_times_for_date(
        self, instructor_id: str, target_date: date
    ) -> List[Dict[str, Any]]:
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
    def get_booked_times_for_week(
        self, instructor_id: str, week_start: date
    ) -> Dict[str, List[Dict[str, Any]]]:
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
        times_by_date: Dict[str, List[Dict[str, Any]]] = {}
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
        reference_date = date(2000, 1, 1)
        start = datetime.combine(  # tz-pattern-ok: duration math only
            reference_date, start_time, tzinfo=timezone.utc
        )
        end = datetime.combine(  # tz-pattern-ok: duration math only
            reference_date, end_time, tzinfo=timezone.utc
        )
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
        self,
        instructor_id: str,
        booking_date: date,
        booking_time: time,
        location_type: str | None = None,
        *,
        instructor_profile: InstructorProfile | None = None,
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
        profile = instructor_profile or self.repository.get_instructor_profile(instructor_id)

        if not profile:
            return {"valid": False, "reason": "Instructor profile not found"}

        # Get instructor for timezone calculations
        instructor = self.user_repository.get_by_id(instructor_id)
        if not instructor:
            return {"valid": False, "reason": "Instructor not found"}

        # Get instructor's current time
        from ..core.timezone_utils import get_user_now

        instructor_now = get_user_now(instructor)

        # Calculate booking datetime in instructor's timezone
        booking_datetime = datetime.combine(
            booking_date, booking_time, tzinfo=instructor_now.tzinfo
        )

        # Calculate minimum booking time
        min_advance_minutes = self.config_service.get_advance_notice_minutes(location_type)
        min_booking_time = instructor_now + timedelta(minutes=min_advance_minutes)

        # For comparison, we need to ensure both times are timezone-aware
        # Convert booking_datetime to instructor's timezone for fair comparison
        booking_datetime_tz = booking_datetime

        if booking_datetime_tz < min_booking_time:
            hours_until_booking = (booking_datetime_tz - instructor_now).total_seconds() / 3600
            return {
                "valid": False,
                "reason": (
                    "Bookings must be made at least "
                    f"{min_advance_minutes} minutes in advance (instructor timezone)"
                ),
                "min_advance_minutes": min_advance_minutes,
                "hours_until_booking": max(0, hours_until_booking),
            }

        return {"valid": True, "min_advance_minutes": min_advance_minutes}

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
        location_type: str | None = None,
        service_id: Optional[str] = None,
        student_id: str | None = None,
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
            errors.append("Cannot book for past dates (instructor timezone)")
        elif booking_date == instructor_today:
            # Get instructor's current time for same-day validation
            instructor = self.user_repository.get_by_id(instructor_id)
            if instructor:
                from ..core.timezone_utils import get_user_now

                instructor_now = get_user_now(instructor)
                if start_time < instructor_now.time():
                    errors.append("Cannot book for past time slots (instructor timezone)")

        profile = self.repository.get_instructor_profile(instructor_id)

        # Check minimum advance booking
        advance_check = self.check_minimum_advance_booking(
            instructor_id,
            booking_date,
            start_time,
            location_type,
            instructor_profile=profile,
        )
        if not advance_check["valid"]:
            errors.append(advance_check["reason"])

        # Check blackout date
        has_blackout = self.check_blackout_date(instructor_id, booking_date)
        if has_blackout:
            errors.append("Instructor is not available on this date")

        # Check for conflicts
        conflicts = self.check_booking_conflicts(
            instructor_id,
            booking_date,
            start_time,
            end_time,
            location_type,
            instructor_profile=profile,
        )
        if conflicts:
            errors.append(f"Time slot conflicts with {len(conflicts)} existing bookings")

        if student_id:
            student_conflicts = self.check_student_booking_conflicts(
                student_id,
                booking_date,
                start_time,
                end_time,
                location_type,
            )
            if student_conflicts:
                errors.append(
                    f"Time slot conflicts with {len(student_conflicts)} of the student's bookings"
                )
        else:
            student_conflicts = []

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
                        f"Service offers {service.duration_options} minutes, "
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
                "student_conflicts": student_conflicts,
                "has_blackout": has_blackout,
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
        reference_date = date(2000, 1, 1)

        for booking in active_bookings:
            # Calculate potential end time using reference date (timezone-agnostic)
            start_dt = datetime.combine(  # tz-pattern-ok: duration math only
                reference_date, current_time, tzinfo=timezone.utc
            )
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
        start_dt = datetime.combine(  # tz-pattern-ok: duration math only
            reference_date, current_time, tzinfo=timezone.utc
        )
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
