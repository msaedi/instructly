from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from importlib import import_module
import logging
import os
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, Optional, cast

from ...core.exceptions import ServiceException
from ...models.booking import PaymentStatus
from ..base import BaseService
from .helpers import ChargeContext

if TYPE_CHECKING:
    from ...repositories.booking_repository import BookingRepository
    from ...repositories.instructor_profile_repository import InstructorProfileRepository
    from ...repositories.payment_repository import PaymentRepository
    from ..stripe_service import StripeServiceModuleProtocol

logger = logging.getLogger(__name__)


def _stripe_service_module() -> StripeServiceModuleProtocol:
    return cast("StripeServiceModuleProtocol", import_module("app.services.stripe_service"))


@dataclass(slots=True)
class _RetryBookingContext:
    booking_id: str
    booking: Any
    student_id: str
    instructor_id: str
    customer_id: str
    destination_account_id: str
    charge_context: ChargeContext


class StripePaymentFlowMixin(BaseService):
    """Booking-specific payment flows and charge-context helpers."""

    booking_repository: BookingRepository
    instructor_repository: InstructorProfileRepository
    payment_repository: PaymentRepository
    pricing_service: Any
    stripe_configured: bool

    if TYPE_CHECKING:

        def capture_payment_intent(
            self, payment_intent_id: str, *, idempotency_key: Optional[str] = None
        ) -> dict[str, Any]:
            ...

        def _call_with_retry(self, func: Any, *args: Any, **kwargs: Any) -> Any:
            ...

        def ensure_top_up_transfer(
            self,
            *,
            booking_id: str,
            payment_intent_id: str,
            destination_account_id: str,
            amount_cents: int,
        ) -> Optional[dict[str, Any]]:
            ...

        def _top_up_from_pi_metadata(self, payment_intent: Any) -> Optional[int]:
            ...

    @BaseService.measure_operation("stripe_build_charge_context")
    def build_charge_context(
        self, booking_id: str, requested_credit_cents: Optional[int] = None
    ) -> ChargeContext:
        """Return pricing and credit details for a booking without hitting Stripe."""
        try:
            with self.transaction():
                booking = self.booking_repository.get_by_id(booking_id)
                if not booking:
                    raise ServiceException("Booking not found for charge context")

                existing_applied = self.payment_repository.get_applied_credit_cents_for_booking(
                    booking_id
                )
                if requested_credit_cents is not None and requested_credit_cents > 0:
                    if existing_applied > 0:
                        applied_credit_cents = existing_applied
                        self.logger.warning(
                            "requested_credit_ignored_due_to_existing_usage",
                            extra={
                                "booking_id": booking_id,
                                "requested_credit_cents": requested_credit_cents,
                                "existing_applied_cents": existing_applied,
                            },
                        )
                    else:
                        lesson_price_cents = int(
                            Decimal(str(booking.hourly_rate))
                            * Decimal(booking.duration_minutes)
                            * Decimal(100)
                            / Decimal(60)
                        )
                        max_applicable_credits = min(
                            int(requested_credit_cents), lesson_price_cents
                        )
                        from ..credit_service import CreditService

                        credit_service = CreditService(self.db)
                        applied_credit_cents = credit_service.reserve_credits_for_booking(
                            user_id=booking.student_id,
                            booking_id=booking_id,
                            max_amount_cents=max_applicable_credits,
                            use_transaction=False,
                        )
                        self.booking_repository.ensure_payment(
                            booking.id
                        ).credits_reserved_cents = applied_credit_cents
                else:
                    applied_credit_cents = existing_applied
                    booking_payment = self.booking_repository.ensure_payment(booking.id)
                    if existing_applied > 0 and (
                        getattr(booking_payment, "credits_reserved_cents", 0) != existing_applied
                    ):
                        booking_payment.credits_reserved_cents = existing_applied

                pricing = self.pricing_service.compute_booking_pricing(
                    booking_id=booking_id,
                    applied_credit_cents=applied_credit_cents,
                )

            context = ChargeContext(
                booking_id=booking_id,
                applied_credit_cents=applied_credit_cents,
                base_price_cents=int(pricing.get("base_price_cents", 0)),
                student_fee_cents=int(pricing.get("student_fee_cents", 0)),
                instructor_platform_fee_cents=int(pricing.get("instructor_platform_fee_cents", 0)),
                target_instructor_payout_cents=int(
                    pricing.get("target_instructor_payout_cents", 0)
                ),
                student_pay_cents=int(pricing.get("student_pay_cents", 0)),
                application_fee_cents=int(pricing.get("application_fee_cents", 0)),
                top_up_transfer_cents=int(pricing.get("top_up_transfer_cents", 0)),
                instructor_tier_pct=Decimal(str(pricing.get("instructor_tier_pct", 0))),
            )
            if context.top_up_transfer_cents > 0:
                self.logger.info(
                    "Charge context requires top-up transfer",
                    extra={
                        "booking_id": booking_id,
                        "top_up_transfer_cents": context.top_up_transfer_cents,
                        "student_pay_cents": context.student_pay_cents,
                    },
                )
            return context
        except Exception as exc:
            if isinstance(exc, ServiceException):
                raise
            self.logger.error("Failed to build charge context for booking %s: %s", booking_id, exc)
            raise ServiceException("Failed to build charge context") from exc

    def _load_retry_booking_context(
        self, *, booking_id: str, requested_credit_cents: Optional[int]
    ) -> _RetryBookingContext:
        booking = self.booking_repository.get_by_id(booking_id)
        if not booking:
            raise ServiceException(f"Booking {booking_id} not found")
        customer = self.payment_repository.get_customer_by_user_id(booking.student_id)
        if not customer:
            raise ServiceException(f"No Stripe customer for student {booking.student_id}")
        instructor_profile = self.instructor_repository.get_by_user_id(booking.instructor_id)
        if not instructor_profile:
            raise ServiceException(f"Instructor profile not found for user {booking.instructor_id}")
        connected_account = self.payment_repository.get_connected_account_by_instructor_id(
            instructor_profile.id
        )
        if not connected_account or not connected_account.stripe_account_id:
            raise ServiceException("Instructor payment account not set up")
        charge_context = self.build_charge_context(
            booking_id=booking_id,
            requested_credit_cents=requested_credit_cents,
        )
        if charge_context.student_pay_cents <= 0:
            raise ServiceException("Charge amount is zero after applied credits")
        return _RetryBookingContext(
            booking_id=booking_id,
            booking=booking,
            student_id=booking.student_id,
            instructor_id=booking.instructor_id,
            customer_id=customer.stripe_customer_id,
            destination_account_id=connected_account.stripe_account_id,
            charge_context=charge_context,
        )

    def _build_retry_payment_intent_kwargs(
        self,
        *,
        context: _RetryBookingContext,
        payment_method_id: Optional[str],
    ) -> dict[str, Any]:
        facade_module = _stripe_service_module()
        transfer_amount_cents = min(
            int(context.charge_context.student_pay_cents),
            int(context.charge_context.target_instructor_payout_cents),
        )
        stripe_kwargs: dict[str, Any] = {
            "amount": context.charge_context.student_pay_cents,
            "currency": facade_module.settings.stripe_currency or "usd",
            "customer": context.customer_id,
            "transfer_data": {
                "destination": context.destination_account_id,
                "amount": transfer_amount_cents,
            },
            "metadata": {
                "booking_id": context.booking_id,
                "student_id": context.student_id,
                "instructor_id": context.instructor_id,
                "instructor_tier_pct": str(context.charge_context.instructor_tier_pct),
                "base_price_cents": str(context.charge_context.base_price_cents),
                "student_fee_cents": str(context.charge_context.student_fee_cents),
                "platform_fee_cents": str(context.charge_context.instructor_platform_fee_cents),
                "applied_credit_cents": str(context.charge_context.applied_credit_cents),
                "student_pay_cents": str(context.charge_context.student_pay_cents),
                "application_fee_cents": str(context.charge_context.application_fee_cents),
                "target_instructor_payout_cents": str(
                    context.charge_context.target_instructor_payout_cents
                ),
            },
            "transfer_group": f"booking:{context.booking_id}",
            "capture_method": "manual",
            "automatic_payment_methods": {"enabled": True, "allow_redirects": "never"},
            "idempotency_key": f"pi_booking_{context.booking_id}",
        }
        if payment_method_id:
            stripe_kwargs["payment_method"] = payment_method_id
            stripe_kwargs["confirm"] = True
            stripe_kwargs["off_session"] = True
        return stripe_kwargs

    def _create_retry_payment_intent(
        self,
        *,
        context: _RetryBookingContext,
        stripe_kwargs: dict[str, Any],
    ) -> Any:
        stripe_sdk = _stripe_service_module().stripe
        try:
            return self._call_with_retry(stripe_sdk.PaymentIntent.create, **stripe_kwargs)
        except Exception as exc:
            if self.stripe_configured:
                raise
            if os.getenv("INSTAINSTRU_PRODUCTION_MODE", "").lower() == "true":
                raise ServiceException(
                    "Stripe not configured in production mode",
                    code="configuration_error",
                ) from exc
            self.logger.warning(
                "Stripe call failed (%s); storing local record for booking %s",
                exc,
                context.booking_id,
            )
            return SimpleNamespace(
                id=f"mock_pi_{context.booking_id}",
                status="requires_payment_method",
            )

    def _persist_retry_payment_intent(
        self,
        *,
        context: _RetryBookingContext,
        payment_intent: Any,
    ) -> Any:
        self.payment_repository.create_payment_record(
            booking_id=context.booking_id,
            payment_intent_id=payment_intent.id,
            amount=context.charge_context.student_pay_cents,
            application_fee=context.charge_context.application_fee_cents,
            status=payment_intent.status,
            base_price_cents=context.charge_context.base_price_cents,
            instructor_tier_pct=context.charge_context.instructor_tier_pct,
            instructor_payout_cents=context.charge_context.target_instructor_payout_cents,
        )
        booking_payment = self.booking_repository.ensure_payment(context.booking.id)
        booking_payment.payment_intent_id = payment_intent.id
        if payment_intent.status in {"requires_capture", "requires_confirmation", "succeeded"} or (
            isinstance(getattr(payment_intent, "id", None), str)
            and payment_intent.id.startswith("mock_pi_")
        ):
            booking_payment.payment_status = PaymentStatus.AUTHORIZED.value
        return payment_intent

    @BaseService.measure_operation("stripe_create_or_retry_booking_pi")
    def create_or_retry_booking_payment_intent(
        self,
        *,
        booking_id: str,
        payment_method_id: Optional[str] = None,
        requested_credit_cents: Optional[int] = None,
    ) -> Any:
        context = self._load_retry_booking_context(
            booking_id=booking_id,
            requested_credit_cents=requested_credit_cents,
        )
        stripe_kwargs = self._build_retry_payment_intent_kwargs(
            context=context,
            payment_method_id=payment_method_id,
        )
        payment_intent = self._create_retry_payment_intent(
            context=context,
            stripe_kwargs=stripe_kwargs,
        )
        return self._persist_retry_payment_intent(
            context=context,
            payment_intent=payment_intent,
        )

    def _refresh_captured_payment_intent(
        self, *, payment_intent_id: str, payment_intent: Any
    ) -> Any:
        refreshed_payment_intent = payment_intent
        if not self.stripe_configured:
            return refreshed_payment_intent
        try:
            refreshed_payment_intent = _stripe_service_module().stripe.PaymentIntent.retrieve(
                payment_intent_id
            )
        except Exception as exc:
            self.logger.warning(
                "failed_to_refresh_payment_intent_after_capture",
                extra={"payment_intent_id": payment_intent_id, "error": str(exc)},
            )
        return refreshed_payment_intent or payment_intent

    def _compute_capture_top_up_amount(
        self, *, booking_id: str, payment_intent_id: str, refreshed_payment_intent: Any
    ) -> int:
        top_up_amount = self._top_up_from_pi_metadata(refreshed_payment_intent)
        if top_up_amount is not None:
            return top_up_amount
        self.logger.info(
            "top_up_metadata_missing_falling_back",
            extra={"booking_id": booking_id, "payment_intent_id": payment_intent_id},
        )
        try:
            charge_context = self.build_charge_context(booking_id, requested_credit_cents=None)
            amount_value = None
            if self.stripe_configured:
                amount_value = getattr(refreshed_payment_intent, "amount_received", None)
            if amount_value is None:
                amount_value = getattr(refreshed_payment_intent, "amount", None)
            charged_amount = (
                int(str(amount_value))
                if amount_value is not None
                else int(charge_context.student_pay_cents)
            )
            return max(0, int(charge_context.target_instructor_payout_cents) - charged_amount)
        except Exception as exc:
            self.logger.warning(
                "fallback_top_up_computation_failed",
                extra={
                    "booking_id": booking_id,
                    "payment_intent_id": payment_intent_id,
                    "error": str(exc),
                },
            )
            return 0

    def _resolve_capture_destination_account(self, *, booking_id: str) -> Optional[str]:
        try:
            booking = self.booking_repository.get_by_id(booking_id)
        except Exception as exc:
            self.logger.warning(
                "booking_lookup_failed_for_top_up",
                extra={"booking_id": booking_id, "error": str(exc)},
            )
            return None
        if not booking:
            return None
        try:
            instructor_profile = self.instructor_repository.get_by_user_id(booking.instructor_id)
        except Exception as exc:
            self.logger.warning(
                "instructor_profile_lookup_failed_for_top_up",
                extra={
                    "booking_id": booking_id,
                    "instructor_id": booking.instructor_id,
                    "error": str(exc),
                },
            )
            return None
        if not instructor_profile:
            return None
        try:
            connected_account = self.payment_repository.get_connected_account_by_instructor_id(
                instructor_profile.id
            )
            return getattr(connected_account, "stripe_account_id", None)
        except Exception as exc:
            self.logger.warning(
                "connected_account_lookup_failed_for_top_up",
                extra={
                    "booking_id": booking_id,
                    "instructor_profile_id": instructor_profile.id,
                    "error": str(exc),
                },
            )
            return None

    def _ensure_capture_top_up_transfer(
        self,
        *,
        booking_id: str,
        payment_intent_id: str,
        destination_account_id: Optional[str],
        top_up_amount: int,
    ) -> None:
        if top_up_amount <= 0 or not destination_account_id:
            return
        try:
            self.ensure_top_up_transfer(
                booking_id=booking_id,
                payment_intent_id=payment_intent_id,
                destination_account_id=destination_account_id,
                amount_cents=top_up_amount,
            )
        except Exception as exc:
            self.logger.error(
                "ensure_top_up_transfer_failed",
                extra={
                    "booking_id": booking_id,
                    "payment_intent_id": payment_intent_id,
                    "amount_cents": top_up_amount,
                    "error": str(exc),
                },
            )

    @BaseService.measure_operation("stripe_capture_booking_pi")
    def capture_booking_payment_intent(
        self,
        *,
        booking_id: str,
        payment_intent_id: str,
        idempotency_key: Optional[str] = None,
    ) -> dict[str, Any]:
        """Capture a booking PI and return capture details with top-up metadata."""
        capture_result = self.capture_payment_intent(
            payment_intent_id,
            idempotency_key=idempotency_key,
        )
        refreshed_payment_intent = self._refresh_captured_payment_intent(
            payment_intent_id=payment_intent_id,
            payment_intent=capture_result.get("payment_intent"),
        )
        top_up_amount = self._compute_capture_top_up_amount(
            booking_id=booking_id,
            payment_intent_id=payment_intent_id,
            refreshed_payment_intent=refreshed_payment_intent,
        )
        destination_account_id = self._resolve_capture_destination_account(booking_id=booking_id)
        self._ensure_capture_top_up_transfer(
            booking_id=booking_id,
            payment_intent_id=payment_intent_id,
            destination_account_id=destination_account_id,
            top_up_amount=top_up_amount,
        )
        capture_result["payment_intent"] = refreshed_payment_intent
        capture_result["top_up_transfer_cents"] = top_up_amount
        return capture_result
