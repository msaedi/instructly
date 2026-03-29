from __future__ import annotations

from datetime import date, time
from typing import TYPE_CHECKING, Any, Dict, List, Optional, cast

from ...core.constants import BOOKING_START_STEP_MINUTES, MINUTES_PER_SLOT, SLOTS_PER_DAY
from ...core.exceptions import BusinessRuleException, ValidationException
from ...models.booking import Booking
from ...models.instructor import InstructorProfile
from ...repositories.availability_day_repository import AvailabilityDayRepository
from ...utils.bitset import get_slot_tag, is_tag_compatible, new_empty_tags
from ...utils.time_helpers import string_to_time
from ...utils.time_utils import time_to_minutes
from ..base import BaseService
from ..config_service import normalize_location_type

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from ...repositories.availability_repository import AvailabilityRepository
    from ...repositories.booking_repository import BookingRepository
    from ...schemas.booking import BookingCreate
    from ..conflict_checker import ConflictChecker


class BookingAvailabilityOpportunitiesMixin:
    if TYPE_CHECKING:
        db: Session
        repository: BookingRepository
        availability_repository: AvailabilityRepository
        conflict_checker: ConflictChecker

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
        start = BookingAvailabilityOpportunitiesMixin._time_to_minutes(
            booking.start_time, is_end_time=False
        )
        end = BookingAvailabilityOpportunitiesMixin._time_to_minutes(
            booking.end_time, is_end_time=True
        )
        if end <= start:
            end = 24 * 60
        return start, end

    def _resolve_local_booking_day(
        self,
        booking_data: BookingCreate,
        instructor_profile: InstructorProfile,
    ) -> date:
        """Return the instructor-local date for availability lookup."""
        return booking_data.booking_date

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
        """Find available time slots for booking based on instructor availability."""
        if not earliest_time:
            earliest_time = time(9, 0)
        if not latest_time:
            latest_time = time(21, 0)

        availability_windows = self._get_instructor_availability_windows(
            instructor_id, target_date, earliest_time, latest_time
        )
        existing_bookings = self._get_existing_bookings_for_date(
            instructor_id, target_date, earliest_time, latest_time
        )
        return self._calculate_booking_opportunities(
            availability_windows,
            existing_bookings,
            target_duration_minutes,
            earliest_time,
            latest_time,
            instructor_id,
            target_date,
        )

    def _get_instructor_availability_windows(
        self,
        instructor_id: str,
        target_date: date,
        earliest_time: time,
        latest_time: time,
    ) -> List[dict[str, Any]]:
        """Get instructor availability windows for a date from bitmap storage."""
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
        """Get existing bookings for the instructor on the date."""
        return self.repository.get_bookings_by_time_range(
            instructor_id=instructor_id,
            booking_date=target_date,
            start_time=earliest_time,
            end_time=latest_time,
        )

    def _calculate_booking_opportunities(
        self,
        availability_windows: List[dict[str, Any]],
        existing_bookings: List[Booking],
        target_duration_minutes: int,
        earliest_time: time,
        latest_time: time,
        instructor_id: str,
        target_date: date,
    ) -> List[Dict[str, Any]]:
        """Calculate available booking opportunities from windows and bookings."""
        opportunities: List[Dict[str, Any]] = []
        earliest_minutes = self._time_to_minutes(earliest_time, is_end_time=False)
        latest_minutes = self._time_to_minutes(latest_time, is_end_time=True)

        for window in availability_windows:
            slot_start = max(window["_start_minutes"], earliest_minutes)
            slot_end = min(window["_end_minutes"], latest_minutes)
            if slot_end <= slot_start:
                continue

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
        """Find booking opportunities within a single availability slot."""
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
        booking_date: date,
        start_time: time,
        end_time: time,
        location_type: Optional[str] = None,
        exclude_booking_id: Optional[str] = None,
    ) -> bool:
        """Check if student has a conflicting booking at the given time."""
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
