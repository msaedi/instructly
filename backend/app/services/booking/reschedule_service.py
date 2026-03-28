from __future__ import annotations

import logging
from types import ModuleType
from typing import TYPE_CHECKING, Any, ContextManager, Dict, Optional, cast

from sqlalchemy.exc import IntegrityError, OperationalError

from ...core.enums import RoleName
from ...core.exceptions import (
    BookingConflictException,
    BusinessRuleException,
    NotFoundException,
    RepositoryException,
    ValidationException,
)
from ...models.booking import Booking, BookingStatus, PaymentStatus
from ...models.instructor import InstructorProfile
from ...models.service_catalog import InstructorService
from ...models.user import User
from ...schemas.booking import BookingCreate, BookingRescheduleRequest
from ...utils.safe_cast import safe_float as _safe_float, safe_str as _safe_str
from ..base import BaseService

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from ...repositories.booking_repository import BookingRepository
    from ..config_service import ConfigService

logger = logging.getLogger(__name__)


def _booking_service_module() -> ModuleType:
    from .. import booking_service as booking_service_module

    return booking_service_module


def _is_mock_like(value: object) -> bool:
    return type(value).__module__.startswith("unittest.mock")


def _stripe_service_class() -> Any:
    booking_service_module = _booking_service_module()
    from .. import stripe_service as stripe_service_module

    facade_cls = booking_service_module.StripeService
    source_cls = stripe_service_module.StripeService
    if _is_mock_like(facade_cls):
        return facade_cls
    if _is_mock_like(source_cls):
        return source_cls
    return facade_cls


class BookingRescheduleMixin:
    if TYPE_CHECKING:
        db: Session
        repository: BookingRepository
        config_service: ConfigService

        def transaction(self) -> ContextManager[None]:
            ...

        def log_operation(self, operation: str, **kwargs: Any) -> None:
            ...

        def _validate_min_session_duration_floor(self, selected_duration: int) -> None:
            ...

        def _calculate_and_validate_end_time(
            self,
            booking_date: Any,
            start_time: Any,
            selected_duration: int,
        ) -> Any:
            ...

        def _validate_against_availability_bits(
            self,
            booking_data: BookingCreate,
            instructor_profile: InstructorProfile,
        ) -> None:
            ...

        def _validate_booking_prerequisites(
            self,
            student: User,
            booking_data: BookingCreate,
        ) -> tuple[InstructorService, InstructorProfile]:
            ...

        def _acquire_booking_create_advisory_lock(
            self,
            instructor_id: str,
            booking_date: Any,
        ) -> None:
            ...

        def _check_conflicts_and_rules(
            self,
            booking_data: BookingCreate,
            service: InstructorService,
            instructor_profile: InstructorProfile,
            student: User,
        ) -> None:
            ...

        def _create_booking_record(
            self,
            student: User,
            booking_data: BookingCreate,
            service: InstructorService,
            instructor_profile: InstructorProfile,
            selected_duration: int,
        ) -> Booking:
            ...

        def _enqueue_booking_outbox_event(self, booking: Booking, event_type: str) -> None:
            ...

        def _snapshot_booking(self, booking: Booking) -> dict[str, Any]:
            ...

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
            ...

        def _get_booking_start_utc(self, booking: Booking) -> Any:
            ...

        def _build_conflict_details(
            self,
            booking_data: BookingCreate,
            student_id: str,
        ) -> dict[str, Any]:
            ...

        def _resolve_integrity_conflict_message(
            self,
            exc: IntegrityError,
        ) -> tuple[str, str | None]:
            ...

        def _is_deadlock_error(self, exc: OperationalError) -> bool:
            ...

        def _raise_conflict_from_repo_error(
            self,
            exc: RepositoryException,
            booking_data: BookingCreate,
            student_id: str,
        ) -> None:
            ...

        def _handle_post_booking_tasks(
            self,
            booking: Booking,
            is_reschedule: bool = False,
            old_booking: Optional[Booking] = None,
        ) -> None:
            ...

        def _cancel_booking_without_stripe_in_transaction(
            self,
            booking_id: str,
            user: User,
            reason: Optional[str] = None,
            *,
            clear_payment_intent: bool = False,
        ) -> tuple[Booking, str]:
            ...

        def _post_cancellation_actions(self, booking: Booking, cancelled_by_role: str) -> None:
            ...

        def check_availability(
            self,
            instructor_id: str,
            booking_date: Any,
            start_time: Any,
            end_time: Any,
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
            ...

        def get_booking_for_user(self, booking_id: str, user: User) -> Optional[Booking]:
            ...

        def get_hours_until_start(self, booking: Booking) -> float:
            ...

        def should_trigger_lock(self, booking: Booking, initiated_by: str) -> bool:
            ...

        def activate_lock_for_reschedule(self, booking_id: str) -> dict[str, Any]:
            ...

        def create_booking_with_payment_setup(
            self,
            student: User,
            booking_data: BookingCreate,
            selected_duration: int,
            old_booking_id: Optional[str] = None,
        ) -> Booking:
            ...

        def confirm_booking_payment(
            self,
            booking_id: str,
            student: User,
            payment_method_id: str,
            save_payment_method: bool = False,
        ) -> Booking:
            ...

        def cancel_booking(
            self,
            booking_id: str,
            user: User,
            reason: Optional[str] = None,
        ) -> Booking:
            ...

    def _validate_rescheduled_booking_inputs(
        self,
        student: User,
        booking_data: BookingCreate,
        selected_duration: int,
        original_booking_id: str,
    ) -> tuple[InstructorService, InstructorProfile, Booking]:
        """Validate the common inputs needed to create a replacement booking."""
        self._validate_min_session_duration_floor(selected_duration)

        existing_booking = self.repository.get_by_id(original_booking_id)
        if not existing_booking:
            raise NotFoundException("Original booking not found")
        if booking_data.instructor_id != existing_booking.instructor_id:
            raise BusinessRuleException(
                "Cannot change instructor during reschedule. Please cancel and create a new booking."
            )

        service, instructor_profile = self._validate_booking_prerequisites(student, booking_data)

        if selected_duration not in service.duration_options:
            raise BusinessRuleException(
                f"Invalid duration {selected_duration}. Available options: {service.duration_options}"
            )

        booking_data.end_time = self._calculate_and_validate_end_time(
            booking_data.booking_date,
            booking_data.start_time,
            selected_duration,
        )
        self._validate_against_availability_bits(booking_data, instructor_profile)
        return service, instructor_profile, existing_booking

    def _create_rescheduled_booking_base_in_transaction(
        self,
        student: User,
        booking_data: BookingCreate,
        selected_duration: int,
        original_booking_id: str,
        service: InstructorService,
        instructor_profile: InstructorProfile,
    ) -> tuple[Booking, Booking, Any, Any]:
        """Create a replacement booking and reschedule linkage inside an active transaction."""
        self._acquire_booking_create_advisory_lock(
            booking_data.instructor_id,
            booking_data.booking_date,
        )
        self._check_conflicts_and_rules(booking_data, service, instructor_profile, student)
        booking = self._create_booking_record(
            student, booking_data, service, instructor_profile, selected_duration
        )

        old_booking = self.repository.get_by_id(original_booking_id)
        if not old_booking:
            raise NotFoundException("Original booking not found")
        if booking_data.instructor_id != old_booking.instructor_id:
            raise BusinessRuleException(
                "Cannot change instructor during reschedule. Please cancel and create a new booking."
            )

        original_lesson_dt = self._get_booking_start_utc(old_booking)
        booking.rescheduled_from_booking_id = old_booking.id
        old_reschedule = self.repository.ensure_reschedule(old_booking.id)
        current_reschedule = self.repository.ensure_reschedule(booking.id)
        current_reschedule.original_lesson_datetime = original_lesson_dt
        old_reschedule.rescheduled_to_booking_id = booking.id
        previous_count = int(old_reschedule.reschedule_count or 0)
        new_count = previous_count + 1
        old_reschedule.reschedule_count = new_count
        current_reschedule.reschedule_count = new_count
        if bool(old_reschedule.late_reschedule_used):
            current_reschedule.late_reschedule_used = True

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

        return booking, old_booking, old_reschedule, current_reschedule

    def _apply_existing_payment_to_rescheduled_booking_in_transaction(
        self,
        booking: Booking,
        old_booking: Booking,
        *,
        payment_intent_id: str,
        payment_status: Optional[str],
        payment_method_id: Optional[str],
    ) -> None:
        """Copy reusable payment state from the original booking onto the replacement booking."""
        from ...repositories.payment_repository import PaymentRepository

        booking_service_module = _booking_service_module()

        bp = self.repository.ensure_payment(booking.id)
        bp.payment_intent_id = payment_intent_id
        if isinstance(payment_method_id, str):
            bp.payment_method_id = payment_method_id
        if isinstance(payment_status, str):
            bp.payment_status = payment_status

        try:
            credit_repo = booking_service_module.RepositoryFactory.create_credit_repository(self.db)
            reserved_credits = credit_repo.get_reserved_credits_for_booking(
                booking_id=old_booking.id
            )
            reserved_total = 0
            for credit in reserved_credits:
                reserved_total += int(credit.reserved_amount_cents or credit.amount_cents or 0)
                credit.reserved_for_booking_id = booking.id
            if reserved_total > 0:
                bp.credits_reserved_cents = reserved_total
                old_bp = self.repository.ensure_payment(old_booking.id)
                old_bp.credits_reserved_cents = 0
        except Exception as exc:
            logger.warning(
                "Failed to transfer reserved credits from booking %s: %s",
                old_booking.id,
                exc,
            )

        payment_repo = PaymentRepository(self.db)
        payment_record = payment_repo.get_payment_by_intent_id(payment_intent_id)
        if payment_record:
            payment_record.booking_id = booking.id

    def _apply_locked_funds_to_rescheduled_booking_in_transaction(
        self,
        booking: Booking,
        current_reschedule: Any,
    ) -> None:
        """Mark a replacement booking as carrying locked funds."""
        booking.has_locked_funds = True
        bp = self.repository.ensure_payment(booking.id)
        bp.payment_status = PaymentStatus.LOCKED.value
        current_reschedule.late_reschedule_used = True

    def _rollback_reschedule_replacement(self, booking: Booking, user: User) -> None:
        """Best-effort rollback of a replacement booking when the original cannot be cancelled."""
        try:
            if booking.status == BookingStatus.PENDING:
                if self.abort_pending_booking(booking.id):
                    return
            self.cancel_booking(
                booking.id,
                user,
                "Reschedule failed - replacement booking cancelled",
            )
        except Exception as exc:  # pragma: no cover - defensive failure path
            logger.critical(
                "Failed to rollback replacement booking %s after reschedule failure: %s",
                booking.id,
                exc,
                exc_info=True,
            )

    def _normalize_reschedule_location_type(self, original_booking: Booking) -> str:
        """Return a canonical location type for rescheduling the original booking."""
        booking_service_module = _booking_service_module()

        location_type_raw = getattr(original_booking, "location_type", None)
        if isinstance(location_type_raw, str):
            if location_type_raw in booking_service_module.VALID_LOCATION_TYPES:
                return location_type_raw
            raise ValidationException(
                f"Invalid location_type: '{location_type_raw}'. Must be one of: {', '.join(sorted(booking_service_module.VALID_LOCATION_TYPES))}"
            )
        return "online"

    def _build_reschedule_booking_data(
        self,
        original_booking: Booking,
        payload: BookingRescheduleRequest,
    ) -> BookingCreate:
        """Carry forward immutable booking fields into a replacement-booking payload."""
        location_type = self._normalize_reschedule_location_type(original_booking)
        student_note = (
            original_booking.student_note
            if isinstance(getattr(original_booking, "student_note", None), str)
            else None
        )
        meeting_location = (
            original_booking.meeting_location
            if isinstance(getattr(original_booking, "meeting_location", None), str)
            else None
        )

        return BookingCreate(
            instructor_id=original_booking.instructor_id,
            instructor_service_id=payload.instructor_service_id
            or original_booking.instructor_service_id,
            booking_date=payload.booking_date,
            start_time=payload.start_time,
            selected_duration=payload.selected_duration,
            student_note=student_note,
            meeting_location=meeting_location,
            location_type=location_type,
            location_address=_safe_str(getattr(original_booking, "location_address", None)),
            location_lat=_safe_float(getattr(original_booking, "location_lat", None)),
            location_lng=_safe_float(getattr(original_booking, "location_lng", None)),
            location_place_id=_safe_str(getattr(original_booking, "location_place_id", None)),
        )

    def _ensure_reschedule_slot_available(
        self,
        *,
        original_booking: Booking,
        booking_data: BookingCreate,
        selected_duration: int,
        student_id: str,
    ) -> None:
        """Validate the proposed replacement slot before any payment or cancellation work."""
        booking_service_module = _booking_service_module()

        proposed_start = booking_service_module.datetime.combine(
            booking_data.booking_date,
            booking_data.start_time,
            tzinfo=booking_service_module.timezone.utc,
        )
        proposed_end_time = (
            proposed_start + booking_service_module.timedelta(minutes=selected_duration)
        ).time()

        availability = self.check_availability(
            instructor_id=original_booking.instructor_id,
            booking_date=booking_data.booking_date,
            start_time=booking_data.start_time,
            end_time=proposed_end_time,
            service_id=booking_data.instructor_service_id,
            instructor_service_id=None,
            exclude_booking_id=original_booking.id,
            location_type=booking_data.location_type,
            student_id=student_id,
            selected_duration=selected_duration,
            location_lat=booking_data.location_lat,
            location_lng=booking_data.location_lng,
        )

        if isinstance(availability, dict):
            is_available = availability.get("available", False)
            reason = availability.get("reason")
        else:
            try:
                is_available = bool(availability)
            except Exception:
                is_available = False
            reason = None

        if not is_available:
            raise BookingConflictException(message=reason or "Requested time is unavailable")

    def _resolve_reschedule_student(self, original_booking: Booking) -> User:
        """Return the canonical student for a reschedule, even if the actor is different."""
        booking_service_module = _booking_service_module()

        student = getattr(original_booking, "student", None)
        if student is not None and str(getattr(student, "id", "")) == str(
            original_booking.student_id
        ):
            return cast(User, student)

        user_repository = booking_service_module.RepositoryFactory.create_user_repository(self.db)
        resolved_student = user_repository.get_by_id(original_booking.student_id)
        if not resolved_student:
            raise NotFoundException("Student not found")
        return cast(User, resolved_student)

    def _create_rescheduled_booking_with_existing_payment_in_transaction(
        self,
        *,
        student: User,
        booking_data: BookingCreate,
        selected_duration: int,
        original_booking_id: str,
        service: InstructorService,
        instructor_profile: InstructorProfile,
        payment_intent_id: str,
        payment_status: Optional[str],
        payment_method_id: Optional[str],
    ) -> tuple[Booking, Booking]:
        """Create a replacement booking and copy the original payment within an open transaction."""
        (
            booking,
            old_booking,
            _old_reschedule,
            _current_reschedule,
        ) = self._create_rescheduled_booking_base_in_transaction(
            student,
            booking_data,
            selected_duration,
            original_booking_id,
            service,
            instructor_profile,
        )
        self._apply_existing_payment_to_rescheduled_booking_in_transaction(
            booking,
            old_booking,
            payment_intent_id=payment_intent_id,
            payment_status=payment_status,
            payment_method_id=payment_method_id,
        )
        return booking, old_booking

    def _create_rescheduled_booking_with_locked_funds_in_transaction(
        self,
        *,
        student: User,
        booking_data: BookingCreate,
        selected_duration: int,
        original_booking_id: str,
        service: InstructorService,
        instructor_profile: InstructorProfile,
    ) -> tuple[Booking, Booking]:
        """Create a replacement booking that inherits a reschedule lock within an open transaction."""
        (
            booking,
            old_booking,
            _old_reschedule,
            current_reschedule,
        ) = self._create_rescheduled_booking_base_in_transaction(
            student,
            booking_data,
            selected_duration,
            original_booking_id,
            service,
            instructor_profile,
        )
        self._apply_locked_funds_to_rescheduled_booking_in_transaction(booking, current_reschedule)
        return booking, old_booking

    @BaseService.measure_operation("reschedule_booking")
    def reschedule_booking(
        self,
        *,
        booking_id: str,
        payload: BookingRescheduleRequest,
        current_user: User,
    ) -> Booking:
        """Reschedule a booking while keeping cancellation and replacement creation consistent."""
        original_booking = self.get_booking_for_user(booking_id, current_user)
        if not original_booking:
            raise NotFoundException("Booking not found")

        self.validate_reschedule_allowed(original_booking)
        reschedule_student = self._resolve_reschedule_student(original_booking)

        new_booking_data = self._build_reschedule_booking_data(original_booking, payload)
        self._ensure_reschedule_slot_available(
            original_booking=original_booking,
            booking_data=new_booking_data,
            selected_duration=payload.selected_duration,
            student_id=str(reschedule_student.id),
        )

        payment_detail = original_booking.payment_detail
        raw_payment_intent_id = payment_detail.payment_intent_id if payment_detail else None
        raw_payment_status = payment_detail.payment_status if payment_detail else None
        raw_payment_method_id = payment_detail.payment_method_id if payment_detail else None

        normalized_payment_status = raw_payment_status
        if raw_payment_status == "requires_capture":
            normalized_payment_status = PaymentStatus.AUTHORIZED.value
        elif raw_payment_status == "succeeded":
            normalized_payment_status = PaymentStatus.SETTLED.value

        reuse_payment = (
            isinstance(raw_payment_intent_id, str)
            and raw_payment_intent_id.startswith("pi_")
            and isinstance(normalized_payment_status, str)
            and normalized_payment_status
            in {PaymentStatus.AUTHORIZED.value, PaymentStatus.SETTLED.value}
        )

        initiator_role = (
            "student" if current_user.id == original_booking.student_id else "instructor"
        )
        hours_until_original = self.get_hours_until_start(original_booking)
        should_lock = self.should_trigger_lock(original_booking, initiator_role)
        force_stripe_cancel = initiator_role == "student" and hours_until_original < 12

        if should_lock:
            self.activate_lock_for_reschedule(original_booking.id)
            return self._reschedule_with_lock(
                original_booking=original_booking,
                booking_data=new_booking_data,
                selected_duration=payload.selected_duration,
                current_user=current_user,
                reschedule_student=reschedule_student,
            )

        if reuse_payment and not force_stripe_cancel:
            return self._reschedule_with_existing_payment(
                original_booking=original_booking,
                booking_data=new_booking_data,
                selected_duration=payload.selected_duration,
                current_user=current_user,
                reschedule_student=reschedule_student,
                payment_intent_id=cast(str, raw_payment_intent_id),
                payment_status=cast(Optional[str], normalized_payment_status),
                payment_method_id=cast(Optional[str], raw_payment_method_id),
            )

        return self._reschedule_with_new_payment(
            original_booking=original_booking,
            booking_data=new_booking_data,
            selected_duration=payload.selected_duration,
            current_user=current_user,
            reschedule_student=reschedule_student,
        )

    def _reschedule_with_lock(
        self,
        *,
        original_booking: Booking,
        booking_data: BookingCreate,
        selected_duration: int,
        current_user: User,
        reschedule_student: User,
    ) -> Booking:
        """Handle the LOCK reschedule path with one transaction for create + cancel."""
        booking_service_module = _booking_service_module()

        service, instructor_profile, _ = self._validate_rescheduled_booking_inputs(
            reschedule_student,
            booking_data,
            selected_duration,
            original_booking.id,
        )
        transactional_repo = cast(Any, self.repository)
        old_booking: Optional[Booking] = None
        try:
            with transactional_repo.transaction():
                (
                    replacement_booking,
                    old_booking,
                ) = self._create_rescheduled_booking_with_locked_funds_in_transaction(
                    student=reschedule_student,
                    booking_data=booking_data,
                    selected_duration=selected_duration,
                    original_booking_id=original_booking.id,
                    service=service,
                    instructor_profile=instructor_profile,
                )
                (
                    cancelled_booking,
                    cancelled_by_role,
                ) = self._cancel_booking_without_stripe_in_transaction(
                    original_booking.id,
                    current_user,
                    "Rescheduled",
                )
        except IntegrityError as exc:
            message, scope = self._resolve_integrity_conflict_message(exc)
            conflict_details = self._build_conflict_details(
                booking_data, str(reschedule_student.id)
            )
            if scope:
                conflict_details["conflict_scope"] = scope
            raise BookingConflictException(
                message=message,
                details=conflict_details,
            ) from exc
        except OperationalError as exc:
            if self._is_deadlock_error(exc):
                conflict_details = self._build_conflict_details(
                    booking_data, str(reschedule_student.id)
                )
                raise BookingConflictException(
                    message=booking_service_module.GENERIC_CONFLICT_MESSAGE,
                    details=conflict_details,
                ) from exc
            raise
        except RepositoryException as exc:
            self._raise_conflict_from_repo_error(exc, booking_data, str(reschedule_student.id))

        self._handle_post_booking_tasks(
            replacement_booking,
            is_reschedule=old_booking is not None,
            old_booking=old_booking,
        )
        self._post_cancellation_actions(cancelled_booking, cancelled_by_role)
        return replacement_booking

    def _reschedule_with_existing_payment(
        self,
        *,
        original_booking: Booking,
        booking_data: BookingCreate,
        selected_duration: int,
        current_user: User,
        reschedule_student: User,
        payment_intent_id: str,
        payment_status: Optional[str],
        payment_method_id: Optional[str],
    ) -> Booking:
        """Handle the payment-reuse reschedule path with one transaction for create + cancel."""
        booking_service_module = _booking_service_module()

        service, instructor_profile, _ = self._validate_rescheduled_booking_inputs(
            reschedule_student,
            booking_data,
            selected_duration,
            original_booking.id,
        )
        transactional_repo = cast(Any, self.repository)
        old_booking: Optional[Booking] = None
        try:
            with transactional_repo.transaction():
                (
                    replacement_booking,
                    old_booking,
                ) = self._create_rescheduled_booking_with_existing_payment_in_transaction(
                    student=reschedule_student,
                    booking_data=booking_data,
                    selected_duration=selected_duration,
                    original_booking_id=original_booking.id,
                    service=service,
                    instructor_profile=instructor_profile,
                    payment_intent_id=payment_intent_id,
                    payment_status=payment_status,
                    payment_method_id=payment_method_id,
                )
                (
                    cancelled_booking,
                    cancelled_by_role,
                ) = self._cancel_booking_without_stripe_in_transaction(
                    original_booking.id,
                    current_user,
                    "Rescheduled",
                    clear_payment_intent=True,
                )
        except IntegrityError as exc:
            message, scope = self._resolve_integrity_conflict_message(exc)
            conflict_details = self._build_conflict_details(
                booking_data, str(reschedule_student.id)
            )
            if scope:
                conflict_details["conflict_scope"] = scope
            raise BookingConflictException(
                message=message,
                details=conflict_details,
            ) from exc
        except OperationalError as exc:
            if self._is_deadlock_error(exc):
                conflict_details = self._build_conflict_details(
                    booking_data, str(reschedule_student.id)
                )
                raise BookingConflictException(
                    message=booking_service_module.GENERIC_CONFLICT_MESSAGE,
                    details=conflict_details,
                ) from exc
            raise
        except RepositoryException as exc:
            self._raise_conflict_from_repo_error(exc, booking_data, str(reschedule_student.id))

        self._handle_post_booking_tasks(
            replacement_booking,
            is_reschedule=old_booking is not None,
            old_booking=old_booking,
        )
        self._post_cancellation_actions(cancelled_booking, cancelled_by_role)
        return replacement_booking

    def _reschedule_with_new_payment(
        self,
        *,
        original_booking: Booking,
        booking_data: BookingCreate,
        selected_duration: int,
        current_user: User,
        reschedule_student: User,
    ) -> Booking:
        """Handle the new-payment reschedule path with compensation if the original cancel fails."""
        has_payment_method, stripe_payment_method_id = self.validate_reschedule_payment_method(
            str(reschedule_student.id)
        )
        if not has_payment_method or not stripe_payment_method_id:
            raise ValidationException(
                "A payment method is required to reschedule this lesson. Please add a payment method and try again.",
                code="payment_method_required_for_reschedule",
            )

        replacement_booking = self.create_booking_with_payment_setup(
            reschedule_student,
            booking_data,
            selected_duration,
            original_booking.id,
        )

        try:
            replacement_booking = self.confirm_booking_payment(
                replacement_booking.id,
                reschedule_student,
                stripe_payment_method_id,
                False,
            )
        except Exception as exc:
            logger.error(
                "Failed to confirm payment for rescheduled booking %s: %s",
                replacement_booking.id,
                exc,
            )
            self.abort_pending_booking(replacement_booking.id)
            raise ValidationException(
                "We couldn't process your payment method. Please try again or update your payment method.",
                code="payment_confirmation_failed",
            ) from exc

        try:
            self.cancel_booking(original_booking.id, current_user, "Rescheduled")
        except Exception as exc:
            logger.critical(
                "Failed to cancel original booking %s after creating replacement booking %s during reschedule: %s",
                original_booking.id,
                replacement_booking.id,
                exc,
                exc_info=True,
            )
            self._rollback_reschedule_replacement(replacement_booking, current_user)
            raise

        return replacement_booking

    @BaseService.measure_operation("create_rescheduled_booking_with_existing_payment")
    def create_rescheduled_booking_with_existing_payment(
        self,
        student: User,
        booking_data: BookingCreate,
        selected_duration: int,
        original_booking_id: str,
        payment_intent_id: str,
        payment_status: Optional[str],
        payment_method_id: Optional[str],
    ) -> Booking:
        """
        Create a rescheduled booking that reuses an existing PaymentIntent.

        This avoids creating a new PaymentIntent when the original payment was
        already authorized or captured.
        """
        booking_service_module = _booking_service_module()

        self.log_operation(
            "create_rescheduled_booking_with_existing_payment",
            student_id=student.id,
            instructor_id=booking_data.instructor_id,
            date=booking_data.booking_date,
            original_booking_id=original_booking_id,
        )
        service, instructor_profile, _ = self._validate_rescheduled_booking_inputs(
            student,
            booking_data,
            selected_duration,
            original_booking_id,
        )

        transactional_repo = cast(Any, self.repository)
        old_booking: Optional[Booking] = None
        try:
            with transactional_repo.transaction():
                (
                    booking,
                    old_booking,
                ) = self._create_rescheduled_booking_with_existing_payment_in_transaction(
                    student=student,
                    booking_data=booking_data,
                    selected_duration=selected_duration,
                    original_booking_id=original_booking_id,
                    service=service,
                    instructor_profile=instructor_profile,
                    payment_intent_id=payment_intent_id,
                    payment_status=payment_status,
                    payment_method_id=payment_method_id,
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
                    message=booking_service_module.GENERIC_CONFLICT_MESSAGE,
                    details=conflict_details,
                ) from exc
            raise
        except RepositoryException as exc:
            self._raise_conflict_from_repo_error(exc, booking_data, student.id)

        self._handle_post_booking_tasks(
            booking,
            is_reschedule=old_booking is not None,
            old_booking=old_booking,
        )

        return booking

    @BaseService.measure_operation("create_rescheduled_booking_with_locked_funds")
    def create_rescheduled_booking_with_locked_funds(
        self,
        student: User,
        booking_data: BookingCreate,
        selected_duration: int,
        original_booking_id: str,
    ) -> Booking:
        """
        Create a rescheduled booking when LOCK is active.

        The new booking carries a has_locked_funds flag and does not reuse
        the original payment intent.
        """
        booking_service_module = _booking_service_module()

        self.log_operation(
            "create_rescheduled_booking_with_locked_funds",
            student_id=student.id,
            instructor_id=booking_data.instructor_id,
            date=booking_data.booking_date,
            original_booking_id=original_booking_id,
        )
        service, instructor_profile, _ = self._validate_rescheduled_booking_inputs(
            student,
            booking_data,
            selected_duration,
            original_booking_id,
        )

        transactional_repo = cast(Any, self.repository)
        old_booking: Optional[Booking] = None
        try:
            with transactional_repo.transaction():
                (
                    booking,
                    old_booking,
                ) = self._create_rescheduled_booking_with_locked_funds_in_transaction(
                    student=student,
                    booking_data=booking_data,
                    selected_duration=selected_duration,
                    original_booking_id=original_booking_id,
                    service=service,
                    instructor_profile=instructor_profile,
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
                    message=booking_service_module.GENERIC_CONFLICT_MESSAGE,
                    details=conflict_details,
                ) from exc
            raise
        except RepositoryException as exc:
            self._raise_conflict_from_repo_error(exc, booking_data, student.id)

        self._handle_post_booking_tasks(
            booking,
            is_reschedule=old_booking is not None,
            old_booking=old_booking,
        )

        return booking

    @BaseService.measure_operation("validate_reschedule_allowed")
    def validate_reschedule_allowed(self, booking: Booking) -> None:
        """
        Validate that a booking can be rescheduled (v2.1.1 rules).

        Rules:
        - Reschedule blocked when <12h before lesson
        - Exactly one late reschedule allowed in 12-24h window (late_reschedule_used)
        - Unlimited reschedules when >=24h
        - Locked bookings cannot be rescheduled

        Args:
            booking: The booking to validate

        Raises:
            BusinessRuleException: If booking has already been rescheduled once
        """
        if getattr(booking.payment_detail, "payment_status", None) == PaymentStatus.LOCKED.value:
            raise BusinessRuleException(
                message="This booking has locked funds and cannot be rescheduled.",
                code="reschedule_locked",
            )

        hours_until_start = self.get_hours_until_start(booking)
        if hours_until_start < 12:
            raise BusinessRuleException(
                message=(
                    "Cannot reschedule within 12 hours of lesson start. "
                    "Please cancel if you cannot attend."
                ),
                code="reschedule_window_closed",
            )

        reschedule_record = self.repository.get_reschedule_by_booking_id(booking.id)
        if bool(reschedule_record and reschedule_record.late_reschedule_used):
            raise BusinessRuleException(
                message=(
                    "You've already used your late reschedule for this booking. "
                    "Please cancel and book a new lesson."
                ),
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
        booking_service_module = _booking_service_module()

        pricing_service = booking_service_module.PricingService(self.db)
        stripe_service = _stripe_service_class()(
            self.db,
            config_service=self.config_service,
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

            if booking.status != BookingStatus.PENDING:
                logger.warning(
                    "Cannot abort booking %s - status is %s, not pending_payment",
                    booking_id,
                    booking.status,
                )
                return False

            with self.transaction():
                self.repository.delete(booking.id)

            logger.info("Aborted pending booking %s", booking_id)
            return True
        except Exception as e:
            logger.error("Failed to abort pending booking %s: %s", booking_id, e)
            return False
