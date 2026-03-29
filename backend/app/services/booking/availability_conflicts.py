from __future__ import annotations

from datetime import date, datetime, time, timedelta
from types import ModuleType
from typing import TYPE_CHECKING, Any, Dict, Optional, cast

from ...core.exceptions import BusinessRuleException, ValidationException
from ...models.instructor import InstructorProfile
from ...models.service_catalog import InstructorService
from ...models.user import User
from ...schemas.booking import BookingCreate
from ...utils.safe_cast import safe_float as _safe_float, safe_str as _safe_str
from ...utils.time_helpers import string_to_time
from ..config_service import normalize_location_type

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from ..conflict_checker import ConflictChecker


def _booking_service_module() -> ModuleType:
    from .. import booking_service as booking_service_module

    return booking_service_module


class BookingAvailabilityConflictsMixin:
    if TYPE_CHECKING:
        db: Session
        conflict_checker: ConflictChecker

        def _validate_location_capability(
            self,
            service: InstructorService,
            location_type: Optional[str],
        ) -> None:
            ...

        def _validate_service_area(
            self,
            booking_data: BookingCreate,
            instructor_id: str,
            service: Optional[InstructorService] = None,
        ) -> None:
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

        def _resolve_instructor_timezone(self, instructor_profile: InstructorProfile) -> str:
            ...

        def _get_advance_notice_minutes(self, location_type: Optional[str] = None) -> int:
            ...

        def _format_advance_notice(self, minutes: int) -> str:
            ...

        def _check_overnight_protection(
            self,
            booking_time_local: datetime,
            lesson_start_local: datetime,
            location_type: str,
            instructor_profile: InstructorProfile,
        ) -> None:
            ...

        def _build_conflict_details(
            self,
            booking_data: BookingCreate,
            student_id: Optional[str],
        ) -> dict[str, str]:
            ...

    def _build_availability_proximity_warnings(
        self,
        *,
        student_id: Optional[str],
        booking_date: date,
        start_time: time,
        end_time: time,
        normalized_location_type: str,
        exclude_booking_id: Optional[str],
        instructor_profile: InstructorProfile,
        location_address: Optional[str],
        location_place_id: Optional[str],
        location_lat: Optional[float],
        location_lng: Optional[float],
        existing_student_bookings: Optional[list[Any]],
    ) -> Optional[list[Dict[str, Any]]]:
        if not student_id:
            return None
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
        return cast(
            Optional[list[Dict[str, Any]]],
            self.conflict_checker.check_student_proximity_warnings(
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
            ),
        )

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
    ) -> tuple[str | None, str | None, float | None, float | None]:
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
            return str(parsed_time.strftime("%I:%M %p").lstrip("0"))
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

    def _check_conflicts_and_rules(
        self,
        booking_data: BookingCreate,
        service: InstructorService,
        instructor_profile: InstructorProfile,
        student: Optional[User] = None,
        exclude_booking_id: Optional[str] = None,
    ) -> None:
        """Check for time conflicts and apply business rules."""
        if booking_data.end_time is None:
            raise ValidationException("End time must be specified before conflict checks")
        normalized_location_type = normalize_location_type(booking_data.location_type)
        self._validate_booking_conflict_prerequisites(
            booking_data,
            service,
            normalized_location_type,
        )
        conflict_time_context = self._resolve_booking_conflict_time_context(
            booking_data,
            normalized_location_type,
            instructor_profile,
        )
        self._enforce_booking_advance_notice(
            booking_start_utc=conflict_time_context["booking_start_utc"],
            now_utc=conflict_time_context["now_utc"],
            min_advance_minutes=conflict_time_context["min_advance_minutes"],
        )
        self._enforce_booking_overnight_rules(
            booking_time_local=conflict_time_context["booking_time_local"],
            lesson_start_local=conflict_time_context["lesson_start_local"],
            normalized_location_type=normalized_location_type,
            instructor_profile=instructor_profile,
        )
        self._raise_instructor_conflict_if_needed(
            booking_data,
            student,
            normalized_location_type,
            instructor_profile,
            exclude_booking_id,
        )
        self._raise_student_conflict_if_needed(
            booking_data,
            student,
            exclude_booking_id,
        )

    def _validate_booking_conflict_prerequisites(
        self,
        booking_data: BookingCreate,
        service: InstructorService,
        normalized_location_type: str,
    ) -> None:
        self._validate_location_capability(service, normalized_location_type)
        self._validate_service_area(booking_data, booking_data.instructor_id, service)

    def _resolve_booking_conflict_time_context(
        self,
        booking_data: BookingCreate,
        normalized_location_type: str,
        instructor_profile: InstructorProfile,
    ) -> Dict[str, Any]:
        booking_service_module = _booking_service_module()
        lesson_tz = self._resolve_lesson_timezone(booking_data, instructor_profile)
        booking_start_utc, _ = self._resolve_booking_times_utc(
            booking_data.booking_date,
            booking_data.start_time,
            cast(time, booking_data.end_time),
            lesson_tz,
        )
        min_advance_minutes = self._get_advance_notice_minutes(normalized_location_type)
        now_utc = booking_service_module.datetime.now(booking_service_module.timezone.utc)
        instructor_tz = self._resolve_instructor_timezone(instructor_profile)
        return {
            "booking_start_utc": booking_start_utc,
            "now_utc": now_utc,
            "min_advance_minutes": min_advance_minutes,
            "booking_time_local": booking_service_module.TimezoneService.utc_to_local(
                now_utc, instructor_tz
            ),
            "lesson_start_local": booking_service_module.TimezoneService.utc_to_local(
                booking_start_utc, instructor_tz
            ),
        }

    def _enforce_booking_advance_notice(
        self,
        *,
        booking_start_utc: datetime,
        now_utc: datetime,
        min_advance_minutes: int,
    ) -> None:
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
            return
        minutes_until = (booking_start_utc - now_utc).total_seconds() / 60
        if minutes_until < min_advance_minutes:
            raise BusinessRuleException(
                "Bookings must be made at least "
                f"{self._format_advance_notice(min_advance_minutes)} in advance"
            )

    def _enforce_booking_overnight_rules(
        self,
        *,
        booking_time_local: datetime,
        lesson_start_local: datetime,
        normalized_location_type: str,
        instructor_profile: InstructorProfile,
    ) -> None:
        self._check_overnight_protection(
            booking_time_local,
            lesson_start_local,
            normalized_location_type,
            instructor_profile,
        )

    def _raise_instructor_conflict_if_needed(
        self,
        booking_data: BookingCreate,
        student: Optional[User],
        normalized_location_type: str,
        instructor_profile: InstructorProfile,
        exclude_booking_id: Optional[str],
    ) -> None:
        booking_service_module = _booking_service_module()
        existing_conflicts = self.conflict_checker.check_booking_conflicts(
            instructor_id=booking_data.instructor_id,
            check_date=booking_data.booking_date,
            start_time=booking_data.start_time,
            end_time=cast(time, booking_data.end_time),
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

    def _raise_student_conflict_if_needed(
        self,
        booking_data: BookingCreate,
        student: Optional[User],
        exclude_booking_id: Optional[str],
    ) -> None:
        if not student:
            return
        booking_service_module = _booking_service_module()
        student_conflicts = self.conflict_checker.check_student_booking_conflicts(
            student_id=student.id,
            check_date=booking_data.booking_date,
            start_time=booking_data.start_time,
            end_time=cast(time, booking_data.end_time),
            exclude_booking_id=exclude_booking_id,
        )
        if student_conflicts:
            conflict_details = self._build_conflict_details(booking_data, student.id)
            conflict_details["conflict_scope"] = "student"
            raise booking_service_module.BookingConflictException(
                message=booking_service_module.STUDENT_CONFLICT_MESSAGE,
                details=conflict_details,
            )
