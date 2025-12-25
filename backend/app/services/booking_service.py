# backend/app/services/booking_service.py
"""
Booking Service for InstaInstru Platform

Handles all booking-related business logic including:
- Creating instant bookings using time ranges
- Finding booking opportunities
- Validating booking constraints
- Managing booking lifecycle
- Coordinating with other services

UPDATED IN v65: Added performance metrics and refactored long methods.
All methods now under 50 lines with comprehensive observability! ⚡
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
import logging
import os
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, cast

from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session
import stripe

from ..core.bgc_policy import is_verified, must_be_verified_for_public
from ..core.enums import RoleName
from ..core.exceptions import (
    BookingConflictException,
    BusinessRuleException,
    NotFoundException,
    RepositoryException,
    ValidationException,
)
from ..events import BookingCancelled, BookingCreated, BookingReminder, EventPublisher
from ..models.audit_log import AuditLog
from ..models.booking import Booking, BookingStatus
from ..models.instructor import InstructorProfile
from ..models.service_catalog import InstructorService
from ..models.user import User
from ..repositories.availability_day_repository import AvailabilityDayRepository
from ..repositories.factory import RepositoryFactory
from ..repositories.job_repository import JobRepository
from ..schemas.booking import BookingCreate, BookingUpdate
from .audit_redaction import redact
from .base import BaseService
from .cache_service import CacheService, CacheServiceSyncAdapter
from .config_service import ConfigService
from .notification_service import NotificationService
from .pricing_service import PricingService
from .student_credit_service import StudentCreditService
from .system_message_service import SystemMessageService
from .timezone_service import TimezoneService

if TYPE_CHECKING:
    # AvailabilitySlot removed - bitmap-only storage now
    from ..repositories.audit_repository import AuditRepository
    from ..repositories.availability_repository import AvailabilityRepository
    from ..repositories.booking_repository import BookingRepository
    from ..repositories.conflict_checker_repository import ConflictCheckerRepository
    from ..repositories.event_outbox_repository import EventOutboxRepository
    from ..schemas.booking import PaymentSummary

logger = logging.getLogger(__name__)

AUDIT_ENABLED = os.getenv("AUDIT_ENABLED", "true").lower() in {"1", "true", "yes"}

INSTRUCTOR_CONFLICT_MESSAGE = "Instructor already has a booking that overlaps this time"
STUDENT_CONFLICT_MESSAGE = "Student already has a booking that overlaps this time"
GENERIC_CONFLICT_MESSAGE = "This time slot conflicts with an existing booking"


class BookingService(BaseService):
    """
    Service layer for booking operations.

    Centralizes all booking business logic and coordinates
    with other services.
    """

    # Attribute type annotations to help static typing
    repository: "BookingRepository"
    availability_repository: "AvailabilityRepository"
    conflict_checker_repository: "ConflictCheckerRepository"
    cache_service: Optional[CacheServiceSyncAdapter]
    notification_service: NotificationService
    event_outbox_repository: "EventOutboxRepository"
    audit_repository: "AuditRepository"
    event_publisher: EventPublisher

    @staticmethod
    def _is_deadlock_error(exc: OperationalError) -> bool:
        orig = getattr(exc, "orig", None)
        pgcode = getattr(orig, "pgcode", None) or getattr(orig, "sqlstate", None)
        if pgcode == "40P01":
            return True
        message = str(exc).lower()
        return "deadlock detected" in message

    def __init__(
        self,
        db: Session,
        notification_service: Optional[NotificationService] = None,
        event_publisher: Optional[EventPublisher] = None,
        repository: Optional["BookingRepository"] = None,
        conflict_checker_repository: Optional["ConflictCheckerRepository"] = None,
        cache_service: Optional[CacheService | CacheServiceSyncAdapter] = None,
        system_message_service: Optional[SystemMessageService] = None,
    ):
        """
        Initialize booking service.

        Args:
            db: Database session
            notification_service: Optional notification service instance
            event_publisher: Optional event publisher for async side effects
            repository: Optional BookingRepository instance
            conflict_checker_repository: Optional ConflictCheckerRepository instance
            cache_service: Optional cache service for invalidation
            system_message_service: Optional system message service for conversation messages
        """
        cache_impl = cache_service
        cache_adapter: Optional[CacheServiceSyncAdapter] = None
        if isinstance(cache_impl, CacheServiceSyncAdapter):
            cache_adapter = cache_impl
        elif isinstance(cache_impl, CacheService):
            cache_adapter = CacheServiceSyncAdapter(cache_impl)
        super().__init__(db, cache=cache_adapter)
        self.notification_service = notification_service or NotificationService(db)
        self.event_publisher = event_publisher or EventPublisher(JobRepository(db))
        self.system_message_service = system_message_service or SystemMessageService(db)
        # Pass cache_service to BookingRepository for caching support
        if repository:
            self.repository = repository
        else:
            from ..repositories.booking_repository import BookingRepository

            self.repository = BookingRepository(db, cache_service=cache_adapter)
        self.availability_repository = RepositoryFactory.create_availability_repository(db)
        self.conflict_checker_repository = (
            conflict_checker_repository or RepositoryFactory.create_conflict_checker_repository(db)
        )
        self.cache_service = cache_adapter
        self.service_area_repository = RepositoryFactory.create_instructor_service_area_repository(
            db
        )
        self.event_outbox_repository = RepositoryFactory.create_event_outbox_repository(db)
        self.audit_repository = RepositoryFactory.create_audit_repository(db)

    def _booking_event_identity(self, booking: Booking, event_type: str) -> tuple[str, str]:
        """Return idempotency key and version for a booking domain event."""
        timestamp: datetime | None = None
        if event_type == "booking.cancelled" and booking.cancelled_at:
            timestamp = booking.cancelled_at
        elif event_type == "booking.completed" and booking.completed_at:
            timestamp = booking.completed_at
        elif booking.updated_at:
            timestamp = booking.updated_at
        else:
            timestamp = booking.created_at or datetime.now(timezone.utc)

        assert timestamp is not None, "timestamp should always be computed for booking event"
        ts = timestamp.astimezone(timezone.utc)
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
    def _time_to_minutes(value: time) -> int:
        """Return minutes since midnight for a time value."""
        return value.hour * 60 + value.minute

    @staticmethod
    def _minutes_to_time(value: int) -> time:
        """Convert minutes since midnight to a time (wrap 24:00 as 00:00)."""
        if value >= 24 * 60:
            return time(0, 0)
        return time(value // 60, value % 60)

    @staticmethod
    def _bitmap_str_to_minutes(value: str) -> int:
        """Convert bitmap strings (e.g., '24:00:00') into minute offsets."""
        parts = value.split(":")
        hour = int(parts[0]) if parts and parts[0] else 0
        minute = int(parts[1]) if len(parts) > 1 and parts[1] else 0
        if hour >= 24:
            return 24 * 60
        return hour * 60 + minute

    @staticmethod
    def _booking_window_to_minutes(booking: Booking) -> tuple[int, int]:
        """Convert a booking's start/end times into minute offsets."""
        if not booking.start_time or not booking.end_time:
            return 0, 0
        start = BookingService._time_to_minutes(booking.start_time)
        end = BookingService._time_to_minutes(booking.end_time)
        if end <= start:
            end = 24 * 60
        return start, end

    def _resolve_actor_payload(
        self, actor: Any | None, default_role: str = "system"
    ) -> dict[str, Any]:
        """Extract actor metadata (id/role) from user-like objects."""
        if actor is None:
            return {"role": default_role}

        if isinstance(actor, dict):
            actor_id = actor.get("id") or actor.get("actor_id") or actor.get("user_id")
            raw_role = actor.get("role") or actor.get("actor_role") or actor.get("role_name")
            resolved_role = str(raw_role) if raw_role is not None else default_role
            return {"id": actor_id, "role": resolved_role}

        actor_id = getattr(actor, "id", None)
        role_value: Any = getattr(actor, "role", None) or getattr(actor, "role_name", None)

        if role_value is None:
            roles = getattr(actor, "roles", None)
            if isinstance(roles, (list, tuple)):
                for role_obj in roles:
                    candidate = getattr(role_obj, "name", None)
                    if candidate:
                        role_value = candidate
                        break
        if role_value is None:
            role_value = default_role

        return {"id": actor_id, "role": str(role_value)}

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
        if AUDIT_ENABLED:
            self.audit_repository.write(audit_entry)

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
        start_datetime = datetime.combine(booking_date, start_time, tzinfo=timezone.utc)
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

        raise ValidationException("Bookings must start and end on the same calendar day")

    @staticmethod
    def _half_hour_index(hh: int, mm: int) -> int:
        """Map HH:MM to the half-hour slot index used by bitmap availability."""
        return hh * 2 + (1 if mm >= 30 else 0)

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

    @staticmethod
    def _is_online_lesson(booking_data: BookingCreate) -> bool:
        """Return True when the lesson is remote/online."""
        location_type = getattr(booking_data, "location_type", None)
        return location_type == "remote"

    def _resolve_instructor_timezone(self, instructor_profile: InstructorProfile) -> str:
        """Resolve instructor timezone with a safe default."""
        instructor_user = getattr(instructor_profile, "user", None)
        instructor_tz = getattr(instructor_user, "timezone", None)
        return instructor_tz or TimezoneService.DEFAULT_TIMEZONE

    @staticmethod
    def _resolve_student_timezone(student: Optional[User]) -> str:
        """Resolve student timezone with a safe default."""
        student_tz = getattr(student, "timezone", None) if student else None
        return student_tz or TimezoneService.DEFAULT_TIMEZONE

    def _resolve_lesson_timezone(
        self,
        booking_data: BookingCreate,
        instructor_profile: InstructorProfile,
    ) -> str:
        instructor_tz = self._resolve_instructor_timezone(instructor_profile)
        is_online = self._is_online_lesson(booking_data)
        return TimezoneService.get_lesson_timezone(instructor_tz, is_online)

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
        end_date = self._resolve_end_date(booking_date, start_time, end_time)
        try:
            start_utc = TimezoneService.local_to_utc(booking_date, start_time, lesson_tz)
            end_utc = TimezoneService.local_to_utc(end_date, end_time, lesson_tz)
        except ValueError as exc:
            raise BusinessRuleException(str(exc)) from exc
        return start_utc, end_utc

    def _get_booking_start_utc(self, booking: Booking) -> datetime:
        """Get booking start time in UTC, handling legacy bookings."""
        if booking.booking_start_utc:
            return cast(datetime, booking.booking_start_utc)

        lesson_tz = booking.lesson_timezone or booking.instructor_tz_at_booking
        if not lesson_tz and booking.instructor:
            lesson_tz = getattr(booking.instructor, "timezone", None)
        lesson_tz = lesson_tz or TimezoneService.DEFAULT_TIMEZONE
        return TimezoneService.local_to_utc(
            booking.booking_date,
            booking.start_time,
            lesson_tz,
        )

    def _get_booking_end_utc(self, booking: Booking) -> datetime:
        """Get booking end time in UTC, handling legacy bookings."""
        if booking.booking_end_utc:
            return cast(datetime, booking.booking_end_utc)

        lesson_tz = booking.lesson_timezone or booking.instructor_tz_at_booking
        if not lesson_tz and booking.instructor:
            lesson_tz = getattr(booking.instructor, "timezone", None)
        lesson_tz = lesson_tz or TimezoneService.DEFAULT_TIMEZONE

        end_date = self._resolve_end_date(
            booking.booking_date, booking.start_time, booking.end_time
        )
        return TimezoneService.local_to_utc(
            end_date,
            booking.end_time,
            lesson_tz,
        )

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

        start_index = self._half_hour_index(start_time_value.hour, start_time_value.minute)
        midnight = time(0, 0)
        if end_time_value == midnight and start_time_value != midnight:
            end_index = 48
        else:
            end_index = self._half_hour_index(end_time_value.hour, end_time_value.minute)

        if not (0 <= start_index < 48) or not (0 < end_index <= 48) or start_index >= end_index:
            raise BusinessRuleException("Requested time is not available")

        local_day = self._resolve_local_booking_day(booking_data, instructor_profile)
        repo = getattr(self, "availability_repository", None)
        if repo is None or not hasattr(repo, "get_day_bits"):
            repo = AvailabilityDayRepository(self.db)
        bits = repo.get_day_bits(booking_data.instructor_id, local_day) or b""

        for idx in range(start_index, end_index):
            byte_i = idx // 8
            bit_mask = 1 << (idx % 8)
            if byte_i >= len(bits) or (bits[byte_i] & bit_mask) == 0:
                raise BusinessRuleException("Requested time is not available")

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
            return INSTRUCTOR_CONFLICT_MESSAGE, "instructor"
        if constraint_name == "bookings_no_overlap_per_student":
            return STUDENT_CONFLICT_MESSAGE, "student"

        return GENERIC_CONFLICT_MESSAGE, None

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
        message = str(exc).lower()
        if "deadlock detected" in message or "exclusion constraint" in message:
            conflict_details = self._build_conflict_details(booking_data, student_id)
            raise BookingConflictException(
                message=GENERIC_CONFLICT_MESSAGE,
                details=conflict_details,
            ) from exc
        raise exc

    @BaseService.measure_operation("create_booking")
    def create_booking(
        self, student: User, booking_data: BookingCreate, selected_duration: int
    ) -> Booking:
        """
        Create an instant booking using selected duration.

        REFACTORED: Split into helper methods to stay under 50 lines.

        Args:
            student: The student creating the booking
            booking_data: Booking creation data with date/time range
            selected_duration: Selected duration in minutes

        Returns:
            Created booking instance

        Raises:
            ValidationException: If validation fails
            NotFoundException: If resources not found
            BusinessRuleException: If business rules violated
            ConflictException: If time slot already booked
        """
        self.log_operation(
            "create_booking",
            student_id=student.id,
            instructor_id=booking_data.instructor_id,
            date=booking_data.booking_date,
            selected_duration=selected_duration,
        )

        # 1. Validate and load required data
        service, instructor_profile = self._validate_booking_prerequisites(student, booking_data)

        # 2. Validate selected duration (strict for new bookings)
        if selected_duration not in service.duration_options:
            raise BusinessRuleException(
                f"Invalid duration {selected_duration}. Available options: {service.duration_options}"
            )

        # 3. Calculate end time for conflict checking
        calculated_end_time = self._calculate_and_validate_end_time(
            booking_data.booking_date,
            booking_data.start_time,
            selected_duration,
        )
        booking_data.end_time = calculated_end_time

        # 4. Ensure requested interval fits published availability (bitmap V2)
        self._validate_against_availability_bits(booking_data, instructor_profile)

        # 5. Check conflicts and apply business rules
        self._check_conflicts_and_rules(booking_data, service, instructor_profile, student)

        # 6. Create the booking with transaction
        transactional_repo = cast(Any, self.repository)
        try:
            with transactional_repo.transaction():
                booking = self._create_booking_record(
                    student, booking_data, service, instructor_profile, selected_duration
                )
                self._enqueue_booking_outbox_event(booking, "booking.created")
                audit_after = self._snapshot_booking(booking)
                self._write_booking_audit(
                    booking,
                    "create",
                    actor=student,
                    before=None,
                    after=audit_after,
                    default_role=RoleName.STUDENT.value,
                )
        except IntegrityError as exc:
            message, scope = self._resolve_integrity_conflict_message(exc)
            conflict_details = self._build_conflict_details(booking_data, student.id)
            if scope:
                conflict_details["conflict_scope"] = scope
            raise BookingConflictException(
                message=message,
                details=conflict_details,
            ) from exc
        except OperationalError as exc:
            if self._is_deadlock_error(exc):
                conflict_details = self._build_conflict_details(booking_data, student.id)
                raise BookingConflictException(
                    message=GENERIC_CONFLICT_MESSAGE,
                    details=conflict_details,
                ) from exc
            raise
        except RepositoryException as exc:
            self._raise_conflict_from_repo_error(exc, booking_data, student.id)

        # 7. Handle post-creation tasks
        self._handle_post_booking_tasks(booking)

        return booking

    @BaseService.measure_operation("create_booking_with_payment_setup")
    def create_booking_with_payment_setup(
        self,
        student: User,
        booking_data: BookingCreate,
        selected_duration: int,
        rescheduled_from_booking_id: Optional[str] = None,
    ) -> Booking:
        """
        Create a booking with payment setup (Phase 2.1).

        Similar to create_booking but:
        1. Sets status to 'PENDING' initially
        2. Creates Stripe SetupIntent for card collection
        3. Returns booking with setup_intent_client_secret attached

        Args:
            student: The student creating the booking
            booking_data: Booking creation data
            selected_duration: Selected duration in minutes

        Returns:
            Booking with setup_intent_client_secret attached
        """
        from ..services.stripe_service import StripeService

        self.log_operation(
            "create_booking_with_payment_setup",
            student_id=student.id,
            instructor_id=booking_data.instructor_id,
            date=booking_data.booking_date,
        )

        # 1. Validate and load required data
        service, instructor_profile = self._validate_booking_prerequisites(student, booking_data)

        # 2. Validate selected duration
        if selected_duration not in service.duration_options:
            raise BusinessRuleException(
                f"Invalid duration {selected_duration}. Available options: {service.duration_options}"
            )

        # 3. Calculate end time
        calculated_end_time = self._calculate_and_validate_end_time(
            booking_data.booking_date,
            booking_data.start_time,
            selected_duration,
        )
        booking_data.end_time = calculated_end_time

        # 4. Ensure requested interval fits published availability (bitmap V2)
        self._validate_against_availability_bits(booking_data, instructor_profile)

        # 5. Check conflicts and apply business rules
        self._check_conflicts_and_rules(booking_data, service, instructor_profile, student)

        # 6. Create booking with PENDING status initially
        transactional_repo = cast(Any, self.repository)
        try:
            with transactional_repo.transaction():
                booking = self._create_booking_record(
                    student, booking_data, service, instructor_profile, selected_duration
                )

                # If this booking was created via reschedule, persist linkage and original lesson datetime
                # for fair cancellation policy (Part 4b: Fair Reschedule Loophole Fix)
                #
                # IMPORTANT: We store the IMMEDIATE previous booking's lesson datetime, NOT traced
                # back to the very first booking in a chain. The question we're answering is:
                # "Was the user in a penalty window when they made THIS reschedule?"
                # That's relative to the booking they're rescheduling FROM.
                #
                # Example: A → B → C (if Part 5 weren't blocking chains)
                # When creating C from B, original_lesson_datetime = B's lesson time
                # NOT: trace back to find A's lesson time
                if rescheduled_from_booking_id:
                    try:
                        # Fetch the IMMEDIATE previous booking (NOT the chain's original)
                        previous_booking = self.repository.get_by_id(rescheduled_from_booking_id)
                        original_lesson_dt = None
                        if previous_booking:
                            # Store the previous booking's lesson datetime for fair cancellation policy
                            original_lesson_dt = self._get_booking_start_utc(previous_booking)

                        updated_booking = self.repository.update(
                            booking.id,
                            rescheduled_from_booking_id=rescheduled_from_booking_id,
                            original_lesson_datetime=original_lesson_dt,
                        )
                        if updated_booking is not None:
                            booking = updated_booking
                    except Exception:
                        # Non-fatal; linkage is analytics-only
                        pass

                # Override status to PENDING until payment confirmed
                booking.status = BookingStatus.PENDING
                booking.payment_status = "pending_payment_method"
                self._enqueue_booking_outbox_event(booking, "booking.created")

                # Transaction handles flush/commit automatically
                audit_after = self._snapshot_booking(booking)
                self._write_booking_audit(
                    booking,
                    "create",
                    actor=student,
                    before=None,
                    after=audit_after,
                    default_role=RoleName.STUDENT.value,
                )
        except IntegrityError as exc:
            message, scope = self._resolve_integrity_conflict_message(exc)
            conflict_details = self._build_conflict_details(booking_data, student.id)
            if scope:
                conflict_details["conflict_scope"] = scope
            raise BookingConflictException(
                message=message,
                details=conflict_details,
            ) from exc
        except OperationalError as exc:
            if self._is_deadlock_error(exc):
                conflict_details = self._build_conflict_details(booking_data, student.id)
                raise BookingConflictException(
                    message=GENERIC_CONFLICT_MESSAGE,
                    details=conflict_details,
                ) from exc
            raise
        except RepositoryException as exc:
            self._raise_conflict_from_repo_error(exc, booking_data, student.id)

        # ========== Phase 2: Stripe SetupIntent (NO transaction) ==========
        stripe_service = StripeService(
            self.db,
            config_service=ConfigService(self.db),
            pricing_service=PricingService(self.db),
        )

        stripe_customer = stripe_service.get_or_create_customer(student.id)

        setup_intent: Any = None
        try:
            # Attempt real Stripe call; tests patch this in CI
            setup_intent = stripe.SetupIntent.create(
                customer=stripe_customer.stripe_customer_id,
                payment_method_types=["card"],
                usage="off_session",  # Will be used for future off-session payments
                metadata={
                    "booking_id": booking.id,
                    "student_id": student.id,
                    "instructor_id": booking_data.instructor_id,
                    "amount_cents": int(booking.total_price * 100),
                },
            )
        except Exception as e:
            # Any Stripe error – fall back to mock (non-network CI path)
            logger.warning(
                f"SetupIntent creation failed for booking {booking.id}: {e}. Falling back to mock.",
            )
            setup_intent = SimpleNamespace(
                id=f"seti_mock_{booking.id}",
                client_secret=f"seti_mock_secret_{booking.id}",
                status="requires_payment_method",
            )

        # ========== Phase 3: Persist SetupIntent (quick transaction) ==========
        with self.transaction():
            refreshed_booking = self.repository.get_by_id(booking.id)
            if not refreshed_booking:
                raise NotFoundException("Booking not found after setup intent creation")

            refreshed_booking.payment_intent_id = setup_intent.id
            setattr(
                refreshed_booking,
                "setup_intent_client_secret",
                getattr(setup_intent, "client_secret", None),
            )

            from ..repositories.payment_repository import PaymentRepository

            payment_repo = PaymentRepository(self.db)
            payment_repo.create_payment_event(
                booking_id=refreshed_booking.id,
                event_type="setup_intent_created",
                event_data={
                    "setup_intent_id": setup_intent.id,
                    "status": setup_intent.status,
                },
            )

            booking = refreshed_booking

        self.log_operation("create_booking_with_payment_setup_completed", booking_id=booking.id)
        return booking

    @BaseService.measure_operation("confirm_booking_payment")
    def confirm_booking_payment(
        self,
        booking_id: str,
        student: User,
        payment_method_id: str,
        save_payment_method: bool = False,
    ) -> Booking:
        """
        Confirm payment method for a booking (Phase 2.1 & 2.2).

        1. Validates booking ownership
        2. Saves payment method to booking
        3. Schedules authorization based on lesson timing
        4. Updates status from PENDING to CONFIRMED

        Args:
            booking_id: The booking to confirm
            student: The student confirming payment
            payment_method_id: Stripe payment method ID
            save_payment_method: Whether to save for future use

        Returns:
            Updated booking with confirmed status
        """
        from datetime import datetime

        from ..repositories.payment_repository import PaymentRepository

        self.log_operation("confirm_booking_payment", booking_id=booking_id, student_id=student.id)

        # Get booking and validate ownership
        booking = self.repository.get_by_id(booking_id)
        if not booking:
            raise NotFoundException(f"Booking {booking_id} not found")

        if booking.student_id != student.id:
            raise NotFoundException("Booking not found")

        if booking.status != BookingStatus.PENDING:
            raise NotFoundException("Booking not found")

        trigger_immediate_auth = False
        immediate_auth_hours_until: Optional[float] = None

        with self.transaction():
            # Save payment method
            booking.payment_method_id = payment_method_id
            booking.payment_status = "payment_method_saved"

            # Save payment method for future use if requested
            if save_payment_method:
                from ..services.stripe_service import StripeService

                stripe_service = StripeService(
                    self.db,
                    config_service=ConfigService(self.db),
                    pricing_service=PricingService(self.db),
                )
                stripe_service.save_payment_method(
                    user_id=student.id, payment_method_id=payment_method_id, set_as_default=False
                )

            # Phase 2.2: Schedule authorization based on lesson timing (UTC)
            booking_start_utc = self._get_booking_start_utc(booking)
            hours_until_lesson = TimezoneService.hours_until(booking_start_utc)

            is_gaming_reschedule = False
            hours_from_original: Optional[float] = None
            if booking.rescheduled_from_booking_id and booking.original_lesson_datetime:
                original_dt = booking.original_lesson_datetime
                if original_dt.tzinfo is None:
                    original_dt = original_dt.replace(tzinfo=timezone.utc)
                reschedule_time = booking.created_at
                if reschedule_time is not None:
                    if reschedule_time.tzinfo is None:
                        reschedule_time = reschedule_time.replace(tzinfo=timezone.utc)
                    hours_from_original = (original_dt - reschedule_time).total_seconds() / 3600
                    is_gaming_reschedule = hours_from_original < 24

            if is_gaming_reschedule:
                # Gaming reschedule: authorize immediately to prevent delayed-auth loophole.
                booking.payment_status = "authorizing"
                trigger_immediate_auth = True
                immediate_auth_hours_until = hours_until_lesson

                payment_repo = PaymentRepository(self.db)
                payment_repo.create_payment_event(
                    booking_id=booking.id,
                    event_type="auth_immediate",
                    event_data={
                        "payment_method_id": payment_method_id,
                        "hours_until_lesson": hours_until_lesson,
                        "hours_from_original": hours_from_original,
                        "scheduled_for": "immediate",
                        "reason": "gaming_reschedule",
                    },
                )

            elif hours_until_lesson <= 24:
                # Lesson is within 24 hours - mark for immediate authorization by background task
                booking.payment_status = "authorizing"

                # Create auth event; actual authorization is handled by worker
                payment_repo = PaymentRepository(self.db)
                payment_repo.create_payment_event(
                    booking_id=booking.id,
                    event_type="auth_immediate",
                    event_data={
                        "payment_method_id": payment_method_id,
                        "hours_until_lesson": hours_until_lesson,
                        "scheduled_for": "immediate",
                    },
                )

            else:
                # Lesson is >24 hours away - schedule authorization
                auth_time = booking_start_utc - timedelta(hours=24)
                booking.payment_status = "scheduled"

                # Create scheduled event using repository
                payment_repo = PaymentRepository(self.db)
                payment_repo.create_payment_event(
                    booking_id=booking.id,
                    event_type="auth_scheduled",
                    event_data={
                        "payment_method_id": payment_method_id,
                        "scheduled_for": auth_time.isoformat(),
                        "hours_until_lesson": hours_until_lesson,
                    },
                )

            # Update booking status to CONFIRMED
            booking.status = BookingStatus.CONFIRMED
            booking.confirmed_at = datetime.now(timezone.utc)

            # Transaction handles flush/commit automatically

        self.log_operation(
            "confirm_booking_payment_completed",
            booking_id=booking.id,
            payment_status=booking.payment_status,
        )

        if trigger_immediate_auth:
            try:
                from app.tasks.payment_tasks import _process_authorization_for_booking

                auth_result = _process_authorization_for_booking(
                    booking.id, immediate_auth_hours_until or 0.0
                )
                if not auth_result.get("success"):
                    logger.warning(
                        "Immediate auth failed for gaming reschedule booking %s: %s",
                        booking.id,
                        auth_result.get("error"),
                    )
            except Exception as exc:
                logger.error(
                    "Immediate auth error for gaming reschedule booking %s: %s",
                    booking.id,
                    exc,
                )

            try:
                self.repository.refresh(booking)
            except Exception:
                pass

        # Create system message in conversation
        try:
            service_name = "Lesson"
            if booking.instructor_service and booking.instructor_service.name:
                service_name = booking.instructor_service.name

            # Check if this is a rescheduled booking
            if booking.rescheduled_from_booking_id:
                old_booking = self.repository.get_by_id(booking.rescheduled_from_booking_id)
                if old_booking:
                    self.system_message_service.create_booking_rescheduled_message(
                        student_id=booking.student_id,
                        instructor_id=booking.instructor_id,
                        booking_id=booking.id,
                        old_date=old_booking.booking_date,
                        old_time=old_booking.start_time,
                        new_date=booking.booking_date,
                        new_time=booking.start_time,
                    )
                else:
                    # Old booking not found, create as new booking
                    self.system_message_service.create_booking_created_message(
                        student_id=booking.student_id,
                        instructor_id=booking.instructor_id,
                        booking_id=booking.id,
                        service_name=service_name,
                        booking_date=booking.booking_date,
                        start_time=booking.start_time,
                    )
            else:
                self.system_message_service.create_booking_created_message(
                    student_id=booking.student_id,
                    instructor_id=booking.instructor_id,
                    booking_id=booking.id,
                    service_name=service_name,
                    booking_date=booking.booking_date,
                    start_time=booking.start_time,
                )
        except Exception as e:
            logger.error(f"Failed to create system message for booking {booking.id}: {str(e)}")

        # Invalidate caches so upcoming lists include the newly confirmed booking
        try:
            self._invalidate_booking_caches(booking)
        except Exception:
            pass
        return booking

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

    @BaseService.measure_operation("cancel_booking")
    def cancel_booking(self, booking_id: str, user: User, reason: Optional[str] = None) -> Booking:
        """
        Cancel a booking.

        Architecture Note (v123): Uses 3-phase pattern to avoid holding DB locks
        during Stripe network calls:
        - Phase 1: Read/validate booking, determine scenario (~5ms)
        - Phase 2: Execute Stripe calls based on scenario (no transaction, 100-500ms)
        - Phase 3: Update booking status, create events (~5ms)

        Args:
            booking_id: ID of booking to cancel
            user: User performing cancellation
            reason: Optional cancellation reason

        Returns:
            Cancelled booking

        Raises:
            NotFoundException: If booking not found
            ValidationException: If user cannot cancel
            BusinessRuleException: If booking not cancellable
        """
        from ..repositories.payment_repository import PaymentRepository
        from ..services.stripe_service import StripeService

        # ========== PHASE 1: Read/validate (quick transaction) ==========
        with self.transaction():
            booking = self.repository.get_booking_with_details(booking_id)
            if not booking:
                raise NotFoundException("Booking not found")

            if user.id not in [booking.student_id, booking.instructor_id]:
                raise ValidationException("You don't have permission to cancel this booking")

            if not booking.is_cancellable:
                raise BusinessRuleException(
                    f"Booking cannot be cancelled - current status: {booking.status}"
                )

            # Extract data needed for Phase 2 (avoid holding ORM objects)
            cancel_ctx = self._build_cancellation_context(booking, user)

        # ========== PHASE 2: Stripe calls (NO transaction) ==========
        stripe_service = StripeService(
            self.db,
            config_service=ConfigService(self.db),
            pricing_service=PricingService(self.db),
        )
        stripe_results = self._execute_cancellation_stripe_calls(cancel_ctx, stripe_service)

        # ========== PHASE 3: Write results (quick transaction) ==========
        with self.transaction():
            # Re-fetch booking to avoid stale ORM object
            booking = self.repository.get_booking_with_details(booking_id)
            if not booking:
                raise NotFoundException("Booking not found after Stripe calls")

            payment_repo = PaymentRepository(self.db)
            audit_before = self._snapshot_booking(booking)

            # Finalize cancellation with Stripe results
            self._finalize_cancellation(booking, cancel_ctx, stripe_results, payment_repo)

            # Cancel the booking
            booking.cancel(user.id, reason)
            self._enqueue_booking_outbox_event(booking, "booking.cancelled")
            audit_after = self._snapshot_booking(booking)
            self._write_booking_audit(
                booking,
                "cancel",
                actor=user,
                before=audit_before,
                after=audit_after,
                default_role=cancel_ctx["default_role"],
            )

        cancelled_by_role = cancel_ctx["cancelled_by_role"]

        # Post-transaction: Publish events and notifications
        self._post_cancellation_actions(booking, cancelled_by_role)

        return booking

    def _build_cancellation_context(self, booking: Booking, user: User) -> Dict[str, Any]:
        """
        Build context for cancellation (Phase 1 helper).
        Extracts all data needed for Stripe calls and finalization.
        """
        booking_start_utc = self._get_booking_start_utc(booking)
        hours_until = TimezoneService.hours_until(booking_start_utc)

        # Part 4b: Fair Reschedule Loophole Fix
        was_gaming_reschedule = False
        hours_from_original: Optional[float] = None
        if booking.rescheduled_from_booking_id and booking.original_lesson_datetime:
            original_dt = booking.original_lesson_datetime
            if original_dt.tzinfo is None:
                original_dt = original_dt.replace(tzinfo=timezone.utc)
            reschedule_time = booking.created_at
            if reschedule_time.tzinfo is None:
                reschedule_time = reschedule_time.replace(tzinfo=timezone.utc)
            hours_from_original = (original_dt - reschedule_time).total_seconds() / 3600
            was_gaming_reschedule = hours_from_original < 24

        cancelled_by_role = "student" if user.id == booking.student_id else "instructor"

        # Determine cancellation scenario
        if cancelled_by_role == "instructor":
            if hours_until > 24:
                scenario = "instructor_cancel_over_24h"
            else:
                scenario = "instructor_cancel_under_24h"
        else:
            if hours_until > 24:
                scenario = "over_24h_gaming" if was_gaming_reschedule else "over_24h_regular"
            elif 12 < hours_until <= 24:
                scenario = "between_12_24h"
            else:
                scenario = "under_12h" if booking.payment_intent_id else "under_12h_no_pi"

            if scenario == "over_24h_gaming" and booking.payment_status != "authorized":
                raise BusinessRuleException(
                    "Gaming reschedule cancellations require an authorized payment"
                )

        # Calculate lesson price for credit scenarios
        lesson_price_cents = int(float(booking.hourly_rate) * booking.duration_minutes * 100 / 60)

        default_role = (
            RoleName.STUDENT.value if user.id == booking.student_id else RoleName.INSTRUCTOR.value
        )

        used_credit_cents = 0
        try:
            from ..repositories.payment_repository import PaymentRepository

            payment_repo = PaymentRepository(self.db)
            used = payment_repo.get_credits_used_by_booking(booking.id)
            used_credit_cents = sum(amount for _, amount in used)
        except Exception as exc:
            logger.warning(
                "Failed to load credits used by booking %s: %s",
                booking.id,
                exc,
            )

        return {
            "booking_id": booking.id,
            "student_id": booking.student_id,
            "instructor_id": booking.instructor_id,
            "payment_intent_id": booking.payment_intent_id,
            "scenario": scenario,
            "hours_until": hours_until,
            "hours_from_original": hours_from_original,
            "was_gaming_reschedule": was_gaming_reschedule,
            "lesson_price_cents": lesson_price_cents,
            "used_credit_cents": used_credit_cents,
            "rescheduled_from_booking_id": booking.rescheduled_from_booking_id,
            "original_lesson_datetime": booking.original_lesson_datetime,
            "default_role": default_role,
            "cancelled_by_role": cancelled_by_role,
            "booking_date": booking.booking_date,
            "start_time": booking.start_time,
        }

    def _execute_cancellation_stripe_calls(
        self, ctx: Dict[str, Any], stripe_service: Any
    ) -> Dict[str, Any]:
        """
        Execute Stripe calls for cancellation (Phase 2).
        No transaction held during network calls.
        """
        results: Dict[str, Any] = {
            "cancel_pi_success": False,
            "capture_success": False,
            "reverse_success": False,
            "capture_data": None,
            "error": None,
        }

        scenario = ctx["scenario"]
        payment_intent_id = ctx["payment_intent_id"]
        booking_id = ctx["booking_id"]

        if scenario == "over_24h_gaming":
            # Capture payment intent, then reverse transfer to retain fee and issue credit.
            if payment_intent_id:
                try:
                    capture = stripe_service.capture_payment_intent(
                        payment_intent_id,
                        idempotency_key=f"capture_resched_{booking_id}",
                    )
                    results["capture_success"] = True
                    results["capture_data"] = {
                        "transfer_id": capture.get("transfer_id"),
                        "amount_received": capture.get("amount_received"),
                        "transfer_amount": capture.get("transfer_amount"),
                    }

                    transfer_id = capture.get("transfer_id")
                    transfer_amount = capture.get("transfer_amount")
                    if transfer_id and transfer_amount:
                        try:
                            stripe_service.reverse_transfer(
                                transfer_id=transfer_id,
                                amount_cents=transfer_amount,
                                idempotency_key=f"reverse_resched_{booking_id}",
                                reason="gaming_reschedule_cancel",
                            )
                            results["reverse_success"] = True
                        except Exception as e:
                            logger.error(f"Transfer reversal failed for booking {booking_id}: {e}")
                except Exception as e:
                    logger.warning(f"Capture not performed for booking {booking_id}: {e}")
                    results["error"] = str(e)

        elif scenario in (
            "over_24h_regular",
            "instructor_cancel_over_24h",
            "instructor_cancel_under_24h",
        ):
            # Cancel payment intent (release authorization)
            if payment_intent_id:
                idem_key = (
                    f"cancel_instructor_{booking_id}"
                    if scenario.startswith("instructor_cancel")
                    else f"cancel_{booking_id}"
                )
                try:
                    stripe_service.cancel_payment_intent(
                        payment_intent_id, idempotency_key=idem_key
                    )
                    results["cancel_pi_success"] = True
                except Exception as e:
                    logger.warning(f"Cancel PI failed for booking {booking_id}: {e}")
                    results["error"] = str(e)

        elif scenario == "between_12_24h":
            # Capture payment intent, then reverse transfer
            if payment_intent_id:
                try:
                    capture = stripe_service.capture_payment_intent(
                        payment_intent_id,
                        idempotency_key=f"capture_cancel_{booking_id}",
                    )
                    results["capture_success"] = True
                    results["capture_data"] = {
                        "transfer_id": capture.get("transfer_id"),
                        "amount_received": capture.get("amount_received"),
                        "transfer_amount": capture.get("transfer_amount"),
                    }

                    # Reverse transfer if available
                    transfer_id = capture.get("transfer_id")
                    transfer_amount = capture.get("transfer_amount")
                    if transfer_id and transfer_amount:
                        try:
                            stripe_service.reverse_transfer(
                                transfer_id=transfer_id,
                                amount_cents=transfer_amount,
                                idempotency_key=f"reverse_{booking_id}",
                                reason="student_cancel_12-24h",
                            )
                            results["reverse_success"] = True
                        except Exception as e:
                            logger.error(f"Transfer reversal failed for booking {booking_id}: {e}")
                except Exception as e:
                    logger.warning(f"Capture not performed for booking {booking_id}: {e}")
                    results["error"] = str(e)

        elif scenario == "under_12h":
            # Capture payment intent only
            if payment_intent_id:
                try:
                    capture = stripe_service.capture_payment_intent(
                        payment_intent_id,
                        idempotency_key=f"capture_late_cancel_{booking_id}",
                    )
                    results["capture_success"] = True
                    results["capture_data"] = {
                        "amount_received": capture.get("amount_received"),
                    }
                except Exception as e:
                    logger.warning(f"Capture not performed for booking {booking_id}: {e}")
                    results["error"] = str(e)

        # scenario == "under_12h_no_pi" - no Stripe calls needed

        return results

    def _finalize_cancellation(
        self,
        booking: Booking,
        ctx: Dict[str, Any],
        stripe_results: Dict[str, Any],
        payment_repo: Any,
    ) -> None:
        """
        Finalize cancellation with Stripe results (Phase 3 helper).
        Creates payment events and updates booking status.
        """
        scenario = ctx["scenario"]
        booking_id = ctx["booking_id"]

        if scenario == "over_24h_gaming":
            if stripe_results["capture_success"]:
                net_credit_cents = max(
                    0, ctx["lesson_price_cents"] - ctx.get("used_credit_cents", 0)
                )
                try:
                    payment_repo.create_platform_credit(
                        user_id=ctx["student_id"],
                        amount_cents=net_credit_cents,
                        reason="Rescheduled booking cancellation (lesson price credit)",
                        source_booking_id=booking_id,
                    )
                except Exception as e:
                    logger.error(f"Failed to create credit for gaming reschedule {booking_id}: {e}")

                payment_repo.create_payment_event(
                    booking_id=booking_id,
                    event_type="credit_created_gaming_reschedule_cancel",
                    event_data={
                        "hours_before_new": round(ctx["hours_until"], 2),
                        "hours_from_original": round(ctx["hours_from_original"], 2)
                        if ctx["hours_from_original"] is not None
                        else None,
                        "lesson_price_cents": ctx["lesson_price_cents"],
                        "used_credit_cents": ctx.get("used_credit_cents", 0),
                        "credit_issued_cents": net_credit_cents,
                        "rescheduled_from": ctx["rescheduled_from_booking_id"],
                        "original_lesson_datetime": ctx["original_lesson_datetime"].isoformat()
                        if ctx["original_lesson_datetime"]
                        else None,
                    },
                )
                booking.payment_status = "credit_issued"
            else:
                payment_repo.create_payment_event(
                    booking_id=booking_id,
                    event_type="capture_failed_gaming_reschedule_cancel",
                    event_data={
                        "payment_intent_id": ctx["payment_intent_id"],
                        "error": stripe_results.get("error"),
                    },
                )
                booking.payment_status = "capture_failed"

        elif scenario == "over_24h_regular":
            payment_repo.create_payment_event(
                booking_id=booking_id,
                event_type="auth_released",
                event_data={
                    "hours_before": round(ctx["hours_until"], 2),
                    "payment_intent_id": ctx["payment_intent_id"],
                },
            )
            booking.payment_status = "released"

        elif scenario == "between_12_24h":
            capture_data = stripe_results.get("capture_data") or {}

            if stripe_results["reverse_success"]:
                payment_repo.create_payment_event(
                    booking_id=booking_id,
                    event_type="transfer_reversed_late_cancel",
                    event_data={
                        "transfer_id": capture_data.get("transfer_id"),
                        "amount": capture_data.get("transfer_amount"),
                        "original_charge_amount": capture_data.get("amount_received"),
                    },
                )

            if stripe_results["capture_success"]:
                net_credit_cents = max(
                    0, ctx["lesson_price_cents"] - ctx.get("used_credit_cents", 0)
                )
                try:
                    payment_repo.create_platform_credit(
                        user_id=ctx["student_id"],
                        amount_cents=net_credit_cents,
                        reason="Cancellation 12-24 hours before lesson (lesson price credit)",
                        source_booking_id=booking_id,
                    )
                except Exception as e:
                    logger.error(f"Failed to create platform credit for booking {booking_id}: {e}")

                payment_repo.create_payment_event(
                    booking_id=booking_id,
                    event_type="credit_created_late_cancel",
                    event_data={
                        "amount": net_credit_cents,
                        "lesson_price_cents": ctx["lesson_price_cents"],
                        "used_credit_cents": ctx.get("used_credit_cents", 0),
                        "total_charged_cents": capture_data.get("amount_received"),
                    },
                )
                booking.payment_status = "credit_issued"
            else:
                payment_repo.create_payment_event(
                    booking_id=booking_id,
                    event_type="capture_failed_late_cancel",
                    event_data={
                        "payment_intent_id": ctx["payment_intent_id"],
                        "error": stripe_results.get("error"),
                    },
                )
                booking.payment_status = "capture_failed"

        elif scenario == "under_12h":
            if stripe_results["capture_success"]:
                capture_data = stripe_results.get("capture_data") or {}
                payment_repo.create_payment_event(
                    booking_id=booking_id,
                    event_type="captured_last_minute_cancel",
                    event_data={
                        "payment_intent_id": ctx["payment_intent_id"],
                        "amount": capture_data.get("amount_received"),
                    },
                )
                booking.payment_status = "captured"
            else:
                payment_repo.create_payment_event(
                    booking_id=booking_id,
                    event_type="capture_failed_last_minute_cancel",
                    event_data={"payment_intent_id": ctx["payment_intent_id"]},
                )
                booking.payment_status = "capture_failed"

        elif scenario == "under_12h_no_pi":
            payment_repo.create_payment_event(
                booking_id=booking_id,
                event_type="capture_skipped_no_intent",
                event_data={"reason": "<12h cancellation without payment_intent"},
            )
            booking.payment_status = "capture_not_possible"

        elif scenario in ("instructor_cancel_over_24h", "instructor_cancel_under_24h"):
            payment_repo.create_payment_event(
                booking_id=booking_id,
                event_type="instructor_cancelled",
                event_data={
                    "hours_before": round(ctx["hours_until"], 2),
                    "payment_intent_id": ctx["payment_intent_id"],
                },
            )
            booking.payment_status = "released"

    def _post_cancellation_actions(self, booking: Booking, cancelled_by_role: str) -> None:
        """
        Post-transaction actions for cancellation.
        Handles event publishing, notifications, and cache invalidation.
        """
        # Publish cancellation event
        try:
            self.event_publisher.publish(
                BookingCancelled(
                    booking_id=booking.id,
                    cancelled_by=cancelled_by_role,
                    cancelled_at=booking.cancelled_at or datetime.now(timezone.utc),
                    refund_amount=None,
                )
            )
        except Exception as e:
            logger.error(f"Failed to send cancellation notification event: {str(e)}")

        # Create system message in conversation
        try:
            self.system_message_service.create_booking_cancelled_message(
                student_id=booking.student_id,
                instructor_id=booking.instructor_id,
                booking_id=booking.id,
                booking_date=booking.booking_date,
                start_time=booking.start_time,
                cancelled_by=cancelled_by_role,
            )
        except Exception as e:
            logger.error(
                f"Failed to create cancellation system message for booking {booking.id}: {str(e)}"
            )

        # Invalidate caches
        self._invalidate_booking_caches(booking)

        # Process refund hooks
        try:
            credit_service = StudentCreditService(self.db)
            credit_service.process_refund_hooks(booking=booking)
        except Exception as exc:
            logger.error(
                "Failed to adjust student credits for cancelled booking %s: %s",
                booking.id,
                exc,
            )

    @BaseService.measure_operation("get_bookings_for_user")
    def get_bookings_for_user(
        self,
        user: User,
        status: Optional[BookingStatus] = None,
        upcoming_only: bool = False,
        exclude_future_confirmed: bool = False,
        include_past_confirmed: bool = False,
        limit: Optional[int] = None,
    ) -> List[Booking]:
        """
        Get bookings for a user (student or instructor) with advanced filtering.

        Args:
            user: User to get bookings for
            status: Optional status filter
            upcoming_only: Only return future bookings
            exclude_future_confirmed: Exclude future confirmed bookings (for History tab)
            include_past_confirmed: Include past confirmed bookings (for BookAgain)
            limit: Optional result limit

        Returns:
            List of bookings
        """
        roles = cast(list[Any], getattr(user, "roles", []) or [])
        is_student = any(cast(str, getattr(role, "name", "")) == RoleName.STUDENT for role in roles)
        if is_student:
            student_bookings: List[Booking] = self.repository.get_student_bookings(
                student_id=user.id,
                status=status,
                upcoming_only=upcoming_only,
                exclude_future_confirmed=exclude_future_confirmed,
                include_past_confirmed=include_past_confirmed,
                limit=limit,
            )
            return student_bookings
        else:  # INSTRUCTOR
            bookings: List[Booking] = self.repository.get_instructor_bookings(
                instructor_id=user.id,
                status=status,
                upcoming_only=upcoming_only,
                exclude_future_confirmed=exclude_future_confirmed,
                include_past_confirmed=include_past_confirmed,
                limit=limit,
            )
            return bookings

    @BaseService.measure_operation("get_booking_stats_for_instructor")
    def get_booking_stats_for_instructor(self, instructor_id: str) -> Dict[str, Any]:
        """
        Get booking statistics for an instructor with caching.

        CACHED: Results are cached for 5 minutes at the service level to reduce
        computation overhead for frequently accessed statistics.

        Args:
            instructor_id: Instructor user ID

        Returns:
            Dictionary of statistics
        """
        # Try to get from cache first if available
        if self.cache_service:
            cache_key = f"booking_stats:instructor:{instructor_id}"
            cached_stats = self.cache_service.get(cache_key)
            if cached_stats is not None:
                logger.debug(f"Cache hit for instructor {instructor_id} booking stats")
                return cast(Dict[str, Any], cached_stats)

        # Calculate stats if not cached
        bookings = self.repository.get_instructor_bookings_for_stats(instructor_id)

        # Use UTC for date-based calculations
        instructor_today = datetime.now(timezone.utc).date()

        # Calculate stats
        total_bookings = len(bookings)
        upcoming_bookings = sum(1 for b in bookings if b.is_upcoming(instructor_today))
        completed_bookings = sum(1 for b in bookings if b.status == BookingStatus.COMPLETED)
        cancelled_bookings = sum(1 for b in bookings if b.status == BookingStatus.CANCELLED)

        # Calculate earnings (only completed bookings)
        total_earnings = sum(
            float(b.total_price) for b in bookings if b.status == BookingStatus.COMPLETED
        )

        # This month's earnings (in instructor's timezone)
        first_day_of_month = instructor_today.replace(day=1)
        this_month_earnings = sum(
            float(b.total_price)
            for b in bookings
            if b.status == BookingStatus.COMPLETED and b.booking_date >= first_day_of_month
        )

        stats = {
            "total_bookings": total_bookings,
            "upcoming_bookings": upcoming_bookings,
            "completed_bookings": completed_bookings,
            "cancelled_bookings": cancelled_bookings,
            "total_earnings": total_earnings,
            "this_month_earnings": this_month_earnings,
            "completion_rate": completed_bookings / total_bookings if total_bookings > 0 else 0,
            "cancellation_rate": cancelled_bookings / total_bookings if total_bookings > 0 else 0,
        }

        # Cache the results for 5 minutes
        if self.cache_service:
            self.cache_service.set(cache_key, stats, tier="hot")
            logger.debug(f"Cached stats for instructor {instructor_id}")

        return stats

    @BaseService.measure_operation("get_booking_for_user")
    def get_booking_for_user(self, booking_id: str, user: User) -> Optional[Booking]:
        """
        Get a booking if the user has access to it.

        Args:
            booking_id: ID of the booking
            user: User requesting the booking

        Returns:
            Booking if user has access, None otherwise
        """
        booking = self.repository.get_booking_with_details(booking_id)

        if booking and user.id in [booking.student_id, booking.instructor_id]:
            return booking

        return None

    @BaseService.measure_operation("update_booking")
    def update_booking(self, booking_id: str, user: User, update_data: BookingUpdate) -> Booking:
        """
        Update booking details (instructor only).

        Args:
            booking_id: ID of booking to update
            user: User performing update
            update_data: Fields to update

        Returns:
            Updated booking

        Raises:
            NotFoundException: If booking not found
            ValidationException: If user cannot update
        """
        with self.transaction():
            booking = self.repository.get_booking_with_details(booking_id)

            if not booking:
                raise NotFoundException("Booking not found")

            # Only instructors can update bookings
            if user.id != booking.instructor_id:
                raise ValidationException("Only the instructor can update booking details")

            audit_before = self._snapshot_booking(booking)

            # Update allowed fields using repository
            update_dict = {}
            if update_data.instructor_note is not None:
                update_dict["instructor_note"] = update_data.instructor_note
            if update_data.meeting_location is not None:
                update_dict["meeting_location"] = update_data.meeting_location

            if update_dict:
                updated_booking = self.repository.update(booking_id, **update_dict)
                if updated_booking is not None:
                    booking = updated_booking

            # Reload with relationships
            refreshed_booking = self.repository.get_booking_with_details(booking_id)
            if not refreshed_booking:
                raise NotFoundException("Booking not found")
            audit_after = self._snapshot_booking(refreshed_booking)
            self._write_booking_audit(
                refreshed_booking,
                "update",
                actor=user,
                before=audit_before,
                after=audit_after,
                default_role=RoleName.INSTRUCTOR.value,
            )
            booking = refreshed_booking

        # Cache invalidation outside transaction
        self._invalidate_booking_caches(booking)

        return booking

    @BaseService.measure_operation("complete_booking")
    def complete_booking(self, booking_id: str, instructor: User) -> Booking:
        """
        Mark a booking as completed (instructor only).

        Args:
            booking_id: ID of booking to complete
            instructor: Instructor marking as complete

        Returns:
            Completed booking

        Raises:
            NotFoundException: If booking not found
            ValidationException: If user is not instructor
            BusinessRuleException: If booking cannot be completed
        """
        instructor_roles = cast(list[Any], getattr(instructor, "roles", []) or [])
        is_instructor = any(
            cast(str, getattr(role, "name", "")) == RoleName.INSTRUCTOR for role in instructor_roles
        )
        if not is_instructor:
            raise ValidationException("Only instructors can mark bookings as complete")

        with self.transaction():
            # Load and validate booking
            booking = self.repository.get_booking_with_details(booking_id)

            if not booking:
                raise NotFoundException("Booking not found")

            if booking.instructor_id != instructor.id:
                raise ValidationException("You can only complete your own bookings")

            if booking.status != BookingStatus.CONFIRMED:
                raise BusinessRuleException(
                    f"Only confirmed bookings can be completed - current status: {booking.status}"
                )

            audit_before = self._snapshot_booking(booking)

            # Mark as complete using repository method
            completed_booking = self.repository.complete_booking(booking_id)
            if completed_booking is None:
                raise NotFoundException("Booking not found")
            booking = completed_booking
            self._enqueue_booking_outbox_event(booking, "booking.completed")
            audit_after = self._snapshot_booking(booking)
            self._write_booking_audit(
                booking,
                "complete",
                actor=instructor,
                before=audit_before,
                after=audit_after,
                default_role=RoleName.INSTRUCTOR.value,
            )

        # External operations outside transaction
        # Reload booking with details for cache invalidation
        refreshed_booking = self.repository.get_booking_with_details(booking_id)
        if refreshed_booking is None:
            raise NotFoundException("Booking not found")
        self._invalidate_booking_caches(refreshed_booking)

        try:
            credit_service = StudentCreditService(self.db)
            credit_service.maybe_issue_milestone_credit(
                student_id=refreshed_booking.student_id,
                booking_id=refreshed_booking.id,
            )
        except Exception as exc:
            logger.error(
                "Failed issuing milestone credit for booking completion %s: %s",
                booking_id,
                exc,
            )

        # Create system message in conversation
        try:
            service_name = None
            if refreshed_booking.instructor_service and refreshed_booking.instructor_service.name:
                service_name = refreshed_booking.instructor_service.name

            self.system_message_service.create_booking_completed_message(
                student_id=refreshed_booking.student_id,
                instructor_id=refreshed_booking.instructor_id,
                booking_id=refreshed_booking.id,
                booking_date=refreshed_booking.booking_date,
                service_name=service_name,
            )
        except Exception as e:
            logger.error(
                f"Failed to create completion system message for booking {booking_id}: {str(e)}"
            )

        return refreshed_booking

    @BaseService.measure_operation("instructor_mark_complete")
    def instructor_mark_complete(
        self,
        booking_id: str,
        instructor: User,
        notes: Optional[str] = None,
    ) -> Booking:
        """
        Mark a lesson as completed by the instructor with payment tracking.

        This triggers the 24-hour payment capture timer. The payment will be
        captured 24 hours after completion, giving the student time to dispute.

        Args:
            booking_id: ID of the booking to complete
            instructor: The instructor marking completion
            notes: Optional completion notes

        Returns:
            Updated booking

        Raises:
            NotFoundException: If booking not found
            ValidationException: If not the instructor's booking
            BusinessRuleException: If booking cannot be completed
        """
        from ..repositories.payment_repository import PaymentRepository
        from ..services.badge_award_service import BadgeAwardService

        payment_repo = PaymentRepository(self.db)

        with self.transaction():
            booking = self.repository.get_by_id(booking_id)
            if not booking:
                raise NotFoundException("Booking not found")

            if booking.instructor_id != instructor.id:
                raise ValidationException("You can only mark your own lessons as complete")

            if booking.status != BookingStatus.CONFIRMED:
                raise BusinessRuleException(
                    f"Cannot mark booking as complete. Current status: {booking.status}"
                )

            # Verify lesson has ended
            now = datetime.now(timezone.utc)
            lesson_end_utc = self._get_booking_end_utc(booking)
            if lesson_end_utc > now:
                raise BusinessRuleException("Cannot mark lesson as complete before it ends")

            # Mark as completed
            booking.status = BookingStatus.COMPLETED
            booking.completed_at = now
            if notes:
                booking.instructor_note = notes

            # Record payment completion event
            payment_repo.create_payment_event(
                booking_id=booking.id,
                event_type="instructor_marked_complete",
                event_data={
                    "instructor_id": instructor.id,
                    "completed_at": now.isoformat(),
                    "notes": notes,
                    "payment_capture_scheduled_for": (now + timedelta(hours=24)).isoformat(),
                },
            )

            # Trigger badge checks
            badge_service = BadgeAwardService(self.db)
            booked_at = booking.confirmed_at or booking.created_at or now
            category_slug = None
            try:
                instructor_service = booking.instructor_service
                if instructor_service and instructor_service.catalog_entry:
                    category = instructor_service.catalog_entry.category
                    if category:
                        category_slug = category.slug
            except AttributeError:
                category_slug = None

            badge_service.check_and_award_on_lesson_completed(
                student_id=booking.student_id,
                lesson_id=booking.id,
                instructor_id=booking.instructor_id,
                category_slug=category_slug,
                booked_at_utc=booked_at,
                completed_at_utc=now,
            )

        # Reload for fresh state after commit
        refreshed = self.repository.get_by_id(booking_id)
        if refreshed is None:
            raise NotFoundException("Booking not found after completion")
        return refreshed

    @BaseService.measure_operation("instructor_dispute_completion")
    def instructor_dispute_completion(
        self,
        booking_id: str,
        instructor: User,
        reason: str,
    ) -> Booking:
        """
        Dispute a lesson completion as an instructor.

        Used when a student marks a lesson as complete but the instructor disagrees.
        This pauses payment capture pending resolution.

        Args:
            booking_id: ID of the booking to dispute
            instructor: The instructor disputing
            reason: Reason for the dispute

        Returns:
            Updated booking

        Raises:
            NotFoundException: If booking not found
            ValidationException: If not the instructor's booking
        """
        from ..repositories.payment_repository import PaymentRepository

        payment_repo = PaymentRepository(self.db)

        with self.transaction():
            booking = self.repository.get_by_id(booking_id)
            if not booking:
                raise NotFoundException("Booking not found")

            if booking.instructor_id != instructor.id:
                raise ValidationException("You can only dispute your own lessons")

            # Record dispute event
            payment_repo.create_payment_event(
                booking_id=booking.id,
                event_type="completion_disputed",
                event_data={
                    "disputed_by": instructor.id,
                    "reason": reason,
                    "disputed_at": datetime.now(timezone.utc).isoformat(),
                    "payment_capture_paused": True,
                },
            )

            # Update payment status to prevent capture
            if booking.payment_status == "authorized":
                booking.payment_status = "disputed"

        # Reload for fresh state after commit
        refreshed = self.repository.get_by_id(booking_id)
        if refreshed is None:
            raise NotFoundException("Booking not found after dispute")
        return refreshed

    @BaseService.measure_operation("mark_no_show")
    def mark_no_show(self, booking_id: str, instructor: User) -> Booking:
        """
        Mark a booking as no-show (instructor only).

        A no-show indicates the student did not attend the scheduled lesson.

        Args:
            booking_id: ID of booking to mark as no-show
            instructor: Instructor marking as no-show

        Returns:
            Booking marked as no-show

        Raises:
            NotFoundException: If booking not found
            ValidationException: If user is not instructor
            BusinessRuleException: If booking cannot be marked as no-show
        """
        instructor_roles = cast(list[Any], getattr(instructor, "roles", []) or [])
        is_instructor = any(
            cast(str, getattr(role, "name", "")) == RoleName.INSTRUCTOR for role in instructor_roles
        )
        if not is_instructor:
            raise ValidationException("Only instructors can mark bookings as no-show")

        with self.transaction():
            # Load and validate booking
            booking = self.repository.get_booking_with_details(booking_id)

            if not booking:
                raise NotFoundException("Booking not found")

            if booking.instructor_id != instructor.id:
                raise ValidationException("You can only mark your own bookings as no-show")

            if booking.status != BookingStatus.CONFIRMED:
                raise BusinessRuleException(
                    f"Only confirmed bookings can be marked as no-show - current status: {booking.status}"
                )

            audit_before = self._snapshot_booking(booking)

            # Mark as no-show using model method
            booking.mark_no_show()

            # Flush to persist status change
            self.repository.flush()

            self._enqueue_booking_outbox_event(booking, "booking.no_show")
            audit_after = self._snapshot_booking(booking)
            self._write_booking_audit(
                booking,
                "no_show",
                actor=instructor,
                before=audit_before,
                after=audit_after,
                default_role=RoleName.INSTRUCTOR.value,
            )

        # External operations outside transaction
        # Reload booking with details for cache invalidation
        refreshed_booking = self.repository.get_booking_with_details(booking_id)
        if refreshed_booking is None:
            raise NotFoundException("Booking not found")
        self._invalidate_booking_caches(refreshed_booking)

        return refreshed_booking

    @BaseService.measure_operation("check_availability")
    def check_availability(
        self,
        instructor_id: str,
        booking_date: date,
        start_time: time,
        end_time: time,
        service_id: str,
        exclude_booking_id: Optional[str] = None,
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
        # Check for conflicts
        has_conflict = self.repository.check_time_conflict(
            instructor_id=instructor_id,
            booking_date=booking_date,
            start_time=start_time,
            end_time=end_time,
            exclude_booking_id=exclude_booking_id,
        )

        if has_conflict:
            return {"available": False, "reason": "Time slot has conflicts with existing bookings"}

        # Get service and instructor profile using repositories
        service = self.conflict_checker_repository.get_active_service(service_id)
        if not service:
            return {"available": False, "reason": "Service not found or no longer available"}

        # Get instructor profile
        instructor_profile = self.conflict_checker_repository.get_instructor_profile(instructor_id)
        if instructor_profile is None:
            return {
                "available": False,
                "reason": "Instructor profile not found",
            }

        # Check minimum advance booking using UTC.
        min_advance_hours = getattr(instructor_profile, "min_advance_booking_hours", 0) or 0
        now_utc = datetime.now(timezone.utc)
        lesson_tz = TimezoneService.get_lesson_timezone(
            self._resolve_instructor_timezone(instructor_profile),
            is_online=False,
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
        if min_advance_hours >= 24:
            min_booking_dt = now_utc + timedelta(hours=min_advance_hours)
            min_date_only = min_booking_dt.date()

            if booking_start_utc.date() < min_date_only or (
                booking_start_utc.date() == min_date_only
                and booking_start_utc.time() < min_booking_dt.time()
            ):
                return {
                    "available": False,
                    "reason": f"Must book at least {min_advance_hours} hours in advance",
                    "min_advance_hours": min_advance_hours,
                }
        else:
            # For <24 hour min advance, do precise time comparison
            hours_until = TimezoneService.hours_until(booking_start_utc)
            if hours_until < min_advance_hours:
                return {
                    "available": False,
                    "reason": f"Must book at least {min_advance_hours} hours in advance",
                    "min_advance_hours": min_advance_hours,
                }

        return {
            "available": True,
            "time_info": {
                "date": booking_date.isoformat(),
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "instructor_id": instructor_id,
            },
        }

    @BaseService.measure_operation("send_booking_reminders")
    def send_booking_reminders(self) -> int:
        """
        Send 24-hour reminder emails for tomorrow's bookings.

        Returns:
            Number of reminders sent
        """
        # Use UTC-only scheduling to avoid mixed timezone behavior.
        utc_today = datetime.now(timezone.utc).date()
        target_date = utc_today + timedelta(days=1)

        bookings = self.repository.get_bookings_for_date(
            booking_date=target_date, status=BookingStatus.CONFIRMED, with_relationships=True
        )

        sent_count = 0

        for booking in bookings:
            try:
                # Queue reminder event for this specific booking
                self.event_publisher.publish(
                    BookingReminder(
                        booking_id=booking.id,
                        reminder_type="24h",
                    )
                )
                sent_count += 1
            except Exception as e:
                logger.error(f"Error queueing reminder for booking {booking.id}: {str(e)}")

        return sent_count

    # Private helper methods for create_booking refactoring

    def _validate_booking_prerequisites(
        self, student: User, booking_data: BookingCreate
    ) -> Tuple[InstructorService, InstructorProfile]:
        """
        Validate student role and load required data.

        Args:
            student: The student creating the booking
            booking_data: Booking creation data

        Returns:
            Tuple of (service, instructor_profile)

        Raises:
            ValidationException: If validation fails
            NotFoundException: If resources not found
        """
        # Validate student role
        if not any(role.name == RoleName.STUDENT for role in student.roles):
            raise ValidationException("Only students can create bookings")

        # Use repositories instead of direct queries
        service = self.conflict_checker_repository.get_active_service(
            booking_data.instructor_service_id
        )
        if not service:
            raise NotFoundException("Service not found or no longer available")

        # Get instructor profile
        instructor_profile = self.conflict_checker_repository.get_instructor_profile(
            booking_data.instructor_id
        )
        if not instructor_profile:
            raise NotFoundException("Instructor profile not found")

        # Verify service belongs to instructor
        if service.instructor_profile_id != instructor_profile.id:
            raise ValidationException("Service does not belong to this instructor")

        # Check instructor account status - only active instructors can receive bookings
        # Use repository to get user data
        user_repository = RepositoryFactory.create_base_repository(self.db, User)
        instructor_user = user_repository.get_by_id(booking_data.instructor_id)
        if instructor_user and instructor_user.account_status != "active":
            if instructor_user.account_status == "suspended":
                raise BusinessRuleException(
                    "This instructor is temporarily suspended and cannot receive new bookings"
                )
            elif instructor_user.account_status == "deactivated":
                raise BusinessRuleException(
                    "This instructor account has been deactivated and cannot receive bookings"
                )
            else:
                raise BusinessRuleException("This instructor cannot receive bookings at this time")

        if must_be_verified_for_public() and not is_verified(
            getattr(instructor_profile, "bgc_status", None)
        ):
            raise BusinessRuleException(
                "This instructor is pending verification and cannot be booked at this time"
            )

        return service, instructor_profile

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
        # Check for instructor time conflicts
        if booking_data.end_time is None:
            raise ValidationException("End time must be specified before conflict checks")

        lesson_tz = self._resolve_lesson_timezone(booking_data, instructor_profile)
        booking_start_utc, _ = self._resolve_booking_times_utc(
            booking_data.booking_date,
            booking_data.start_time,
            booking_data.end_time,
            lesson_tz,
        )

        existing_conflicts = self.repository.check_time_conflict(
            instructor_id=booking_data.instructor_id,
            booking_date=booking_data.booking_date,
            start_time=booking_data.start_time,
            end_time=booking_data.end_time,
            exclude_booking_id=exclude_booking_id,
        )

        if existing_conflicts:
            conflict_details = self._build_conflict_details(
                booking_data, getattr(student, "id", None)
            )
            conflict_details["conflict_scope"] = "instructor"
            raise BookingConflictException(
                message=INSTRUCTOR_CONFLICT_MESSAGE,
                details=conflict_details,
            )

        # Check for student time conflicts
        if student:
            student_conflicts = self.repository.check_student_time_conflict(
                student_id=student.id,
                booking_date=booking_data.booking_date,
                start_time=booking_data.start_time,
                end_time=booking_data.end_time,
                exclude_booking_id=exclude_booking_id,
            )

            if student_conflicts:
                conflict_details = self._build_conflict_details(booking_data, student.id)
                conflict_details["conflict_scope"] = "student"
                raise BookingConflictException(
                    message=STUDENT_CONFLICT_MESSAGE,
                    details=conflict_details,
                )

        # Check minimum advance booking time (UTC)
        # For instructors with >=24 hour min advance, enforce on date granularity to avoid HH:MM boundary flakiness
        min_advance_hours = getattr(instructor_profile, "min_advance_booking_hours", 0) or 0
        now_utc = datetime.now(timezone.utc)

        if min_advance_hours >= 24:
            min_booking_dt = now_utc + timedelta(hours=min_advance_hours)
            min_date_only = min_booking_dt.date()

            if booking_start_utc.date() < min_date_only or (
                booking_start_utc.date() == min_date_only
                and booking_start_utc.time() < min_booking_dt.time()
            ):
                raise BusinessRuleException(
                    f"Bookings must be made at least {min_advance_hours} hours in advance"
                )
        else:
            hours_until = TimezoneService.hours_until(booking_start_utc)
            if hours_until < min_advance_hours:
                raise BusinessRuleException(
                    f"Bookings must be made at least {min_advance_hours} hours in advance"
                )

    def _create_booking_record(
        self,
        student: User,
        booking_data: BookingCreate,
        service: InstructorService,
        instructor_profile: InstructorProfile,
        selected_duration: int,
    ) -> Booking:
        """
        Create the booking record with pricing calculation.

        Args:
            student: Student creating the booking
            booking_data: Booking data
            service: Service being booked
            instructor_profile: Instructor's profile
            selected_duration: Selected duration in minutes

        Returns:
            Created booking instance
        """
        if booking_data.end_time is None:
            raise ValidationException("End time must be calculated before creating a booking")
        end_time_value = booking_data.end_time

        instructor_tz = self._resolve_instructor_timezone(instructor_profile)
        student_tz = self._resolve_student_timezone(student)
        lesson_tz = TimezoneService.get_lesson_timezone(
            instructor_tz, self._is_online_lesson(booking_data)
        )
        booking_start_utc, booking_end_utc = self._resolve_booking_times_utc(
            booking_data.booking_date,
            booking_data.start_time,
            end_time_value,
            lesson_tz,
        )

        # Calculate pricing based on selected duration
        total_price = service.session_price(selected_duration)

        # Derive service area summary for booking record
        service_area_summary = self._determine_service_area_summary(instructor_profile.user_id)

        # Create the booking
        booking = self.repository.create(
            student_id=student.id,
            instructor_id=booking_data.instructor_id,
            instructor_service_id=service.id,
            booking_date=booking_data.booking_date,
            start_time=booking_data.start_time,
            end_time=end_time_value,
            booking_start_utc=booking_start_utc,
            booking_end_utc=booking_end_utc,
            lesson_timezone=lesson_tz,
            instructor_tz_at_booking=instructor_tz,
            student_tz_at_booking=student_tz,
            service_name=service.catalog_entry.name if service.catalog_entry else "Unknown Service",
            hourly_rate=service.hourly_rate,
            total_price=total_price,
            duration_minutes=selected_duration,
            status=BookingStatus.CONFIRMED,
            service_area=service_area_summary,
            meeting_location=booking_data.meeting_location,
            location_type=booking_data.location_type,
            student_note=booking_data.student_note,
        )

        # Load relationships for response
        detailed_booking = self.repository.get_booking_with_details(booking.id)

        pricing_service = PricingService(self.db)
        pricing_service.compute_booking_pricing(booking.id, applied_credit_cents=0, persist=False)

        if detailed_booking is not None:
            return detailed_booking

        return booking

    def _determine_service_area_summary(self, instructor_id: str) -> str:
        """Summarize instructor service areas for booking metadata."""
        areas = self.service_area_repository.list_for_instructor(instructor_id)
        boroughs: set[str] = set()

        for area in areas:
            region = getattr(area, "neighborhood", None)
            borough = getattr(region, "parent_region", None)
            region_meta = getattr(region, "region_metadata", None)
            if isinstance(region_meta, dict):
                meta_borough = region_meta.get("borough")
                if isinstance(meta_borough, str) and meta_borough:
                    borough = meta_borough
            if isinstance(borough, str) and borough:
                boroughs.add(borough)

        sorted_boroughs = sorted(boroughs)
        if not sorted_boroughs:
            return ""
        if len(sorted_boroughs) <= 2:
            return ", ".join(sorted_boroughs)
        return f"{sorted_boroughs[0]} + {len(sorted_boroughs) - 1} more"

    def _handle_post_booking_tasks(
        self, booking: Booking, is_reschedule: bool = False, old_booking: Optional[Booking] = None
    ) -> None:
        """
        Handle notifications, system messages, and cache invalidation after booking creation.

        Args:
            booking: The created booking
            is_reschedule: Whether this is a rescheduled booking
            old_booking: The original booking if this is a reschedule
        """
        # Publish async notification event
        try:
            self.event_publisher.publish(
                BookingCreated(
                    booking_id=booking.id,
                    student_id=booking.student_id,
                    instructor_id=booking.instructor_id,
                    created_at=booking.created_at or datetime.now(timezone.utc),
                )
            )
        except Exception as e:
            logger.error(f"Failed to enqueue booking confirmation event: {str(e)}")

        # Create system message in conversation
        try:
            service_name = "Lesson"
            if booking.instructor_service and booking.instructor_service.name:
                service_name = booking.instructor_service.name

            if is_reschedule and old_booking:
                # Create rescheduled message
                self.system_message_service.create_booking_rescheduled_message(
                    student_id=booking.student_id,
                    instructor_id=booking.instructor_id,
                    booking_id=booking.id,
                    old_date=old_booking.booking_date,
                    old_time=old_booking.start_time,
                    new_date=booking.booking_date,
                    new_time=booking.start_time,
                )
            else:
                # Create booking created message
                self.system_message_service.create_booking_created_message(
                    student_id=booking.student_id,
                    instructor_id=booking.instructor_id,
                    booking_id=booking.id,
                    service_name=service_name,
                    booking_date=booking.booking_date,
                    start_time=booking.start_time,
                )
        except Exception as e:
            logger.error(f"Failed to create system message for booking {booking.id}: {str(e)}")

        # Invalidate relevant caches
        self._invalidate_booking_caches(booking)

    # Private helper methods for find_booking_opportunities refactoring

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
        from ..repositories.availability_day_repository import AvailabilityDayRepository
        from ..utils.bitset import windows_from_bits

        repo = AvailabilityDayRepository(self.db)
        bits = repo.get_day_bits(instructor_id, target_date)
        if not bits:
            return []

        windows_str: list[tuple[str, str]] = windows_from_bits(bits)
        earliest_minutes = self._time_to_minutes(earliest_time)
        latest_minutes = self._time_to_minutes(latest_time)
        if latest_minutes <= earliest_minutes and latest_time == time(0, 0):
            latest_minutes = 24 * 60
        if latest_minutes <= earliest_minutes and latest_time == time(0, 0):
            latest_minutes = 24 * 60
        result: list[dict[str, Any]] = []
        for start_str, end_str in windows_str:
            start_minutes = self._bitmap_str_to_minutes(start_str)
            end_minutes = self._bitmap_str_to_minutes(end_str)
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
        earliest_minutes = self._time_to_minutes(earliest_time)
        latest_minutes = self._time_to_minutes(latest_time)
        if latest_minutes <= earliest_minutes and latest_time == time(0, 0):
            latest_minutes = 24 * 60

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

    # Existing private helper methods

    def _apply_cancellation_rules(self, booking: Booking, user: User) -> None:
        """Apply business rules for cancellation."""
        # Check cancellation deadline using UTC
        booking_start_utc = self._get_booking_start_utc(booking)
        cancellation_deadline = booking_start_utc - timedelta(hours=2)
        now_utc = datetime.now(timezone.utc)

        if now_utc > cancellation_deadline:
            # Log late cancellation but allow it
            logger.warning(f"Late cancellation for booking {booking.id} by user {user.id}")

    def _calculate_pricing(
        self, service: InstructorService, start_time: time, end_time: time
    ) -> Dict[str, Any]:
        """Calculate booking pricing based on time range."""
        # Calculate duration
        # Use a reference date for duration calculations
        # This is just for calculating the duration, not timezone-specific
        reference_date = date(2024, 1, 1)
        start = datetime.combine(reference_date, start_time, tzinfo=timezone.utc)
        end = datetime.combine(reference_date, end_time, tzinfo=timezone.utc)
        duration = end - start
        duration_minutes = int(duration.total_seconds() / 60)

        # Calculate price based on actual booking duration
        hours = duration_minutes / 60
        total_price = float(service.hourly_rate) * hours

        return {
            "duration_minutes": duration_minutes,
            "total_price": total_price,
            "hourly_rate": service.hourly_rate,
        }

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
        if self.cache_service:
            try:
                # Invalidate all availability caches for the instructor and specific date
                self.cache_service.invalidate_instructor_availability(
                    booking.instructor_id, [booking.booking_date]
                )
                # Invalidate booking statistics cache for the instructor (actively used)
                stats_cache_key = f"booking_stats:instructor:{booking.instructor_id}"
                self.cache_service.delete(stats_cache_key)
                logger.debug(
                    f"Invalidated availability and stats caches for instructor {booking.instructor_id}"
                )
            except Exception as cache_error:
                logger.warning(f"Failed to invalidate caches: {cache_error}")

            # Invalidate BookingRepository cached methods
            # The cache keys use hashed kwargs, so we need to invalidate ALL cached queries
            try:
                self.cache_service.delete_pattern("booking:get_student_bookings:*")
                self.cache_service.delete_pattern("booking:get_instructor_bookings:*")
                logger.debug(
                    f"Invalidated BookingRepository caches after booking {booking.id} change"
                )
            except Exception as e:
                logger.warning(f"Failed to invalidate BookingRepository caches: {e}")

    # =========================================================================
    # Methods for route layer (no direct DB/repo access needed in routes)
    # =========================================================================

    @BaseService.measure_operation("get_booking_pricing_preview")
    def get_booking_pricing_preview(
        self,
        booking_id: str,
        current_user_id: str,
        applied_credit_cents: int = 0,
    ) -> Optional[Dict[str, Any]]:
        """
        Get pricing preview for a booking.

        Args:
            booking_id: Booking ULID
            current_user_id: Current user's ID (for access control)
            applied_credit_cents: Credits to apply

        Returns:
            Dict with pricing data or None if booking not found/access denied
        """
        from ..schemas.pricing_preview import PricingPreviewData
        from ..services.pricing_service import PricingService

        booking = self.repository.get_by_id(booking_id)
        if not booking:
            return None

        # Access control
        allowed_participants = {booking.student_id, booking.instructor_id}
        if current_user_id not in allowed_participants:
            logger.warning(
                "pricing_preview.forbidden",
                extra={
                    "booking_id": booking_id,
                    "requested_by": current_user_id,
                },
            )
            return {"error": "access_denied"}

        pricing_service = PricingService(self.db)
        pricing_data: PricingPreviewData = pricing_service.compute_booking_pricing(
            booking_id,
            applied_credit_cents,
            False,
        )
        return dict(pricing_data)

    @BaseService.measure_operation("get_booking_with_payment_summary")
    def get_booking_with_payment_summary(
        self,
        booking_id: str,
        user: "User",
    ) -> Optional[tuple["Booking", Optional["PaymentSummary"]]]:
        """
        Get booking with payment summary for student.

        Args:
            booking_id: Booking ULID
            user: Current user (for access control and payment summary)

        Returns:
            Tuple of (booking, payment_summary) or None if not found
        """
        from ..repositories.factory import RepositoryFactory
        from ..repositories.review_repository import ReviewTipRepository
        from ..services.config_service import ConfigService
        from ..services.payment_summary_service import build_student_payment_summary

        booking = self.get_booking_for_user(booking_id, user)
        if not booking:
            return None

        payment_summary: Optional[PaymentSummary] = None
        if booking.student_id == user.id:
            config_service = ConfigService(self.db)
            pricing_config, _ = config_service.get_pricing_config()
            payment_repo = RepositoryFactory.create_payment_repository(self.db)
            tip_repo = ReviewTipRepository(self.db)
            payment_summary = build_student_payment_summary(
                booking=booking,
                pricing_config=pricing_config,
                payment_repo=payment_repo,
                review_tip_repo=tip_repo,
            )

        return (booking, payment_summary)

    @BaseService.measure_operation("check_student_time_conflict")
    def check_student_time_conflict(
        self,
        student_id: str,
        booking_date: "date",
        start_time: "time",
        end_time: "time",
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
            conflicting = self.repository.check_student_time_conflict(
                student_id=student_id,
                booking_date=booking_date,
                start_time=start_time,
                end_time=end_time,
                exclude_booking_id=exclude_booking_id,
            )
            return bool(conflicting)
        except Exception:
            return False

    @BaseService.measure_operation("validate_reschedule_allowed")
    def validate_reschedule_allowed(self, booking: "Booking") -> None:
        """
        Validate that a booking can be rescheduled (Part 5: Block Second Reschedule).

        A booking can only be rescheduled ONCE. If it was already created via
        reschedule (rescheduled_from_booking_id is set), it cannot be rescheduled again.

        Args:
            booking: The booking to validate

        Raises:
            BusinessRuleException: If booking has already been rescheduled once
        """
        if booking.rescheduled_from_booking_id:
            raise BusinessRuleException(
                message="You've already rescheduled this booking. To change the date again, please cancel (for credit) and book a new lesson.",
                code="reschedule_limit_reached",
            )

    @BaseService.measure_operation("validate_reschedule_payment_method")
    def validate_reschedule_payment_method(
        self,
        user_id: str,
    ) -> tuple[bool, Optional[str]]:
        """
        Validate that user has a valid payment method for rescheduling.

        Args:
            user_id: User ULID

        Returns:
            Tuple of (has_valid_method, stripe_payment_method_id)
        """
        from ..services.config_service import ConfigService as _ConfigService
        from ..services.pricing_service import PricingService as _PricingService
        from ..services.stripe_service import StripeService as _StripeService

        config_service = _ConfigService(self.db)
        pricing_service = _PricingService(self.db)
        stripe_service = _StripeService(
            self.db,
            config_service=config_service,
            pricing_service=pricing_service,
        )

        default_pm = stripe_service.payment_repository.get_default_payment_method(user_id)
        if not default_pm or not default_pm.stripe_payment_method_id:
            return False, None

        return True, default_pm.stripe_payment_method_id

    @BaseService.measure_operation("abort_pending_booking")
    def abort_pending_booking(self, booking_id: str) -> bool:
        """
        Abort a pending booking (used when reschedule payment confirmation fails).

        Only aborts bookings in pending_payment status.

        Args:
            booking_id: Booking ULID to abort

        Returns:
            True if aborted, False otherwise
        """
        try:
            booking = self.repository.get_by_id(booking_id)
            if not booking:
                return False

            # Only abort pending bookings
            if booking.status != BookingStatus.PENDING:
                logger.warning(
                    f"Cannot abort booking {booking_id} - status is {booking.status}, not pending_payment"
                )
                return False

            with self.transaction():
                self.repository.delete(booking.id)

            logger.info(f"Aborted pending booking {booking_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to abort pending booking {booking_id}: {e}")
            return False
