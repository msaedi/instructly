from __future__ import annotations

from datetime import date, datetime, time, timedelta
from types import ModuleType
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, cast

from ...core.constants import BOOKING_START_STEP_MINUTES, MINUTES_PER_SLOT, SLOTS_PER_DAY
from ...core.exceptions import BusinessRuleException, ValidationException
from ...models.booking import Booking
from ...models.instructor import InstructorProfile
from ...models.service_catalog import InstructorService
from ...models.user import User
from ...repositories.availability_day_repository import AvailabilityDayRepository
from ...schemas.booking import BookingCreate
from ...utils.bitset import get_slot_tag, is_tag_compatible, new_empty_tags
from ...utils.safe_cast import safe_float as _safe_float, safe_str as _safe_str
from ...utils.time_helpers import string_to_time
from ...utils.time_utils import time_to_minutes
from ..base import BaseService
from ..config_service import is_instructor_travel_format, normalize_location_type

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from ...repositories.availability_repository import AvailabilityRepository
    from ...repositories.booking_repository import BookingRepository
    from ...repositories.conflict_checker_repository import ConflictCheckerRepository
    from ...repositories.filter_repository import FilterRepository
    from ..config_service import ConfigService
    from ..conflict_checker import ConflictChecker


def _booking_service_module() -> ModuleType:
    from .. import booking_service as booking_service_module

    return booking_service_module


class BookingAvailabilityMixin:
    if TYPE_CHECKING:
        db: Session
        repository: BookingRepository
        availability_repository: AvailabilityRepository
        conflict_checker_repository: ConflictCheckerRepository
        conflict_checker: ConflictChecker
        filter_repository: FilterRepository
        config_service: ConfigService

        def _resolve_instructor_timezone(self, instructor_profile: InstructorProfile) -> str:
            ...

        def _resolve_lesson_timezone(
            self,
            booking_data: BookingCreate,
            instructor_profile: InstructorProfile,
        ) -> str:
            ...

        def _resolve_booking_times_utc(
            self,
            booking_date: date,
            start_time: time,
            end_time: time,
            lesson_timezone: str,
        ) -> tuple[datetime, datetime]:
            ...

        def _build_conflict_details(
            self,
            booking_data: BookingCreate,
            student_id: Optional[str],
        ) -> dict[str, str]:
            ...

        @staticmethod
        def _validate_min_session_duration_floor(duration_minutes: int) -> None:
            ...

        def _calculate_and_validate_end_time(
            self,
            booking_date: date,
            start_time: time,
            selected_duration: int,
        ) -> time:
            ...

    @staticmethod
    def _time_to_minutes(value: time, *, is_end_time: bool = False) -> int:
        """Return minutes since midnight for a time value."""
        minutes: int = time_to_minutes(value, is_end_time=is_end_time)
        return minutes

    @staticmethod
    def _minutes_to_time(value: int) -> time:
        """Convert minutes since midnight to a time (wrap 24:00 as 00:00)."""
        if value >= 24 * 60:
            return time(0, 0)
        return time(value // 60, value % 60)

    @staticmethod
    def _bitmap_str_to_minutes(value: str, *, is_end_time: bool = False) -> int:
        """Convert bitmap strings (e.g., '24:00:00') into minute offsets."""
        if value.startswith("24:"):
            is_end_time = True
        minutes: int = time_to_minutes(string_to_time(value), is_end_time=is_end_time)
        return minutes

    @staticmethod
    def _booking_window_to_minutes(booking: Booking) -> tuple[int, int]:
        """Convert a booking's start/end times into minute offsets."""
        if not booking.start_time or not booking.end_time:
            return 0, 0
        start = BookingAvailabilityMixin._time_to_minutes(booking.start_time, is_end_time=False)
        end = BookingAvailabilityMixin._time_to_minutes(booking.end_time, is_end_time=True)
        if end <= start:
            end = 24 * 60
        return start, end

    def _resolve_local_booking_day(
        self,
        booking_data: BookingCreate,
        instructor_profile: InstructorProfile,
    ) -> date:
        """Return the instructor-local date for availability lookup.

        Booking requests send instructor-local dates/times, and availability
        is stored in instructor-local days. No conversion is needed here.
        """
        # Client and availability are instructor-local; use the provided date as-is.
        result: date = booking_data.booking_date
        return result

    def _get_day_bitmaps(self, instructor_id: str, day: date) -> tuple[bytes, bytes]:
        """Return (bits, format_tags) for a day, defaulting tags to all-zero."""
        repo = getattr(self, "availability_repository", None)
        if repo is None or (
            not hasattr(repo, "get_day_bitmaps") and not hasattr(repo, "get_day_bits")
        ):
            repo = AvailabilityDayRepository(self.db)

        if hasattr(repo, "get_day_bitmaps"):
            bitmaps = repo.get_day_bitmaps(instructor_id, day)
            if bitmaps is not None:
                return cast(tuple[bytes, bytes], bitmaps)

        bits = repo.get_day_bits(instructor_id, day) if hasattr(repo, "get_day_bits") else None
        return (bits or b"", new_empty_tags())

    def _get_bitmap_availability_error(
        self,
        instructor_id: str,
        day: date,
        start_index: int,
        end_index: int,
        *,
        location_type: str | None,
    ) -> str | None:
        """Return a user-facing availability error when bits or tags reject the request."""
        bits, format_tags = self._get_day_bitmaps(instructor_id, day)
        for idx in range(start_index, end_index):
            byte_i = idx // 8
            bit_mask = 1 << (idx % 8)
            if byte_i >= len(bits) or (bits[byte_i] & bit_mask) == 0:
                return "Requested time is not available"

        normalized_location_type = normalize_location_type(location_type)
        for idx in range(start_index, end_index):
            tag = get_slot_tag(format_tags, idx)
            if not is_tag_compatible(tag, normalized_location_type):
                return "This time slot is not available for the selected lesson format"

        return None

    def _validate_against_availability_bits(
        self,
        booking_data: BookingCreate,
        instructor_profile: InstructorProfile,
    ) -> None:
        start_time_value = booking_data.start_time
        end_time_value = booking_data.end_time
        if start_time_value is None or end_time_value is None:
            raise ValidationException(
                "Start and end time must be specified for availability checks"
            )

        # Enforce 15-minute booking boundary
        start_minutes = time_to_minutes(start_time_value)
        if start_minutes % BOOKING_START_STEP_MINUTES != 0:
            raise BusinessRuleException(
                f"Booking start time must be on a {BOOKING_START_STEP_MINUTES}-minute boundary",
                code="INVALID_START_TIME",
            )

        start_index = start_minutes // MINUTES_PER_SLOT
        end_minutes = time_to_minutes(end_time_value, is_end_time=True)
        end_index = end_minutes // MINUTES_PER_SLOT

        if (
            not (0 <= start_index < SLOTS_PER_DAY)
            or not (0 < end_index <= SLOTS_PER_DAY)
            or start_index >= end_index
        ):
            raise BusinessRuleException("Requested time is not available")

        local_day = self._resolve_local_booking_day(booking_data, instructor_profile)
        error_message = self._get_bitmap_availability_error(
            booking_data.instructor_id,
            local_day,
            start_index,
            end_index,
            location_type=booking_data.location_type,
        )
        if error_message:
            error_code = (
                "FORMAT_TAG_INCOMPATIBLE"
                if error_message == "This time slot is not available for the selected lesson format"
                else None
            )
            raise BusinessRuleException(error_message, code=error_code)

    @BaseService.measure_operation("find_booking_opportunities")
    def find_booking_opportunities(
        self,
        instructor_id: str,
        target_date: date,
        target_duration_minutes: int = 60,
        earliest_time: Optional[time] = None,
        latest_time: Optional[time] = None,
    ) -> List[Dict[str, Any]]:
        """
        Find available time slots for booking based on instructor availability.

        REFACTORED: Split into helper methods to stay under 50 lines.

        Args:
            instructor_id: The instructor ID
            target_date: The date to check
            target_duration_minutes: Desired booking duration
            earliest_time: Earliest acceptable time (default 9 AM)
            latest_time: Latest acceptable time (default 9 PM)

        Returns:
            List of available time slots for booking
        """
        # Set defaults
        if not earliest_time:
            earliest_time = time(9, 0)
        if not latest_time:
            latest_time = time(21, 0)

        # Get availability data
        availability_windows = self._get_instructor_availability_windows(
            instructor_id, target_date, earliest_time, latest_time
        )

        existing_bookings = self._get_existing_bookings_for_date(
            instructor_id, target_date, earliest_time, latest_time
        )

        # Find opportunities
        opportunities = self._calculate_booking_opportunities(
            availability_windows,
            existing_bookings,
            target_duration_minutes,
            earliest_time,
            latest_time,
            instructor_id,
            target_date,
        )

        return opportunities

    @BaseService.measure_operation("check_availability")
    def check_availability(
        self,
        instructor_id: str,
        booking_date: date,
        start_time: time,
        end_time: time,
        service_id: Optional[str] = None,
        instructor_service_id: Optional[str] = None,
        exclude_booking_id: Optional[str] = None,
        location_type: Optional[str] = None,
        student_id: Optional[str] = None,
        selected_duration: Optional[int] = None,
        location_address: Optional[str] = None,
        location_place_id: Optional[str] = None,
        location_lat: Optional[float] = None,
        location_lng: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Check if a time range is available for booking.

        Args:
            instructor_id: The instructor ID
            booking_date: The date to check
            start_time: Start time
            end_time: End time
            service_id: Service ID

        Returns:
            Dictionary with availability status and details
        """
        # Enforce 15-minute booking boundary
        start_minutes = time_to_minutes(start_time)
        if start_minutes % BOOKING_START_STEP_MINUTES != 0:
            return {
                "available": False,
                "reason": f"Start time must be on a {BOOKING_START_STEP_MINUTES}-minute boundary",
            }

        resolved_service_id = service_id or instructor_service_id
        if not resolved_service_id:
            return {"available": False, "reason": "Service not found or no longer available"}

        normalized_location_type = normalize_location_type(location_type)
        exclude_id = str(exclude_booking_id) if exclude_booking_id is not None else None

        # Get service and instructor profile using repositories
        service = self.conflict_checker_repository.get_active_service(resolved_service_id)
        if not service:
            return {"available": False, "reason": "Service not found or no longer available"}

        # Get instructor profile
        instructor_profile = self.conflict_checker_repository.get_instructor_profile(instructor_id)
        if instructor_profile is None:
            return {
                "available": False,
                "reason": "Instructor profile not found",
            }

        try:
            self._validate_location_capability(service, normalized_location_type)
        except ValidationException as exc:
            return {
                "available": False,
                "reason": str(exc),
            }

        try:
            self._validate_selected_duration_for_service(
                service=service,
                booking_date=booking_date,
                start_time=start_time,
                end_time=end_time,
                selected_duration=selected_duration,
            )
        except ValidationException as exc:
            return {
                "available": False,
                "reason": str(exc),
            }

        try:
            self._validate_service_area_for_availability_check(
                instructor_id=instructor_id,
                service=service,
                location_type=normalized_location_type,
                location_lat=location_lat,
                location_lng=location_lng,
            )
        except ValidationException as exc:
            return {
                "available": False,
                "reason": str(exc),
            }

        booking_service_module = _booking_service_module()

        # Check minimum advance booking using UTC.
        min_advance_minutes = self._get_advance_notice_minutes(normalized_location_type)
        now_utc = booking_service_module.datetime.now(booking_service_module.timezone.utc)
        instructor_tz = self._resolve_instructor_timezone(instructor_profile)
        lesson_tz = booking_service_module.TimezoneService.get_lesson_timezone(
            instructor_tz,
            is_online=normalized_location_type == "online",
        )
        try:
            booking_start_utc, _ = self._resolve_booking_times_utc(
                booking_date,
                start_time,
                end_time,
                lesson_tz,
            )
        except BusinessRuleException as exc:
            return {"available": False, "reason": str(exc)}

        # For >=24 hour min advance, use date-level granularity to avoid HH:MM boundary flakiness
        if min_advance_minutes >= 24 * 60:
            min_booking_dt = now_utc + timedelta(minutes=min_advance_minutes)
            min_date_only = min_booking_dt.date()

            if booking_start_utc.date() < min_date_only or (
                booking_start_utc.date() == min_date_only
                and booking_start_utc.time() < min_booking_dt.time()
            ):
                return {
                    "available": False,
                    "reason": (
                        f"Must book at least {self._format_advance_notice(min_advance_minutes)} "
                        "in advance"
                    ),
                    "min_advance_minutes": min_advance_minutes,
                }
        else:
            # For <24 hour min advance, do precise time comparison
            minutes_until = (booking_start_utc - now_utc).total_seconds() / 60
            if minutes_until < min_advance_minutes:
                return {
                    "available": False,
                    "reason": (
                        f"Must book at least {self._format_advance_notice(min_advance_minutes)} "
                        "in advance"
                    ),
                    "min_advance_minutes": min_advance_minutes,
                }

        booking_time_local = booking_service_module.TimezoneService.utc_to_local(
            now_utc, instructor_tz
        )
        lesson_start_local = booking_service_module.TimezoneService.utc_to_local(
            booking_start_utc, instructor_tz
        )
        try:
            self._check_overnight_protection(
                booking_time_local,
                lesson_start_local,
                normalized_location_type,
                instructor_profile,
            )
        except BusinessRuleException as exc:
            return {"available": False, "reason": str(exc)}

        has_conflict = self.conflict_checker.check_time_conflicts(
            instructor_id=instructor_id,
            booking_date=booking_date,
            start_time=start_time,
            end_time=end_time,
            new_location_type=normalized_location_type,
            exclude_booking_id=exclude_booking_id,
            instructor_profile=instructor_profile,
        )
        if has_conflict:
            return {"available": False, "reason": "Time slot has conflicts with existing bookings"}

        existing_student_bookings: Optional[List[Any]] = None
        if student_id:
            existing_student_bookings = (
                self.conflict_checker_repository.get_student_bookings_for_conflict_check(
                    student_id,
                    booking_date,
                    exclude_id,
                )
            )
            student_conflicts = self.conflict_checker.check_student_booking_conflicts(
                student_id=student_id,
                check_date=booking_date,
                start_time=start_time,
                end_time=end_time,
                exclude_booking_id=exclude_booking_id,
                existing_bookings=existing_student_bookings,
            )
            if student_conflicts:
                return {
                    "available": False,
                    "reason": self._build_student_conflict_reason(
                        student_conflicts[0],
                        booking_date,
                    ),
                }

        # Verify bitmap availability covers the requested range
        start_index = start_minutes // MINUTES_PER_SLOT
        end_minutes = time_to_minutes(end_time, is_end_time=True)
        end_index = end_minutes // MINUTES_PER_SLOT

        if (
            not (0 <= start_index < SLOTS_PER_DAY)
            or not (0 < end_index <= SLOTS_PER_DAY)
            or start_index >= end_index
        ):
            return {"available": False, "reason": "Requested time is not available"}

        error_message = self._get_bitmap_availability_error(
            instructor_id,
            booking_date,
            start_index,
            end_index,
            location_type=normalized_location_type,
        )
        if error_message:
            return {
                "available": False,
                "reason": error_message,
            }

        proximity_warnings: Optional[List[Dict[str, Any]]] = None
        if student_id:
            (
                warning_location_address,
                warning_location_place_id,
                warning_location_lat,
                warning_location_lng,
            ) = self._resolve_availability_location_fields(
                location_type=normalized_location_type,
                instructor_profile=instructor_profile,
                location_address=location_address,
                location_place_id=location_place_id,
                location_lat=location_lat,
                location_lng=location_lng,
            )
            proximity_warnings = self.conflict_checker.check_student_proximity_warnings(
                student_id=student_id,
                check_date=booking_date,
                start_time=start_time,
                end_time=end_time,
                location_type=normalized_location_type,
                exclude_booking_id=exclude_booking_id,
                location_address=warning_location_address,
                location_place_id=warning_location_place_id,
                location_lat=warning_location_lat,
                location_lng=warning_location_lng,
                existing_bookings=existing_student_bookings,
            )

        return {
            "available": True,
            "warnings": proximity_warnings or None,
            "time_info": {
                "date": booking_date.isoformat(),
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "instructor_id": instructor_id,
            },
        }

    def _get_primary_teaching_location(
        self,
        instructor_profile: InstructorProfile,
    ) -> object | None:
        user = getattr(instructor_profile, "user", None)
        preferred_places = getattr(user, "preferred_places", None)
        if preferred_places is None:
            return None

        for place in preferred_places:
            if getattr(place, "kind", None) == "teaching_location":
                return cast(object, place)

        return None

    def _resolve_availability_location_fields(
        self,
        *,
        location_type: str | None,
        instructor_profile: InstructorProfile,
        location_address: str | None = None,
        location_place_id: str | None = None,
        location_lat: float | None = None,
        location_lng: float | None = None,
    ) -> Tuple[str | None, str | None, float | None, float | None]:
        normalized_location_type = normalize_location_type(location_type)
        if normalized_location_type == "online":
            return None, None, None, None

        if normalized_location_type == "instructor_location":
            teaching_location = self._get_primary_teaching_location(instructor_profile)
            if teaching_location is None:
                return None, None, None, None

            return (
                _safe_str(getattr(teaching_location, "address", None)),
                _safe_str(getattr(teaching_location, "place_id", None)),
                _safe_float(getattr(teaching_location, "lat", None)),
                _safe_float(getattr(teaching_location, "lng", None)),
            )

        return (
            _safe_str(location_address),
            _safe_str(location_place_id),
            _safe_float(location_lat),
            _safe_float(location_lng),
        )

    @staticmethod
    def _format_conflict_reason_time(start_time: object) -> str:
        if isinstance(start_time, time):
            return start_time.strftime("%I:%M %p").lstrip("0")
        if isinstance(start_time, str):
            try:
                parsed_time = string_to_time(start_time)
            except ValueError:
                return start_time
            return parsed_time.strftime("%I:%M %p").lstrip("0")
        return "Unknown time"

    @classmethod
    def _build_student_conflict_reason(
        cls,
        conflict: Dict[str, Any],
        booking_date: date,
    ) -> str:
        service_name = _safe_str(conflict.get("service_name")) or "lesson"
        lesson_label = (
            "a lesson" if service_name.casefold() == "lesson" else f"a {service_name} lesson"
        )
        formatted_time = cls._format_conflict_reason_time(conflict.get("start_time"))
        formatted_date = booking_date.strftime("%A, %B %d").replace(" 0", " ")
        return f"You already have {lesson_label} at {formatted_time} on {formatted_date}"

    def _neutral_location_uses_service_area(self, service: InstructorService) -> bool:
        """Neutral-location bookings only need service-area coverage when they fall back to travel."""
        offers_at_location = bool(getattr(service, "offers_at_location", False))
        offers_travel = bool(getattr(service, "offers_travel", False))
        return (not offers_at_location) and offers_travel

    def _get_advance_notice_minutes(self, location_type: Optional[str] = None) -> int:
        """Resolve advance-notice minutes from platform configuration."""
        return int(self.config_service.get_advance_notice_minutes(location_type))

    def _get_overnight_earliest_hour(self, location_type: Optional[str] = None) -> int:
        """Resolve the earliest locally-bookable hour during overnight protection."""
        return int(self.config_service.get_overnight_earliest_hour(location_type))

    def _is_in_overnight_window(self, booking_time_local: datetime) -> bool:
        """Return whether the request is being made inside the overnight booking window."""
        return bool(self.config_service.is_in_overnight_window(booking_time_local))

    @staticmethod
    def _format_advance_notice(minutes: int) -> str:
        """Human-readable advance-notice text for validation messages."""
        if minutes % 60 == 0:
            hours = minutes // 60
            suffix = "" if hours == 1 else "s"
            return f"{hours} hour{suffix}"
        suffix = "" if minutes == 1 else "s"
        return f"{minutes} minute{suffix}"

    def _check_overnight_protection(
        self,
        booking_time_local: datetime,
        lesson_start_local: datetime,
        location_type: str,
        instructor_profile: InstructorProfile,
    ) -> None:
        """Block protected early-morning lessons when booked overnight."""
        if not bool(getattr(instructor_profile, "overnight_protection_enabled", True)):
            return

        normalized_location_type = normalize_location_type(location_type)
        earliest_hour = self._get_overnight_earliest_hour(normalized_location_type)
        start_hour, _window_end_hour = self.config_service.get_overnight_window_hours()

        if booking_time_local.hour >= start_hour:
            protected_lesson_date = booking_time_local.date() + timedelta(days=1)
        elif booking_time_local.hour < earliest_hour:
            protected_lesson_date = booking_time_local.date()
        else:
            return

        if lesson_start_local.date() != protected_lesson_date:
            return

        if 0 <= lesson_start_local.hour < earliest_hour:
            lesson_descriptor = (
                "travel lessons"
                if is_instructor_travel_format(normalized_location_type)
                else "lessons"
            )
            raise BusinessRuleException(
                f"Early morning {lesson_descriptor} cannot be booked overnight",
                code="OVERNIGHT_PROTECTION",
            )

    def _validate_service_area(
        self,
        booking_data: BookingCreate,
        instructor_id: str,
        service: Optional[InstructorService] = None,
    ) -> None:
        """
        Ensure travel-based bookings fall within the instructor's service area.
        """
        if booking_data.location_type == "student_location":
            pass
        elif booking_data.location_type == "neutral_location":
            if service is not None and not self._neutral_location_uses_service_area(service):
                return
        else:
            return

        if booking_data.location_lat is None or booking_data.location_lng is None:
            raise ValidationException(
                "Coordinates are required to validate service area",
                code="COORDINATES_REQUIRED",
            )

        is_covered = self.filter_repository.is_location_in_service_area(
            instructor_id=instructor_id,
            lat=float(booking_data.location_lat),
            lng=float(booking_data.location_lng),
        )
        if not is_covered:
            raise ValidationException(
                "This location is outside the instructor's service area. "
                "Please choose a different location or select a different instructor.",
                code="OUTSIDE_SERVICE_AREA",
            )

    def _validate_service_area_for_availability_check(
        self,
        *,
        instructor_id: str,
        service: InstructorService,
        location_type: Optional[str],
        location_lat: Optional[float],
        location_lng: Optional[float],
    ) -> None:
        """Apply service-area validation parity for availability checks when coordinates exist."""
        normalized_location_type = normalize_location_type(location_type)
        if normalized_location_type == "student_location":
            pass
        elif normalized_location_type == "neutral_location":
            if not self._neutral_location_uses_service_area(service):
                return
        else:
            return

        if location_lat is None or location_lng is None:
            return

        is_covered = self.filter_repository.is_location_in_service_area(
            instructor_id=instructor_id,
            lat=float(location_lat),
            lng=float(location_lng),
        )
        if not is_covered:
            raise ValidationException(
                "This location is outside the instructor's service area. "
                "Please choose a different location or select a different instructor.",
                code="OUTSIDE_SERVICE_AREA",
            )

    def _validate_selected_duration_for_service(
        self,
        *,
        service: InstructorService,
        booking_date: date,
        start_time: time,
        end_time: time,
        selected_duration: Optional[int],
    ) -> None:
        """Validate optional duration input so availability preflights match booking creation."""
        if selected_duration is None:
            return

        self._validate_min_session_duration_floor(selected_duration)

        raw_duration_options = getattr(service, "duration_options", None)
        duration_options = (
            list(raw_duration_options)
            if isinstance(raw_duration_options, (list, tuple, set))
            else []
        )

        if selected_duration not in duration_options:
            raise ValidationException(
                f"Invalid duration {selected_duration}. Available options: {duration_options}"
            )

        calculated_end_time = self._calculate_and_validate_end_time(
            booking_date,
            start_time,
            selected_duration,
        )
        if calculated_end_time != end_time:
            raise ValidationException("Selected duration does not match the requested time range")

    def _validate_location_capability(
        self, service: InstructorService, location_type: Optional[str]
    ) -> None:
        """Validate that the instructor offers the requested location type."""
        if not location_type:
            location_type = "online"
        offers_travel = bool(getattr(service, "offers_travel", False))
        offers_at_location = bool(getattr(service, "offers_at_location", False))
        offers_online = bool(getattr(service, "offers_online", False))

        if location_type == "student_location" and not offers_travel:
            raise ValidationException(
                "This instructor doesn't travel for this service",
                code="TRAVEL_NOT_OFFERED",
            )

        if location_type == "neutral_location" and not (offers_travel or offers_at_location):
            raise ValidationException(
                "This instructor doesn't offer in-person lessons for this service",
                code="IN_PERSON_NOT_OFFERED",
            )

        if location_type == "instructor_location" and not offers_at_location:
            raise ValidationException(
                "This instructor doesn't offer lessons at their location for this service",
                code="AT_LOCATION_NOT_OFFERED",
            )

        if location_type == "online" and not offers_online:
            raise ValidationException(
                "This instructor doesn't offer online lessons for this service",
                code="ONLINE_NOT_OFFERED",
            )

        # Verify the location_type has a matching format price configured.
        # The offers_* checks above guard capability; this guards pricing data.
        if hasattr(service, "format_for_booking_location_type"):
            try:
                service.format_for_booking_location_type(location_type)
            except BusinessRuleException:
                raise ValidationException(
                    "This instructor doesn't offer lessons at that location type",
                    code="LOCATION_TYPE_PRICING_NOT_FOUND",
                )

    def _check_conflicts_and_rules(
        self,
        booking_data: BookingCreate,
        service: InstructorService,
        instructor_profile: InstructorProfile,
        student: Optional[User] = None,
        exclude_booking_id: Optional[str] = None,
    ) -> None:
        """
        Check for time conflicts and apply business rules.

        Args:
            booking_data: Booking creation data
            service: The service being booked
            instructor_profile: Instructor's profile
            student: The student making the booking (for student conflict checks)
            exclude_booking_id: Optional booking ID to exclude (for updates)

        Raises:
            ConflictException: If time slot conflicts
            BusinessRuleException: If business rules violated
        """
        booking_service_module = _booking_service_module()

        # Check for instructor time conflicts
        if booking_data.end_time is None:
            raise ValidationException("End time must be specified before conflict checks")

        normalized_location_type = normalize_location_type(booking_data.location_type)

        self._validate_location_capability(service, normalized_location_type)
        self._validate_service_area(booking_data, booking_data.instructor_id, service)

        lesson_tz = self._resolve_lesson_timezone(booking_data, instructor_profile)
        booking_start_utc, _ = self._resolve_booking_times_utc(
            booking_data.booking_date,
            booking_data.start_time,
            booking_data.end_time,
            lesson_tz,
        )

        # Check minimum advance booking time (UTC)
        # For >=24 hour advance notice, enforce on date granularity to avoid HH:MM boundary flakiness
        min_advance_minutes = self._get_advance_notice_minutes(normalized_location_type)
        now_utc = booking_service_module.datetime.now(booking_service_module.timezone.utc)

        if min_advance_minutes >= 24 * 60:
            min_booking_dt = now_utc + timedelta(minutes=min_advance_minutes)
            min_date_only = min_booking_dt.date()

            if booking_start_utc.date() < min_date_only or (
                booking_start_utc.date() == min_date_only
                and booking_start_utc.time() < min_booking_dt.time()
            ):
                raise BusinessRuleException(
                    "Bookings must be made at least "
                    f"{self._format_advance_notice(min_advance_minutes)} in advance"
                )
        else:
            minutes_until = (booking_start_utc - now_utc).total_seconds() / 60
            if minutes_until < min_advance_minutes:
                raise BusinessRuleException(
                    "Bookings must be made at least "
                    f"{self._format_advance_notice(min_advance_minutes)} in advance"
                )

        instructor_tz = self._resolve_instructor_timezone(instructor_profile)
        booking_time_local = booking_service_module.TimezoneService.utc_to_local(
            now_utc, instructor_tz
        )
        lesson_start_local = booking_service_module.TimezoneService.utc_to_local(
            booking_start_utc, instructor_tz
        )
        self._check_overnight_protection(
            booking_time_local,
            lesson_start_local,
            normalized_location_type,
            instructor_profile,
        )

        existing_conflicts = self.conflict_checker.check_booking_conflicts(
            instructor_id=booking_data.instructor_id,
            check_date=booking_data.booking_date,
            start_time=booking_data.start_time,
            end_time=booking_data.end_time,
            new_location_type=normalized_location_type,
            exclude_booking_id=exclude_booking_id,
            instructor_profile=instructor_profile,
        )

        if existing_conflicts:
            conflict_details = self._build_conflict_details(
                booking_data, getattr(student, "id", None)
            )
            conflict_details["conflict_scope"] = "instructor"
            raise booking_service_module.BookingConflictException(
                message=booking_service_module.INSTRUCTOR_CONFLICT_MESSAGE,
                details=conflict_details,
            )

        # Check for student time conflicts
        if student:
            student_conflicts = self.conflict_checker.check_student_booking_conflicts(
                student_id=student.id,
                check_date=booking_data.booking_date,
                start_time=booking_data.start_time,
                end_time=booking_data.end_time,
                exclude_booking_id=exclude_booking_id,
            )

            if student_conflicts:
                conflict_details = self._build_conflict_details(booking_data, student.id)
                conflict_details["conflict_scope"] = "student"
                raise booking_service_module.BookingConflictException(
                    message=booking_service_module.STUDENT_CONFLICT_MESSAGE,
                    details=conflict_details,
                )

    def _get_instructor_availability_windows(
        self,
        instructor_id: str,
        target_date: date,
        earliest_time: time,
        latest_time: time,
    ) -> List[dict[str, Any]]:
        """
        Get instructor's availability windows for the date (bitmap storage).

        Args:
            instructor_id: The instructor ID
            target_date: The date to check
            earliest_time: Earliest time boundary
            latest_time: Latest time boundary

        Returns:
            List of availability windows as dicts
        """
        # Use bitmap storage to get windows
        from ...utils.bitset import windows_from_bits

        repo = AvailabilityDayRepository(self.db)
        bits = repo.get_day_bits(instructor_id, target_date)
        if not bits:
            return []

        windows_str: list[tuple[str, str]] = windows_from_bits(bits)
        earliest_minutes = self._time_to_minutes(earliest_time, is_end_time=False)
        latest_minutes = self._time_to_minutes(latest_time, is_end_time=True)
        result: list[dict[str, Any]] = []
        for start_str, end_str in windows_str:
            start_minutes = self._bitmap_str_to_minutes(start_str, is_end_time=False)
            end_minutes = self._bitmap_str_to_minutes(end_str, is_end_time=True)
            if end_minutes <= earliest_minutes or start_minutes >= latest_minutes:
                continue
            result.append(
                {
                    "start_time": self._minutes_to_time(start_minutes),
                    "end_time": self._minutes_to_time(end_minutes),
                    "specific_date": target_date,
                    "_start_minutes": start_minutes,
                    "_end_minutes": end_minutes,
                }
            )
        return result

    def _get_existing_bookings_for_date(
        self,
        instructor_id: str,
        target_date: date,
        earliest_time: time,
        latest_time: time,
    ) -> List[Booking]:
        """
        Get existing bookings for the instructor on the date.

        Args:
            instructor_id: The instructor ID
            target_date: The date to check
            earliest_time: Earliest time boundary
            latest_time: Latest time boundary

        Returns:
            List of existing bookings
        """
        bookings: List[Booking] = self.repository.get_bookings_by_time_range(
            instructor_id=instructor_id,
            booking_date=target_date,
            start_time=earliest_time,
            end_time=latest_time,
        )
        return bookings

    def _calculate_booking_opportunities(
        self,
        availability_windows: List[dict[str, Any]],  # Bitmap windows as dicts
        existing_bookings: List[Booking],
        target_duration_minutes: int,
        earliest_time: time,
        latest_time: time,
        instructor_id: str,
        target_date: date,
    ) -> List[Dict[str, Any]]:
        """
        Calculate available booking opportunities from windows and bookings.

        Args:
            availability_windows: Available time windows (as dicts)
            existing_bookings: Existing bookings
            target_duration_minutes: Desired duration
            earliest_time: Earliest boundary
            latest_time: Latest boundary
            instructor_id: Instructor ID
            target_date: Target date

        Returns:
            List of booking opportunities
        """
        opportunities: List[Dict[str, Any]] = []
        earliest_minutes = self._time_to_minutes(earliest_time, is_end_time=False)
        latest_minutes = self._time_to_minutes(latest_time, is_end_time=True)

        for window in availability_windows:
            slot_start = max(window["_start_minutes"], earliest_minutes)
            slot_end = min(window["_end_minutes"], latest_minutes)
            if slot_end <= slot_start:
                continue

            # Find opportunities within this slot
            opportunities.extend(
                self._find_opportunities_in_slot(
                    slot_start,
                    slot_end,
                    existing_bookings,
                    target_duration_minutes,
                    instructor_id,
                    target_date,
                )
            )

        return opportunities

    def _find_opportunities_in_slot(
        self,
        slot_start: int,
        slot_end: int,
        existing_bookings: List[Booking],
        target_duration_minutes: int,
        instructor_id: str,
        target_date: date,
    ) -> List[Dict[str, Any]]:
        """
        Find booking opportunities within a single availability slot.

        Args:
            slot_start: Start of availability slot (minutes since midnight)
            slot_end: End of availability slot (minutes since midnight)
            existing_bookings: List of existing bookings
            target_duration_minutes: Desired booking duration
            instructor_id: Instructor ID
            target_date: Target date

        Returns:
            List of opportunities in this slot
        """
        opportunities: List[Dict[str, Any]] = []
        current_minutes = slot_start
        booking_windows = [
            self._booking_window_to_minutes(booking) for booking in existing_bookings if booking
        ]

        while current_minutes + target_duration_minutes <= slot_end:
            potential_end = current_minutes + target_duration_minutes

            has_conflict = False
            for booking_start, booking_end in booking_windows:
                if current_minutes < booking_end and potential_end > booking_start:
                    current_minutes = max(current_minutes, booking_end)
                    has_conflict = True
                    break

            if has_conflict:
                continue

            opportunities.append(
                {
                    "start_time": self._minutes_to_time(current_minutes).isoformat(),
                    "end_time": self._minutes_to_time(potential_end).isoformat(),
                    "duration_minutes": target_duration_minutes,
                    "available": True,
                    "instructor_id": instructor_id,
                    "date": target_date.isoformat(),
                }
            )

            current_minutes = potential_end

        return opportunities

    @BaseService.measure_operation("check_student_time_conflict")
    def check_student_time_conflict(
        self,
        student_id: str,
        booking_date: "date",
        start_time: "time",
        end_time: "time",
        location_type: Optional[str] = None,
        exclude_booking_id: Optional[str] = None,
    ) -> bool:
        """
        Check if student has a conflicting booking at the given time.

        Args:
            student_id: Student ULID
            booking_date: Date to check
            start_time: Start time
            end_time: End time
            exclude_booking_id: Optional booking to exclude from check

        Returns:
            True if there's a conflict, False otherwise
        """
        try:
            conflicting = self.conflict_checker.check_student_time_conflicts(
                student_id=student_id,
                booking_date=booking_date,
                start_time=start_time,
                end_time=end_time,
                exclude_booking_id=exclude_booking_id,
            )
            return bool(conflicting)
        except Exception:
            return False
