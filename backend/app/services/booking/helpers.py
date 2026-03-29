from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
import hashlib
import logging
import os
from types import ModuleType
from typing import TYPE_CHECKING, Any, Optional, Tuple, cast

from sqlalchemy.exc import IntegrityError, OperationalError

from ...core.constants import MIN_SESSION_DURATION
from ...core.enums import RoleName
from ...core.exceptions import (
    BusinessRuleException,
    RepositoryException,
    ValidationException,
)
from ...models.booking import Booking
from ...models.instructor import InstructorProfile
from ...models.user import User
from ...schemas.booking import BookingCreate

if TYPE_CHECKING:
    from ...repositories.booking_repository import BookingRepository

logger = logging.getLogger(__name__)


def _is_test_or_ci() -> bool:
    return bool(os.getenv("PYTEST_CURRENT_TEST") or os.getenv("CI"))


def _booking_service_module() -> ModuleType:
    from .. import booking_service as booking_service_module

    return booking_service_module


class BookingHelpersMixin:
    if TYPE_CHECKING:
        repository: BookingRepository

    @staticmethod
    def _user_has_role(user: User, role: RoleName) -> bool:
        roles = cast(list[Any], getattr(user, "roles", []) or [])
        return any(cast(str, getattr(role_obj, "name", "")) == role for role_obj in roles)

    def _calculate_and_validate_end_time(
        self,
        booking_date: date,
        start_time: time,
        selected_duration: int,
    ) -> time:
        """
        Calculate the booking end time and enforce the half-open [start, end) rule.

        Allows bookings that end exactly at midnight (treated as 24:00) but rejects
        any ranges that otherwise wrap past the booking date.
        """
        start_datetime = datetime.combine(  # tz-pattern-ok: duration math only
            booking_date, start_time, tzinfo=timezone.utc
        )
        end_datetime = start_datetime + timedelta(minutes=selected_duration)
        end_time = end_datetime.time()
        midnight = time(0, 0)

        if end_datetime.date() == booking_date:
            if end_time <= start_time:
                raise ValidationException("Booking end time must be after the start time")
            return end_time

        next_day = booking_date + timedelta(days=1)
        if end_datetime.date() == next_day and end_time == midnight and start_time != midnight:
            return end_time

        raise ValidationException(
            "Bookings cannot span multiple days (end time at midnight is allowed)."
        )

    @staticmethod
    def _is_online_lesson(booking_data: BookingCreate) -> bool:
        """Return True when the lesson is remote/online."""
        location_type = getattr(booking_data, "location_type", None)
        return location_type == "online"

    def _resolve_instructor_timezone(self, instructor_profile: InstructorProfile) -> str:
        """Resolve instructor timezone with a safe default."""
        instructor_user = getattr(instructor_profile, "user", None)
        instructor_tz = getattr(instructor_user, "timezone", None)
        booking_service_module = _booking_service_module()
        default_tz: str = booking_service_module.TimezoneService.DEFAULT_TIMEZONE
        if isinstance(instructor_tz, str) and instructor_tz:
            return instructor_tz
        return default_tz

    @staticmethod
    def _resolve_student_timezone(student: Optional[User]) -> str:
        """Resolve student timezone with a safe default."""
        student_tz = getattr(student, "timezone", None) if student else None
        booking_service_module = _booking_service_module()
        default_tz: str = booking_service_module.TimezoneService.DEFAULT_TIMEZONE
        if isinstance(student_tz, str) and student_tz:
            return student_tz
        return default_tz

    def _resolve_lesson_timezone(
        self,
        booking_data: BookingCreate,
        instructor_profile: InstructorProfile,
    ) -> str:
        booking_service_module = _booking_service_module()
        instructor_tz = self._resolve_instructor_timezone(instructor_profile)
        is_online = self._is_online_lesson(booking_data)
        lesson_tz: str = booking_service_module.TimezoneService.get_lesson_timezone(
            instructor_tz, is_online
        )
        return lesson_tz or booking_service_module.TimezoneService.DEFAULT_TIMEZONE

    @staticmethod
    def _resolve_end_date(booking_date: date, start_time: time, end_time: time) -> date:
        """Resolve the end date for a booking, handling midnight rollover."""
        midnight = time(0, 0)
        if end_time == midnight and start_time != midnight:
            return booking_date + timedelta(days=1)
        return booking_date

    def _resolve_booking_times_utc(
        self,
        booking_date: date,
        start_time: time,
        end_time: time,
        lesson_tz: str,
    ) -> Tuple[datetime, datetime]:
        """Convert local booking times to UTC, raising on invalid times."""
        booking_service_module = _booking_service_module()
        end_date = self._resolve_end_date(booking_date, start_time, end_time)
        try:
            start_utc = booking_service_module.TimezoneService.local_to_utc(
                booking_date, start_time, lesson_tz
            )
            end_utc = booking_service_module.TimezoneService.local_to_utc(
                end_date, end_time, lesson_tz
            )
        except ValueError as exc:
            raise BusinessRuleException(str(exc)) from exc
        return start_utc, end_utc

    def _get_booking_start_utc(self, booking: Booking) -> datetime:
        """Get booking start time in UTC."""
        if booking.booking_start_utc is None:
            raise ValueError(f"Booking {booking.id} missing booking_start_utc")
        return cast(datetime, booking.booking_start_utc)

    def _get_booking_end_utc(self, booking: Booking) -> datetime:
        """Get booking end time in UTC."""
        if booking.booking_end_utc is None:
            raise ValueError(f"Booking {booking.id} missing booking_end_utc")
        return cast(datetime, booking.booking_end_utc)

    def _build_conflict_details(
        self, booking_data: BookingCreate, student_id: Optional[str]
    ) -> dict[str, str]:
        """Construct structured conflict metadata for error responses."""
        end_time_value = booking_data.end_time
        return {
            "instructor_id": booking_data.instructor_id,
            "student_id": student_id or "",
            "booking_date": booking_data.booking_date.isoformat(),
            "start_time": booking_data.start_time.isoformat(),
            "end_time": end_time_value.isoformat() if end_time_value else "",
        }

    def _resolve_integrity_conflict_message(
        self, integrity_error: IntegrityError
    ) -> Tuple[str, Optional[str]]:
        """
        Determine the appropriate conflict message and scope from a database IntegrityError.
        """
        booking_service_module = _booking_service_module()
        constraint_name: str = ""
        orig = getattr(integrity_error, "orig", None)
        diag = getattr(orig, "diag", None)

        if diag is not None:
            constraint_name = getattr(diag, "constraint_name", "") or ""

        if not constraint_name and orig is not None:
            text = str(orig)
            if "bookings_no_overlap_per_instructor" in text:
                constraint_name = "bookings_no_overlap_per_instructor"
            elif "bookings_no_overlap_per_student" in text:
                constraint_name = "bookings_no_overlap_per_student"

        if constraint_name == "bookings_no_overlap_per_instructor":
            return booking_service_module.INSTRUCTOR_CONFLICT_MESSAGE, "instructor"
        if constraint_name == "bookings_no_overlap_per_student":
            return booking_service_module.STUDENT_CONFLICT_MESSAGE, "student"

        return booking_service_module.GENERIC_CONFLICT_MESSAGE, None

    def _raise_conflict_from_repo_error(
        self,
        exc: RepositoryException,
        booking_data: BookingCreate,
        student_id: Optional[str],
    ) -> None:
        """
        Translate repository-level deadlocks into booking conflicts so callers
        receive a deterministic error instead of a generic RepositoryException.
        """
        booking_service_module = _booking_service_module()
        message = str(exc).lower()
        if "deadlock detected" in message or "exclusion constraint" in message:
            conflict_details = self._build_conflict_details(booking_data, student_id)
            raise booking_service_module.BookingConflictException(
                message=booking_service_module.GENERIC_CONFLICT_MESSAGE,
                details=conflict_details,
            ) from exc
        raise exc

    @staticmethod
    def _validate_min_session_duration_floor(selected_duration: int) -> None:
        """Defense-in-depth minimum duration check for booking flows."""
        if selected_duration < MIN_SESSION_DURATION:
            raise ValidationException(f"Duration must be at least {MIN_SESSION_DURATION} minutes")

    @staticmethod
    def _is_deadlock_error(exc: OperationalError) -> bool:
        orig = getattr(exc, "orig", None)
        pgcode = getattr(orig, "pgcode", None) or getattr(orig, "sqlstate", None)
        if pgcode == "40P01":
            return True
        message = str(exc).lower()
        return "deadlock detected" in message

    @staticmethod
    def _booking_create_lock_key(instructor_id: str, booking_date: date) -> int:
        payload = f"{instructor_id}:{booking_date.isoformat()}".encode("utf-8")
        digest = hashlib.sha256(payload).digest()
        return int.from_bytes(digest[:8], byteorder="big", signed=True)

    def _acquire_booking_create_advisory_lock(self, instructor_id: str, booking_date: date) -> None:
        acquire_lock = getattr(self.repository, "acquire_transaction_advisory_lock", None)
        if not callable(acquire_lock):
            return

        acquire_lock(
            self._booking_create_lock_key(
                instructor_id,
                booking_date,
            )
        )

    @staticmethod
    def _format_user_display_name(user: Optional[User]) -> str:
        if not user:
            return "Someone"
        first = (getattr(user, "first_name", "") or "").strip()
        last = (getattr(user, "last_name", "") or "").strip()
        if first and last:
            return f"{first} {last[0]}."
        return first or "Someone"

    @staticmethod
    def _format_booking_date(booking: Booking) -> str:
        booking_date = getattr(booking, "booking_date", None)
        if isinstance(booking_date, date):
            return booking_date.strftime("%B %d").replace(" 0", " ")
        return str(booking_date or "")

    @staticmethod
    def _format_booking_time(booking: Booking) -> str:
        start_time = getattr(booking, "start_time", None)
        if isinstance(start_time, time):
            return start_time.strftime("%I:%M %p").lstrip("0")
        if start_time:
            return str(start_time)
        return ""

    @staticmethod
    def _resolve_service_name(booking: Booking) -> str:
        name = getattr(booking, "service_name", None)
        if isinstance(name, str) and name.strip():
            return name.strip()
        service = getattr(booking, "instructor_service", None)
        service_name = getattr(service, "name", None)
        if isinstance(service_name, str) and service_name.strip():
            return service_name.strip()
        return "Lesson"
