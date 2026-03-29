from __future__ import annotations

from datetime import date, datetime, time, timedelta
from types import ModuleType
from typing import TYPE_CHECKING, Any, Dict, List, Optional, cast

from ...core.constants import BOOKING_START_STEP_MINUTES, MINUTES_PER_SLOT, SLOTS_PER_DAY
from ...core.exceptions import BusinessRuleException, ValidationException
from ...models.instructor import InstructorProfile
from ...models.service_catalog import InstructorService
from ...schemas.booking import BookingCreate
from ...utils.time_utils import time_to_minutes
from ..base import BaseService
from ..config_service import normalize_location_type

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from ...repositories.booking_repository import BookingRepository
    from ...repositories.conflict_checker_repository import ConflictCheckerRepository
    from ..config_service import ConfigService
    from ..conflict_checker import ConflictChecker


def _booking_service_module() -> ModuleType:
    from .. import booking_service as booking_service_module

    return booking_service_module


class BookingAvailabilityMixin:
    if TYPE_CHECKING:
        db: Session
        repository: BookingRepository
        conflict_checker_repository: ConflictCheckerRepository
        conflict_checker: ConflictChecker
        config_service: ConfigService

        def _resolve_instructor_timezone(self, instructor_profile: InstructorProfile) -> str:
            ...

        def _resolve_booking_times_utc(
            self,
            booking_date: date,
            start_time: time,
            end_time: time,
            lesson_tz: str,
        ) -> tuple[datetime, datetime]:
            ...

        def _validate_location_capability(
            self,
            service: InstructorService,
            location_type: Optional[str],
        ) -> None:
            ...

        def _validate_selected_duration_for_service(
            self,
            *,
            service: InstructorService,
            booking_date: date,
            start_time: time,
            end_time: time,
            selected_duration: Optional[int],
        ) -> None:
            ...

        def _validate_service_area_for_availability_check(
            self,
            *,
            instructor_id: str,
            service: InstructorService,
            location_type: Optional[str],
            location_lat: Optional[float],
            location_lng: Optional[float],
        ) -> None:
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
            existing_student_bookings: Optional[List[Any]],
        ) -> Optional[List[Dict[str, Any]]]:
            ...

        def _get_bitmap_availability_error(
            self,
            instructor_id: str,
            day: date,
            start_index: int,
            end_index: int,
            *,
            location_type: str | None,
        ) -> str | None:
            ...

        def _resolve_local_booking_day(
            self,
            booking_data: BookingCreate,
            instructor_profile: InstructorProfile,
        ) -> date:
            ...

        def _build_student_conflict_reason(
            self,
            conflicting_booking: Any,
            booking_date: date,
        ) -> str:
            ...

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
        """Check whether a requested lesson window is available."""
        start_minutes = time_to_minutes(start_time)
        resolved_service_id = service_id or instructor_service_id
        normalized_location_type = normalize_location_type(location_type)
        exclude_id = str(exclude_booking_id) if exclude_booking_id is not None else None
        shape_error = self._validate_availability_request_shape(start_minutes, resolved_service_id)
        if shape_error:
            return shape_error
        availability_context = self._load_availability_context(
            resolved_service_id=cast(str, resolved_service_id), instructor_id=instructor_id
        )
        if availability_context.get("error"):
            return cast(Dict[str, Any], availability_context["error"])
        service = cast(InstructorService, availability_context["service"])
        instructor_profile = cast(InstructorProfile, availability_context["instructor_profile"])
        business_rule_error = self._validate_availability_business_rules(
            service=service,
            instructor_id=instructor_id,
            booking_date=booking_date,
            start_time=start_time,
            end_time=end_time,
            selected_duration=selected_duration,
            normalized_location_type=normalized_location_type,
            location_lat=location_lat,
            location_lng=location_lng,
        )
        if business_rule_error:
            return business_rule_error
        timing_error = self._enforce_availability_notice_and_overnight_rules(
            booking_date=booking_date,
            start_time=start_time,
            end_time=end_time,
            normalized_location_type=normalized_location_type,
            instructor_profile=instructor_profile,
        )
        if timing_error:
            return timing_error
        conflict_ctx = self._check_availability_conflicts(
            instructor_id=instructor_id,
            booking_date=booking_date,
            start_time=start_time,
            end_time=end_time,
            normalized_location_type=normalized_location_type,
            exclude_booking_id=exclude_booking_id,
            student_id=student_id,
            exclude_id=exclude_id,
            instructor_profile=instructor_profile,
        )
        if conflict_ctx.get("error"):
            return cast(Dict[str, Any], conflict_ctx["error"])
        bitmap_error = self._validate_availability_bitmap_range(
            instructor_id=instructor_id,
            booking_date=booking_date,
            start_minutes=start_minutes,
            end_time=end_time,
            normalized_location_type=normalized_location_type,
        )
        if bitmap_error:
            return bitmap_error
        proximity_warnings = self._build_availability_proximity_warnings(
            student_id=student_id,
            booking_date=booking_date,
            start_time=start_time,
            end_time=end_time,
            normalized_location_type=normalized_location_type,
            exclude_booking_id=exclude_booking_id,
            instructor_profile=instructor_profile,
            location_address=location_address,
            location_place_id=location_place_id,
            location_lat=location_lat,
            location_lng=location_lng,
            existing_student_bookings=cast(
                Optional[List[Any]], conflict_ctx["existing_student_bookings"]
            ),
        )
        return self._build_availability_success_response(
            booking_date=booking_date,
            start_time=start_time,
            end_time=end_time,
            instructor_id=instructor_id,
            proximity_warnings=proximity_warnings,
        )

    def _validate_availability_request_shape(
        self,
        start_minutes: int,
        resolved_service_id: Optional[str],
    ) -> Dict[str, Any] | None:
        if start_minutes % BOOKING_START_STEP_MINUTES != 0:
            return {
                "available": False,
                "reason": f"Start time must be on a {BOOKING_START_STEP_MINUTES}-minute boundary",
            }
        if not resolved_service_id:
            return {"available": False, "reason": "Service not found or no longer available"}
        return None

    def _load_availability_context(
        self,
        *,
        resolved_service_id: str,
        instructor_id: str,
    ) -> Dict[str, Any]:
        service = self.conflict_checker_repository.get_active_service(resolved_service_id)
        if not service:
            return {
                "error": {"available": False, "reason": "Service not found or no longer available"}
            }
        instructor_profile = self.conflict_checker_repository.get_instructor_profile(instructor_id)
        if instructor_profile is None:
            return {"error": {"available": False, "reason": "Instructor profile not found"}}
        return {"service": service, "instructor_profile": instructor_profile}

    def _validate_availability_business_rules(
        self,
        *,
        service: InstructorService,
        instructor_id: str,
        booking_date: date,
        start_time: time,
        end_time: time,
        selected_duration: Optional[int],
        normalized_location_type: str,
        location_lat: Optional[float],
        location_lng: Optional[float],
    ) -> Dict[str, Any] | None:
        try:
            self._validate_location_capability(service, normalized_location_type)
            self._validate_selected_duration_for_service(
                service=service,
                booking_date=booking_date,
                start_time=start_time,
                end_time=end_time,
                selected_duration=selected_duration,
            )
            self._validate_service_area_for_availability_check(
                instructor_id=instructor_id,
                service=service,
                location_type=normalized_location_type,
                location_lat=location_lat,
                location_lng=location_lng,
            )
        except ValidationException as exc:
            return {"available": False, "reason": str(exc)}
        return None

    def _enforce_availability_notice_and_overnight_rules(
        self,
        *,
        booking_date: date,
        start_time: time,
        end_time: time,
        normalized_location_type: str,
        instructor_profile: InstructorProfile,
    ) -> Dict[str, Any] | None:
        booking_service_module = _booking_service_module()
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

        advance_error = self._availability_advance_notice_error(
            booking_start_utc=booking_start_utc,
            now_utc=now_utc,
            min_advance_minutes=min_advance_minutes,
        )
        if advance_error:
            return advance_error

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
        return None

    def _availability_advance_notice_error(
        self,
        *,
        booking_start_utc: datetime,
        now_utc: datetime,
        min_advance_minutes: int,
    ) -> Dict[str, Any] | None:
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
                        f"Must book at least {self._format_advance_notice(min_advance_minutes)} in advance"
                    ),
                    "min_advance_minutes": min_advance_minutes,
                }
            return None

        minutes_until = (booking_start_utc - now_utc).total_seconds() / 60
        if minutes_until < min_advance_minutes:
            return {
                "available": False,
                "reason": (
                    f"Must book at least {self._format_advance_notice(min_advance_minutes)} in advance"
                ),
                "min_advance_minutes": min_advance_minutes,
            }
        return None

    def _check_availability_conflicts(
        self,
        *,
        instructor_id: str,
        booking_date: date,
        start_time: time,
        end_time: time,
        normalized_location_type: str,
        exclude_booking_id: Optional[str],
        student_id: Optional[str],
        exclude_id: Optional[str],
        instructor_profile: InstructorProfile,
    ) -> Dict[str, Any]:
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
            return {
                "error": {
                    "available": False,
                    "reason": "Time slot has conflicts with existing bookings",
                },
                "existing_student_bookings": None,
            }

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
                    "error": {
                        "available": False,
                        "reason": self._build_student_conflict_reason(
                            student_conflicts[0],
                            booking_date,
                        ),
                    },
                    "existing_student_bookings": existing_student_bookings,
                }
        return {"error": None, "existing_student_bookings": existing_student_bookings}

    def _validate_availability_bitmap_range(
        self,
        *,
        instructor_id: str,
        booking_date: date,
        start_minutes: int,
        end_time: time,
        normalized_location_type: str,
    ) -> Dict[str, Any] | None:
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
            return {"available": False, "reason": error_message}
        return None

    @staticmethod
    def _build_availability_success_response(
        *,
        booking_date: date,
        start_time: time,
        end_time: time,
        instructor_id: str,
        proximity_warnings: Optional[List[Dict[str, Any]]],
    ) -> Dict[str, Any]:
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
