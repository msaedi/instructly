from __future__ import annotations

import logging
from types import ModuleType
from typing import TYPE_CHECKING, Any, Dict, Optional, cast

from ...core.exceptions import (
    BookingConflictException,
    BusinessRuleException,
    NotFoundException,
    ValidationException,
)
from ...models.booking import Booking, PaymentStatus
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

        def check_availability(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
            ...

        def get_booking_for_user(self, booking_id: str, user: User) -> Optional[Booking]:
            ...

        def get_hours_until_start(self, booking: Booking) -> float:
            ...

        def should_trigger_lock(self, booking: Booking, initiated_by: str) -> bool:
            ...

        def activate_lock_for_reschedule(self, booking_id: str) -> dict[str, Any]:
            ...

        def _reschedule_with_lock(self, *args: Any, **kwargs: Any) -> Booking:
            ...

        def _reschedule_with_existing_payment(self, *args: Any, **kwargs: Any) -> Booking:
            ...

        def _rollback_reschedule_replacement(self, booking: Booking, user: User) -> None:
            ...

        def abort_pending_booking(self, booking_id: str) -> bool:
            ...

        def create_booking_with_payment_setup(self, *args: Any, **kwargs: Any) -> Booking:
            ...

        def confirm_booking_payment(self, *args: Any, **kwargs: Any) -> Booking:
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

    @BaseService.measure_operation("validate_reschedule_allowed")
    def validate_reschedule_allowed(self, booking: Booking) -> None:
        """Validate that a booking can be rescheduled (v2.1.1 rules)."""
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
        """Validate that user has a valid payment method for rescheduling."""
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
