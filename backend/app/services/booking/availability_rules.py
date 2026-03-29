from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import TYPE_CHECKING, Optional

from ...core.exceptions import BusinessRuleException, ValidationException
from ...models.instructor import InstructorProfile
from ...models.service_catalog import InstructorService
from ...schemas.booking import BookingCreate
from ..config_service import is_instructor_travel_format, normalize_location_type

if TYPE_CHECKING:
    from ...repositories.filter_repository import FilterRepository
    from ..config_service import ConfigService


class BookingAvailabilityRulesMixin:
    if TYPE_CHECKING:
        filter_repository: FilterRepository
        config_service: ConfigService

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
        """Ensure travel-based bookings fall within the instructor's service area."""
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
        self,
        service: InstructorService,
        location_type: Optional[str],
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

        if hasattr(service, "format_for_booking_location_type"):
            try:
                service.format_for_booking_location_type(location_type)
            except BusinessRuleException:
                raise ValidationException(
                    "This instructor doesn't offer lessons at that location type",
                    code="LOCATION_TYPE_PRICING_NOT_FOUND",
                )
