from __future__ import annotations

import logging
from types import ModuleType
from typing import TYPE_CHECKING, Any, ContextManager, Dict, Optional, cast

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


class BookingPaymentRetryMixin:
    if TYPE_CHECKING:
        db: Session
        repository: BookingRepository
        config_service: ConfigService

        def transaction(self) -> ContextManager[None]:
            ...

    @BaseService.measure_operation("retry_authorization")
    def retry_authorization(self, *, booking_id: str, user: User) -> Dict[str, Any]:
        """Retry payment authorization for a booking after failure."""
        from ...repositories.payment_repository import PaymentRepository

        booking_service_module = _booking_service_module()
        payment_repo = PaymentRepository(self.db)
        booking = self._load_retry_authorization_context(booking_id, user)
        payment_method_id = self._resolve_retry_payment_method(payment_repo, user.id, booking)
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
            return self._authorize_zero_amount_retry(
                booking_id=booking_id,
                payment_repo=payment_repo,
                payment_method_id=payment_method_id,
                ctx=ctx,
                now=now,
            )

        stripe_outcome = self._execute_retry_authorization_stripe_step(
            booking=booking,
            payment_method_id=payment_method_id,
            stripe_service=stripe_service,
        )
        return self._persist_retry_authorization_result(
            booking_id=booking_id,
            payment_repo=payment_repo,
            payment_method_id=payment_method_id,
            ctx=ctx,
            now=now,
            stripe_outcome=stripe_outcome,
        )

    def _load_retry_authorization_context(self, booking_id: str, user: User) -> Booking:
        booking = self.repository.get_booking_with_details(booking_id)
        if not booking:
            raise NotFoundException("Booking not found")
        if booking.student_id != user.id:
            raise ForbiddenException("Only the student can retry payment authorization")
        if booking.status == BookingStatus.CANCELLED:
            raise BusinessRuleException("Booking has been cancelled")
        if booking.status == BookingStatus.PAYMENT_FAILED:
            raise BusinessRuleException("Booking payment has already failed")
        pd = booking.payment_detail
        cur_payment_status = pd.payment_status if pd is not None else None
        if cur_payment_status not in {
            PaymentStatus.PAYMENT_METHOD_REQUIRED.value,
            PaymentStatus.SCHEDULED.value,
        }:
            raise BusinessRuleException(f"Cannot retry payment in status: {cur_payment_status}")
        return booking

    def _resolve_retry_payment_method(
        self,
        payment_repo: Any,
        user_id: str,
        booking: Booking,
    ) -> str:
        pd = booking.payment_detail
        default_method = payment_repo.get_default_payment_method(user_id)
        payment_method_id = (
            default_method.stripe_payment_method_id
            if default_method and default_method.stripe_payment_method_id
            else (pd.payment_method_id if pd is not None else None)
        )
        if not payment_method_id:
            raise ValidationException("No payment method available for retry")
        return cast(str, payment_method_id)

    def _authorize_zero_amount_retry(
        self,
        *,
        booking_id: str,
        payment_repo: Any,
        payment_method_id: str,
        ctx: Any,
        now: Any,
    ) -> Dict[str, Any]:
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

    def _execute_retry_authorization_stripe_step(
        self,
        *,
        booking: Booking,
        payment_method_id: str,
        stripe_service: Any,
    ) -> Dict[str, Any]:
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
        return {
            "payment_intent_id": payment_intent_id,
            "stripe_status": stripe_status,
            "stripe_error": stripe_error,
            "success": stripe_status in {"requires_capture", "succeeded"},
        }

    def _persist_retry_authorization_result(
        self,
        *,
        booking_id: str,
        payment_repo: Any,
        payment_method_id: str,
        ctx: Any,
        now: Any,
        stripe_outcome: Dict[str, Any],
    ) -> Dict[str, Any]:
        with self.transaction():
            booking = self.repository.get_booking_with_details(booking_id)
            if not booking:
                raise NotFoundException("Booking not found")

            bp = self.repository.ensure_payment(booking.id)
            bp.payment_method_id = payment_method_id
            bp.auth_attempted_at = now
            bp.auth_scheduled_for = None
            if stripe_outcome["success"]:
                bp.payment_status = PaymentStatus.AUTHORIZED.value
                bp.payment_intent_id = stripe_outcome["payment_intent_id"]
                bp.auth_failure_count = 0
                bp.auth_last_error = None
                payment_repo.create_payment_event(
                    booking_id=booking.id,
                    event_type="auth_retry_succeeded",
                    event_data={
                        "payment_intent_id": stripe_outcome["payment_intent_id"],
                        "authorized_at": now.isoformat(),
                        "amount_cents": ctx.student_pay_cents,
                        "application_fee_cents": ctx.application_fee_cents,
                    },
                )
            else:
                bp.payment_status = PaymentStatus.PAYMENT_METHOD_REQUIRED.value
                bp.auth_failure_count = int(bp.auth_failure_count or 0) + 1
                bp.auth_last_error = (
                    stripe_outcome["stripe_error"]
                    or stripe_outcome["stripe_status"]
                    or "authorization_failed"
                )
                payment_repo.create_payment_event(
                    booking_id=booking.id,
                    event_type="auth_retry_failed",
                    event_data={
                        "payment_intent_id": stripe_outcome["payment_intent_id"],
                        "error": bp.auth_last_error,
                        "failed_at": now.isoformat(),
                    },
                )
            return {
                "success": stripe_outcome["success"],
                "payment_status": bp.payment_status,
                "failure_count": bp.auth_failure_count,
                "error": None if stripe_outcome["success"] else bp.auth_last_error,
            }
