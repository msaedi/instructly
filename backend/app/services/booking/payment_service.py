from __future__ import annotations

import logging
from types import ModuleType
from typing import TYPE_CHECKING, Any, ContextManager, Dict, Optional

from ...core.exceptions import (
    BusinessRuleException,
    ForbiddenException,
    NotFoundException,
    ValidationException,
)
from ...models.booking import Booking, BookingStatus, PaymentStatus
from ...models.user import User
from ..base import BaseService

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from ...repositories.booking_repository import BookingRepository
    from ..config_service import ConfigService
    from ..system_message_service import SystemMessageService

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


class BookingPaymentMixin:
    if TYPE_CHECKING:
        db: Session
        repository: BookingRepository
        config_service: ConfigService
        system_message_service: SystemMessageService

        def transaction(self) -> ContextManager[None]:
            ...

        def log_operation(self, operation: str, **kwargs: Any) -> None:
            ...

        def _get_booking_start_utc(self, booking: Booking) -> Any:
            ...

        def _invalidate_booking_caches(self, booking: Booking) -> None:
            ...

    def _determine_auth_timing(self, lesson_start_at: Any) -> Dict[str, Any]:
        """
        Determine authorization timing based on lesson start time.

        Returns:
            {
                "immediate": bool,
                "scheduled_for": datetime | None,
                "initial_payment_status": str,
                "hours_until_lesson": float,
            }
        """
        booking_service_module = _booking_service_module()

        if lesson_start_at.tzinfo is None:
            lesson_start_at = lesson_start_at.replace(tzinfo=booking_service_module.timezone.utc)
        now = booking_service_module.datetime.now(booking_service_module.timezone.utc)
        hours_until_lesson = (lesson_start_at - now).total_seconds() / 3600

        if hours_until_lesson >= 24:
            scheduled_for = lesson_start_at - booking_service_module.timedelta(hours=24)
            return {
                "immediate": False,
                "scheduled_for": scheduled_for,
                "initial_payment_status": PaymentStatus.SCHEDULED.value,
                "hours_until_lesson": hours_until_lesson,
            }

        return {
            "immediate": True,
            "scheduled_for": None,
            "initial_payment_status": PaymentStatus.SCHEDULED.value,
            "hours_until_lesson": hours_until_lesson,
        }

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
        from ...repositories.payment_repository import PaymentRepository

        booking_service_module = _booking_service_module()

        self.log_operation("confirm_booking_payment", booking_id=booking_id, student_id=student.id)

        # Defense-in-depth: filter by student at DB level (AUTHZ-VULN-01)
        booking = self.repository.get_booking_for_student(booking_id, student.id)
        if not booking:
            raise NotFoundException("Booking not found")

        if booking.status != BookingStatus.PENDING:
            raise NotFoundException("Booking not found")

        trigger_immediate_auth = False
        immediate_auth_hours_until: Optional[float] = None

        # Save payment method for future use (Stripe call should be outside DB transaction)
        if save_payment_method:
            stripe_service = _stripe_service_class()(
                self.db,
                config_service=self.config_service,
                pricing_service=booking_service_module.PricingService(self.db),
            )
            stripe_service.save_payment_method(
                user_id=student.id, payment_method_id=payment_method_id, set_as_default=False
            )

        with self.transaction():
            # Save payment method
            bp = self.repository.ensure_payment(booking.id)
            bp.payment_method_id = payment_method_id
            bp.payment_status = PaymentStatus.SCHEDULED.value

            # Phase 2.2: Schedule authorization based on lesson timing (UTC)
            booking_start_utc = self._get_booking_start_utc(booking)
            auth_timing = self._determine_auth_timing(booking_start_utc)
            hours_until_lesson = auth_timing["hours_until_lesson"]

            is_gaming_reschedule = False
            hours_from_original: Optional[float] = None
            reschedule_record = self.repository.get_reschedule_by_booking_id(booking.id)
            original_lesson_datetime = (
                reschedule_record.original_lesson_datetime if reschedule_record else None
            )
            if booking.rescheduled_from_booking_id and original_lesson_datetime:
                original_dt = original_lesson_datetime
                if original_dt.tzinfo is None:
                    original_dt = original_dt.replace(tzinfo=booking_service_module.timezone.utc)
                reschedule_time = booking.created_at
                if reschedule_time is not None:
                    if reschedule_time.tzinfo is None:
                        reschedule_time = reschedule_time.replace(
                            tzinfo=booking_service_module.timezone.utc
                        )
                    hours_from_original_value = (
                        original_dt - reschedule_time
                    ).total_seconds() / 3600
                    hours_from_original = hours_from_original_value
                    is_gaming_reschedule = hours_from_original_value < 24

            if is_gaming_reschedule:
                # Gaming reschedule: authorize immediately to prevent delayed-auth loophole.
                bp.payment_status = PaymentStatus.SCHEDULED.value
                bp.auth_scheduled_for = booking_service_module.datetime.now(
                    booking_service_module.timezone.utc
                )
                bp.auth_last_error = None
                bp.auth_failure_count = 0
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

            elif auth_timing["immediate"]:
                # Lesson is within 24 hours - mark for immediate authorization by background task
                bp.payment_status = PaymentStatus.SCHEDULED.value
                bp.auth_scheduled_for = booking_service_module.datetime.now(
                    booking_service_module.timezone.utc
                )
                bp.auth_last_error = None
                bp.auth_failure_count = 0

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
                trigger_immediate_auth = True
                immediate_auth_hours_until = hours_until_lesson

            else:
                # Lesson is >24 hours away - schedule authorization
                auth_time = auth_timing["scheduled_for"]
                bp.payment_status = PaymentStatus.SCHEDULED.value
                bp.auth_scheduled_for = auth_time
                bp.auth_last_error = None
                bp.auth_failure_count = 0

                # Create scheduled event using repository
                payment_repo = PaymentRepository(self.db)
                payment_repo.create_payment_event(
                    booking_id=booking.id,
                    event_type="auth_scheduled",
                    event_data={
                        "payment_method_id": payment_method_id,
                        "scheduled_for": auth_time.isoformat() if auth_time else None,
                        "hours_until_lesson": hours_until_lesson,
                    },
                )

            # Update booking status to CONFIRMED only when auth is scheduled (>24h)
            # For immediate auth (<24h), confirmation happens after successful authorization.
            if not trigger_immediate_auth:
                booking.status = BookingStatus.CONFIRMED
                booking.confirmed_at = booking_service_module.datetime.now(
                    booking_service_module.timezone.utc
                )
            else:
                booking.status = BookingStatus.PENDING
                booking.confirmed_at = None

            # Transaction handles flush/commit automatically

        self.log_operation(
            "confirm_booking_payment_completed",
            booking_id=booking.id,
            payment_status=getattr(booking.payment_detail, "payment_status", None),
        )

        auth_result: Optional[Dict[str, Any]] = None
        if trigger_immediate_auth:
            try:
                from app.tasks.payment_tasks import _process_authorization_for_booking

                auth_result = _process_authorization_for_booking(
                    booking.id, immediate_auth_hours_until or 0.0
                )
                if not auth_result or not auth_result.get("success"):
                    logger.warning(
                        "Immediate auth failed for gaming reschedule booking %s: %s",
                        booking.id,
                        auth_result.get("error") if auth_result else "unknown error",
                    )
            except Exception as exc:
                logger.error(
                    "Immediate auth error for gaming reschedule booking %s: %s",
                    booking.id,
                    exc,
                )

        if auth_result and auth_result.get("success"):
            try:
                with self.transaction():
                    refreshed = self.repository.get_by_id(booking.id)
                    if refreshed and refreshed.status == BookingStatus.PENDING:
                        refreshed.status = BookingStatus.CONFIRMED
                        refreshed.confirmed_at = booking_service_module.datetime.now(
                            booking_service_module.timezone.utc
                        )
                        refreshed_bp = self.repository.ensure_payment(refreshed.id)
                        if refreshed_bp.payment_status == PaymentStatus.SCHEDULED.value:
                            refreshed_bp.payment_status = PaymentStatus.AUTHORIZED.value
                self.repository.refresh(booking)
            except Exception:
                logger.warning(
                    "Booking %s was updated after immediate authorization, but ORM refresh failed",
                    booking.id,
                    exc_info=True,
                )
        elif trigger_immediate_auth:
            try:
                self.repository.refresh(booking)
            except Exception:
                logger.warning(
                    "Failed to refresh booking %s after immediate authorization attempt",
                    booking.id,
                    exc_info=True,
                )
        # Create system message in conversation only after confirmation
        if booking.status != BookingStatus.CONFIRMED:
            return booking

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
            logger.error("Failed to create system message for booking %s: %s", booking.id, str(e))

        # Invalidate caches so upcoming lists include the newly confirmed booking
        try:
            self._invalidate_booking_caches(booking)
        except Exception:
            # Side-effect only — does not affect booking state.
            logger.debug(
                "Failed to invalidate booking caches after confirmation for booking %s",
                booking.id,
                exc_info=True,
            )
        return booking

    @BaseService.measure_operation("retry_authorization")
    def retry_authorization(self, *, booking_id: str, user: User) -> Dict[str, Any]:
        """
        Retry payment authorization for a booking after failure.
        """
        from ...repositories.payment_repository import PaymentRepository

        booking_service_module = _booking_service_module()

        booking = self.repository.get_booking_with_details(booking_id)
        if not booking:
            raise NotFoundException("Booking not found")

        if booking.student_id != user.id:
            raise ForbiddenException("Only the student can retry payment authorization")

        if booking.status == BookingStatus.CANCELLED:
            raise BusinessRuleException("Booking has been cancelled")

        pd = booking.payment_detail
        cur_payment_status = pd.payment_status if pd is not None else None
        if cur_payment_status not in {
            PaymentStatus.PAYMENT_METHOD_REQUIRED.value,
            PaymentStatus.SCHEDULED.value,
        }:
            raise BusinessRuleException(f"Cannot retry payment in status: {cur_payment_status}")

        payment_repo = PaymentRepository(self.db)
        default_method = payment_repo.get_default_payment_method(user.id)
        payment_method_id = (
            default_method.stripe_payment_method_id
            if default_method and default_method.stripe_payment_method_id
            else (pd.payment_method_id if pd is not None else None)
        )

        if not payment_method_id:
            raise ValidationException("No payment method available for retry")

        stripe_service = _stripe_service_class()(
            self.db,
            config_service=self.config_service,
            pricing_service=booking_service_module.PricingService(self.db),
        )

        ctx = stripe_service.build_charge_context(
            booking_id=booking.id, requested_credit_cents=None
        )

        now = booking_service_module.datetime.now(booking_service_module.timezone.utc)
        if ctx.student_pay_cents <= 0:
            with self.transaction():
                booking = self.repository.get_booking_with_details(booking_id)
                if not booking:
                    raise NotFoundException("Booking not found")
                bp = self.repository.ensure_payment(booking.id)
                bp.payment_status = PaymentStatus.AUTHORIZED.value
                bp.auth_attempted_at = now
                bp.auth_failure_count = 0
                bp.auth_last_error = None
                bp.payment_method_id = payment_method_id

                payment_repo.create_payment_event(
                    booking_id=booking.id,
                    event_type="auth_retry_succeeded",
                    event_data={
                        "credits_applied_cents": ctx.applied_credit_cents,
                        "authorized_at": now.isoformat(),
                    },
                )

            return {
                "success": True,
                "payment_status": PaymentStatus.AUTHORIZED.value,
                "failure_count": 0,
            }

        pd_for_pi = booking.payment_detail
        raw_pi_id = pd_for_pi.payment_intent_id if pd_for_pi is not None else None
        payment_intent_id = (
            raw_pi_id if isinstance(raw_pi_id, str) and raw_pi_id.startswith("pi_") else None
        )

        stripe_error: Optional[str] = None
        stripe_status: Optional[str] = None
        try:
            if payment_intent_id:
                payment_record = stripe_service.confirm_payment_intent(
                    payment_intent_id, payment_method_id
                )
                stripe_status = getattr(payment_record, "status", None)
            else:
                payment_intent = stripe_service.create_or_retry_booking_payment_intent(
                    booking_id=booking.id,
                    payment_method_id=payment_method_id,
                    requested_credit_cents=None,
                )
                payment_intent_id = getattr(payment_intent, "id", None)
                stripe_status = getattr(payment_intent, "status", None)
        except Exception as exc:
            stripe_error = str(exc)

        success = stripe_status in {"requires_capture", "succeeded"}
        with self.transaction():
            booking = self.repository.get_booking_with_details(booking_id)
            if not booking:
                raise NotFoundException("Booking not found")

            bp = self.repository.ensure_payment(booking.id)
            bp.payment_method_id = payment_method_id
            bp.auth_attempted_at = now
            bp.auth_scheduled_for = None

            if success:
                bp.payment_status = PaymentStatus.AUTHORIZED.value
                bp.payment_intent_id = payment_intent_id
                bp.auth_failure_count = 0
                bp.auth_last_error = None
                payment_repo.create_payment_event(
                    booking_id=booking.id,
                    event_type="auth_retry_succeeded",
                    event_data={
                        "payment_intent_id": payment_intent_id,
                        "authorized_at": now.isoformat(),
                        "amount_cents": ctx.student_pay_cents,
                        "application_fee_cents": ctx.application_fee_cents,
                    },
                )
            else:
                bp.payment_status = PaymentStatus.PAYMENT_METHOD_REQUIRED.value
                bp.auth_failure_count = int(bp.auth_failure_count or 0) + 1
                bp.auth_last_error = stripe_error or stripe_status or "authorization_failed"
                payment_repo.create_payment_event(
                    booking_id=booking.id,
                    event_type="auth_retry_failed",
                    event_data={
                        "payment_intent_id": payment_intent_id,
                        "error": bp.auth_last_error,
                        "failed_at": now.isoformat(),
                    },
                )

        return {
            "success": success,
            "payment_status": bp.payment_status,
            "failure_count": bp.auth_failure_count,
            "error": None if success else bp.auth_last_error,
        }
