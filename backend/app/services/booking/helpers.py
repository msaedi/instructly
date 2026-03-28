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
from ...models.audit_log import AuditLog
from ...models.booking import Booking, BookingStatus
from ...models.instructor import InstructorProfile
from ...models.user import User
from ...schemas.booking import BookingCreate
from ..audit_redaction import redact
from ..base import BaseService

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from ...models.booking_transfer import BookingTransfer
    from ...repositories.audit_repository import AuditRepository
    from ...repositories.booking_repository import BookingRepository
    from ...repositories.event_outbox_repository import EventOutboxRepository
    from ..cache_service import CacheServiceSyncAdapter
    from ..pricing_service import PricingService

logger = logging.getLogger(__name__)

AUDIT_ENABLED = os.getenv("AUDIT_ENABLED", "true").lower() in {"1", "true", "yes"}


def _is_test_or_ci() -> bool:
    return bool(os.getenv("PYTEST_CURRENT_TEST") or os.getenv("CI"))


def _booking_service_module() -> ModuleType:
    from .. import booking_service as booking_service_module

    return booking_service_module


class BookingHelpersMixin:
    if TYPE_CHECKING:
        db: Session
        pricing_service: PricingService
        repository: BookingRepository
        event_outbox_repository: EventOutboxRepository
        audit_repository: AuditRepository
        cache_service: Optional[CacheServiceSyncAdapter]

        def _resolve_actor_payload(
            self,
            actor: Any | None,
            default_role: str = "system",
        ) -> dict[str, Any]:
            ...

    def _maybe_refresh_instructor_tier(self, instructor_user_id: str, booking_id: str) -> None:
        if not instructor_user_id:
            return

        try:
            self.pricing_service.evaluate_and_persist_instructor_tier(
                instructor_user_id=str(instructor_user_id)
            )
        except Exception as exc:
            logger.error(
                "Failed refreshing instructor tier after booking completion %s: %s",
                booking_id,
                exc,
                exc_info=True,
            )

    def _get_transfer_record(self, booking_id: str) -> BookingTransfer | None:
        """Return booking transfer satellite row when present."""
        return self.repository.get_transfer_by_booking_id(booking_id)

    def _ensure_transfer_record(self, booking_id: str) -> BookingTransfer:
        """Get or create booking transfer satellite row."""
        return self.repository.ensure_transfer(booking_id)

    def _booking_event_identity(self, booking: Booking, event_type: str) -> tuple[str, str]:
        """Return idempotency key and version for a booking domain event."""
        booking_service_module = _booking_service_module()
        timestamp = booking.created_at or booking_service_module.datetime.now(
            booking_service_module.timezone.utc
        )
        if event_type == "booking.cancelled" and booking.cancelled_at:
            timestamp = booking.cancelled_at
        elif event_type == "booking.completed" and booking.completed_at:
            timestamp = booking.completed_at
        elif booking.updated_at:
            timestamp = booking.updated_at

        ts = timestamp.astimezone(booking_service_module.timezone.utc)
        version = ts.isoformat()
        key = f"booking:{booking.id}:{event_type}:{version}"
        return key, version

    def _serialize_booking_event_payload(
        self, booking: Booking, event_type: str, version: str
    ) -> dict[str, Any]:
        """Build JSON-safe payload for outbox events."""
        return {
            "booking_id": booking.id,
            "event_type": event_type,
            "version": version,
            "status": booking.status.value
            if isinstance(booking.status, BookingStatus)
            else str(booking.status),
            "student_id": booking.student_id,
            "instructor_id": booking.instructor_id,
            "booking_date": booking.booking_date.isoformat() if booking.booking_date else None,
            "start_time": booking.start_time.isoformat() if booking.start_time else None,
            "end_time": booking.end_time.isoformat() if booking.end_time else None,
            "total_price": str(booking.total_price),
            "created_at": booking.created_at.isoformat() if booking.created_at else None,
            "updated_at": booking.updated_at.isoformat() if booking.updated_at else None,
            "cancelled_at": booking.cancelled_at.isoformat() if booking.cancelled_at else None,
            "completed_at": booking.completed_at.isoformat() if booking.completed_at else None,
        }

    def _enqueue_booking_outbox_event(self, booking: Booking, event_type: str) -> None:
        """Persist an outbox entry for the given booking event inside the current transaction."""
        self.repository.flush()  # Ensure timestamps are populated before computing identity
        idempotency_key, version = self._booking_event_identity(booking, event_type)
        payload = self._serialize_booking_event_payload(booking, event_type, version)
        self.event_outbox_repository.enqueue(
            event_type=event_type,
            aggregate_id=booking.id,
            payload=payload,
            idempotency_key=idempotency_key,
        )

    @staticmethod
    def _user_has_role(user: User, role: RoleName) -> bool:
        roles = cast(list[Any], getattr(user, "roles", []) or [])
        return any(cast(str, getattr(role_obj, "name", "")) == role for role_obj in roles)

    def _snapshot_booking(self, booking: Booking) -> dict[str, Any]:
        """Return a redacted snapshot of a booking suitable for audit logging."""
        data = booking.to_dict()
        status_value = data.get("status")
        if isinstance(status_value, BookingStatus):
            data["status"] = status_value.value
        return redact(data) or {}

    def _write_booking_audit(
        self,
        booking: Booking,
        action: str,
        *,
        actor: Any | None,
        before: dict[str, Any] | None,
        after: dict[str, Any] | None,
        default_role: str = "system",
    ) -> None:
        """Persist an audit row capturing the change."""
        actor_payload = self._resolve_actor_payload(actor, default_role=default_role)
        audit_entry = AuditLog.from_change(
            entity_type="booking",
            entity_id=booking.id,
            action=action,
            actor=actor_payload,
            before=before,
            after=after,
        )
        booking_service_module = _booking_service_module()
        if booking_service_module.AUDIT_ENABLED:
            self.audit_repository.write(audit_entry)
            try:
                normalized_action = action.lower()
                if "cancel" in normalized_action:
                    audit_action = "booking.cancel"
                elif "complete" in normalized_action:
                    audit_action = "booking.complete"
                elif normalized_action == "create":
                    audit_action = "booking.create"
                else:
                    audit_action = f"booking.{action}"
                    if normalized_action == "status_change" and isinstance(after, dict):
                        status_value = after.get("status")
                        if status_value:
                            normalized_status = str(status_value).lower()
                            if normalized_status in {"completed", "complete"}:
                                audit_action = "booking.complete"
                            elif normalized_status in {"cancelled", "canceled"}:
                                audit_action = "booking.cancel"

                booking_service_module.AuditService(self.db).log_changes(
                    action=audit_action,
                    resource_type="booking",
                    resource_id=booking.id,
                    old_values=before,
                    new_values=after,
                    actor=actor if isinstance(actor, User) else None,
                    actor_type="user" if actor is not None else "system",
                    actor_id=actor_payload.get("id") if actor is not None else None,
                    description=f"Booking {action}",
                    metadata={"legacy_action": action},
                )
            except Exception:
                # Side-effect only — does not affect booking state.
                logger.debug(
                    "Failed to write booking audit trail for booking %s",
                    booking.id,
                    exc_info=True,
                )

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

    @BaseService.measure_operation("invalidate_booking_cache")
    def invalidate_booking_cache(self, booking_or_id: Booking | str) -> None:
        """Invalidate cached booking data for a specific booking."""
        target_booking: Optional[Booking]
        if isinstance(booking_or_id, Booking):
            target_booking = booking_or_id
        else:
            target_booking = self.repository.get_by_id(booking_or_id)

        if not target_booking:
            return

        self._invalidate_booking_caches(target_booking)

    def _invalidate_booking_caches(self, booking: Booking) -> None:
        """
        Invalidate caches affected by booking changes using enhanced cache service.

        Note: Ghost keys removed in v123 cleanup. Only active cache keys are invalidated:
        - Availability caches via invalidate_instructor_availability()
        - booking_stats:instructor (active - used in get_instructor_booking_stats)
        - BookingRepository cached methods via delete_pattern
        """
        booking_service_module = _booking_service_module()
        if self.cache_service:
            try:
                # Invalidate all availability caches for the instructor and specific date
                self.cache_service.invalidate_instructor_availability(
                    booking.instructor_id, [booking.booking_date]
                )
                booking_service_module.invalidate_on_availability_change(str(booking.instructor_id))
                # Invalidate booking statistics cache for the instructor (actively used)
                stats_cache_key = f"booking_stats:instructor:{booking.instructor_id}"
                self.cache_service.delete(stats_cache_key)
                logger.debug(
                    "Invalidated availability, search, and stats caches for instructor %s",
                    booking.instructor_id,
                )
            except Exception as cache_error:
                logger.warning("Failed to invalidate caches: %s", cache_error)

            # Invalidate BookingRepository cached methods
            # The cache keys use hashed kwargs, so we need to invalidate ALL cached queries
            try:
                self.cache_service.delete_pattern("booking:get_student_bookings:*")
                self.cache_service.delete_pattern("booking:get_instructor_bookings:*")
                logger.debug(
                    "Invalidated BookingRepository caches after booking %s change",
                    booking.id,
                )
            except Exception as e:
                logger.warning("Failed to invalidate BookingRepository caches: %s", e)
