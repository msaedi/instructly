from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
import logging
import math
import os
from typing import TYPE_CHECKING, Any, Optional

import stripe

from ...core.exceptions import ServiceException
from ...models.payment import PaymentIntent
from ..base import BaseService
from .helpers import ChargeContext

if TYPE_CHECKING:
    from ...repositories.payment_repository import PaymentRepository

logger = logging.getLogger(__name__)


def _stripe_service_module() -> Any:
    return import_module("app.services.stripe_service")


@dataclass(slots=True)
class _PreparedPaymentIntent:
    charge_context: Optional[ChargeContext]
    amount: int
    transfer_amount_cents: int
    platform_retained_cents: int
    metadata: dict[str, str]


class StripePaymentIntentsMixin(BaseService):
    """PaymentIntent primitives used by checkout and booking flows."""

    payment_repository: PaymentRepository
    platform_fee_percentage: float
    stripe_configured: bool
    _last_client_secret: Optional[str]

    if TYPE_CHECKING:

        def _call_with_retry(self, func: Any, *args: Any, **kwargs: Any) -> Any:
            ...

        def build_charge_context(
            self, booking_id: str, requested_credit_cents: Optional[int] = None
        ) -> ChargeContext:
            ...

    def _validate_payment_intent_preview_parity(
        self,
        *,
        booking_id: str,
        charge_context: ChargeContext,
        metadata: dict[str, str],
    ) -> None:
        settings = _stripe_service_module().settings
        if settings.environment == "production":
            return
        try:
            metadata_student_pay_cents = int(metadata["student_pay_cents"])
            metadata_base_price_cents = int(metadata["base_price_cents"])
            metadata_student_fee_cents = int(metadata["student_fee_cents"])
            metadata_applied_credit_cents = int(metadata["applied_credit_cents"])
        except (KeyError, ValueError) as parse_error:
            self.logger.warning(
                "stripe.pi.preview_parity_parse_error",
                {
                    "booking_id": booking_id,
                    "error": str(parse_error),
                    "metadata": metadata,
                },
            )
            return

        parity_snapshot = {
            "booking_id": booking_id,
            "student_pay_cents": charge_context.student_pay_cents,
            "metadata_student_pay_cents": metadata_student_pay_cents,
            "base_price_cents": charge_context.base_price_cents,
            "metadata_base_price_cents": metadata_base_price_cents,
            "student_fee_cents": charge_context.student_fee_cents,
            "metadata_student_fee_cents": metadata_student_fee_cents,
            "applied_credit_cents": charge_context.applied_credit_cents,
            "metadata_applied_credit_cents": metadata_applied_credit_cents,
        }
        self.logger.debug("stripe.pi.preview_parity", parity_snapshot)
        if metadata_student_pay_cents != charge_context.student_pay_cents:
            raise ServiceException("PaymentIntent amount mismatch preview student pay")
        if metadata_base_price_cents != charge_context.base_price_cents:
            raise ServiceException("PaymentIntent base price mismatch preview")
        if metadata_student_fee_cents != charge_context.student_fee_cents:
            raise ServiceException("PaymentIntent student fee mismatch preview")
        if metadata_applied_credit_cents != charge_context.applied_credit_cents:
            raise ServiceException("PaymentIntent credit mismatch preview")

    def _prepare_payment_intent_context(
        self,
        *,
        booking_id: str,
        charge_context: Optional[ChargeContext],
        requested_credit_cents: Optional[int],
        amount_cents: Optional[int],
    ) -> _PreparedPaymentIntent:
        context = charge_context
        if context is None and requested_credit_cents is not None:
            context = self.build_charge_context(booking_id, requested_credit_cents)

        if context is None:
            if amount_cents is None:
                raise ServiceException(
                    "amount_cents is required when charge context is not provided"
                )
            amount = int(amount_cents)
            platform_retained_cents = math.ceil(amount * self.platform_fee_percentage)
            return _PreparedPaymentIntent(
                charge_context=None,
                amount=amount,
                transfer_amount_cents=amount - platform_retained_cents,
                platform_retained_cents=platform_retained_cents,
                metadata={
                    "booking_id": booking_id,
                    "platform": "instainstru",
                    "applied_credit_cents": "0",
                },
            )

        metadata = {
            "booking_id": booking_id,
            "platform": "instainstru",
            "instructor_tier_pct": str(context.instructor_tier_pct),
            "base_price_cents": str(context.base_price_cents),
            "student_fee_cents": str(context.student_fee_cents),
            "platform_fee_cents": str(context.instructor_platform_fee_cents),
            "applied_credit_cents": str(context.applied_credit_cents),
            "student_pay_cents": str(context.student_pay_cents),
            "application_fee_cents": str(context.application_fee_cents),
            "target_instructor_payout_cents": str(context.target_instructor_payout_cents),
        }
        self._validate_payment_intent_preview_parity(
            booking_id=booking_id,
            charge_context=context,
            metadata=metadata,
        )
        amount = int(context.student_pay_cents)
        transfer_amount_cents = min(amount, int(context.target_instructor_payout_cents))
        return _PreparedPaymentIntent(
            charge_context=context,
            amount=amount,
            transfer_amount_cents=transfer_amount_cents,
            platform_retained_cents=max(0, amount - transfer_amount_cents),
            metadata=metadata,
        )

    def _build_payment_intent_kwargs(
        self,
        *,
        booking_id: str,
        customer_id: str,
        destination_account_id: str,
        currency: str,
        save_payment_method: bool,
        prepared: _PreparedPaymentIntent,
    ) -> dict[str, Any]:
        stripe_kwargs: dict[str, Any] = {
            "amount": prepared.amount,
            "currency": currency,
            "customer": customer_id,
            "transfer_data": {
                "destination": destination_account_id,
                "amount": prepared.transfer_amount_cents,
            },
            "metadata": prepared.metadata,
            "capture_method": "manual",
            "automatic_payment_methods": {
                "enabled": True,
                "allow_redirects": "never",
            },
            "idempotency_key": f"pi_checkout_{booking_id}_{prepared.amount}",
        }
        if prepared.charge_context is not None:
            stripe_kwargs["transfer_group"] = f"booking:{booking_id}"
        if save_payment_method:
            stripe_kwargs["setup_future_usage"] = "off_session"
        return stripe_kwargs

    def _create_payment_intent_with_fallback(
        self,
        *,
        booking_id: str,
        stripe_create: Any,
        stripe_kwargs: dict[str, Any],
    ) -> tuple[str, str, Optional[str]]:
        try:
            stripe_intent = self._call_with_retry(stripe_create, **stripe_kwargs)
            return stripe_intent.id, stripe_intent.status, stripe_intent.client_secret
        except Exception as exc:
            if self.stripe_configured:
                raise
            production_mode = os.getenv("INSTAINSTRU_PRODUCTION_MODE", "").strip().lower()
            if production_mode in {"1", "true", "yes", "on"}:
                raise ServiceException(
                    "Stripe is not configured in production mode; refusing mock payment intent fallback"
                ) from exc
            self.logger.warning(
                "Stripe not configured or call failed (%s); using mock payment intent for booking %s",
                exc,
                booking_id,
            )
            return (
                f"mock_pi_{booking_id}",
                "requires_payment_method",
                f"mock_secret_{booking_id}",
            )

    def _persist_created_payment_intent(
        self,
        *,
        booking_id: str,
        payment_intent_id: str,
        prepared: _PreparedPaymentIntent,
        status: str,
    ) -> PaymentIntent:
        charge_context = prepared.charge_context
        return self.payment_repository.create_payment_record(
            booking_id=booking_id,
            payment_intent_id=payment_intent_id,
            amount=prepared.amount,
            application_fee=prepared.platform_retained_cents,
            status=status,
            base_price_cents=charge_context.base_price_cents if charge_context else None,
            instructor_tier_pct=charge_context.instructor_tier_pct if charge_context else None,
            instructor_payout_cents=charge_context.target_instructor_payout_cents
            if charge_context
            else None,
        )

    @BaseService.measure_operation("stripe_create_payment_intent")
    def create_payment_intent(
        self,
        booking_id: str,
        customer_id: str,
        destination_account_id: str,
        *,
        charge_context: Optional[ChargeContext] = None,
        requested_credit_cents: Optional[int] = None,
        amount_cents: Optional[int] = None,
        currency: str = "usd",
        save_payment_method: bool = False,
    ) -> PaymentIntent:
        """Create a Stripe PaymentIntent for a booking."""
        try:
            prepared = self._prepare_payment_intent_context(
                booking_id=booking_id,
                charge_context=charge_context,
                requested_credit_cents=requested_credit_cents,
                amount_cents=amount_cents,
            )
            stripe_kwargs = self._build_payment_intent_kwargs(
                booking_id=booking_id,
                customer_id=customer_id,
                destination_account_id=destination_account_id,
                currency=currency,
                save_payment_method=save_payment_method,
                prepared=prepared,
            )
            stripe_sdk = _stripe_service_module().stripe
            (
                payment_intent_id,
                stripe_status,
                stripe_client_secret,
            ) = self._create_payment_intent_with_fallback(
                booking_id=booking_id,
                stripe_create=stripe_sdk.PaymentIntent.create,
                stripe_kwargs=stripe_kwargs,
            )
            with self.transaction():
                payment_record = self._persist_created_payment_intent(
                    booking_id=booking_id,
                    payment_intent_id=payment_intent_id,
                    prepared=prepared,
                    status=stripe_status,
                )
            self._last_client_secret = stripe_client_secret
            self.logger.info(
                "Created payment intent %s for booking %s", payment_intent_id, booking_id
            )
            return payment_record
        except stripe.StripeError as exc:
            self.logger.error("Stripe error creating payment intent: %s", exc)
            raise ServiceException(f"Failed to create payment intent: {str(exc)}")
        except Exception as exc:
            self.logger.error("Error creating payment intent: %s", exc)
            raise ServiceException(f"Failed to create payment intent: {str(exc)}")

    @BaseService.measure_operation("stripe_create_and_confirm_manual_authorization")
    def create_and_confirm_manual_authorization(
        self,
        *,
        booking_id: str,
        customer_id: str,
        destination_account_id: str,
        payment_method_id: str,
        amount_cents: int,
        currency: str = "usd",
        idempotency_key: Optional[str] = None,
    ) -> dict[str, Any]:
        """Create and confirm a manual-capture PaymentIntent off-session."""
        try:
            platform_retained_cents = math.ceil(amount_cents * self.platform_fee_percentage)
            transfer_amount_cents = amount_cents - platform_retained_cents
            stripe_sdk = _stripe_service_module().stripe
            payment_intent = self._call_with_retry(
                stripe_sdk.PaymentIntent.create,
                amount=amount_cents,
                currency=currency,
                customer=customer_id,
                payment_method=payment_method_id,
                capture_method="manual",
                confirm=True,
                off_session=True,
                automatic_payment_methods={"enabled": True, "allow_redirects": "never"},
                transfer_data={
                    "destination": destination_account_id,
                    "amount": transfer_amount_cents,
                },
                metadata={
                    "booking_id": booking_id,
                    "platform": "instainstru",
                    "applied_credit_cents": "0",
                    "target_instructor_payout_cents": str(transfer_amount_cents),
                },
                idempotency_key=idempotency_key,
            )
            result: dict[str, Any] = {
                "payment_intent": payment_intent,
                "status": payment_intent.status,
                "requires_action": getattr(payment_intent, "status", "") == "requires_action",
                "client_secret": getattr(payment_intent, "client_secret", None)
                if getattr(payment_intent, "status", "") == "requires_action"
                else _stripe_service_module()._ABSENT,
            }
            try:
                upsert = getattr(self.payment_repository, "upsert_payment_record", None)
                if callable(upsert):
                    upsert(
                        booking_id=booking_id,
                        payment_intent_id=payment_intent.id,
                        amount=amount_cents,
                        application_fee=platform_retained_cents,
                        status=payment_intent.status,
                    )
                elif self.payment_repository.get_payment_by_intent_id(payment_intent.id) is None:
                    self.payment_repository.create_payment_record(
                        booking_id=booking_id,
                        payment_intent_id=payment_intent.id,
                        amount=amount_cents,
                        application_fee=platform_retained_cents,
                        status=payment_intent.status,
                    )
            except Exception:
                logger.warning(
                    "Failed to persist manual authorization payment record for booking %s",
                    booking_id,
                    exc_info=True,
                )
            return result
        except stripe.StripeError as exc:
            self.logger.error("Stripe error creating manual authorization: %s", exc)
            raise ServiceException(f"Failed to authorize payment: {str(exc)}")
        except Exception as exc:
            self.logger.error("Error creating manual authorization: %s", exc)
            raise ServiceException(f"Failed to authorize payment: {str(exc)}")

    @BaseService.measure_operation("stripe_confirm_payment_intent")
    def confirm_payment_intent(
        self, payment_intent_id: str, payment_method_id: str
    ) -> PaymentIntent:
        """Confirm a payment intent with a payment method."""
        try:
            facade_module = _stripe_service_module()
            stripe_sdk = facade_module.stripe
            stripe_intent = stripe_sdk.PaymentIntent.confirm(
                payment_intent_id,
                payment_method=payment_method_id,
                return_url=f"{facade_module.settings.frontend_url}/student/payment/complete",
            )
            with self.transaction():
                payment_record = self.payment_repository.update_payment_status(
                    payment_intent_id,
                    stripe_intent.status,
                )
                if not payment_record:
                    raise ServiceException(
                        f"Payment record not found for intent {payment_intent_id}"
                    )
            self.logger.info("Confirmed payment intent %s", payment_intent_id)
            return payment_record
        except stripe.StripeError as exc:
            self.logger.error("Stripe error confirming payment: %s", exc)
            raise ServiceException(f"Failed to confirm payment: {str(exc)}")
        except Exception as exc:
            self.logger.error("Error confirming payment intent: %s", exc)
            raise ServiceException(f"Failed to confirm payment: {str(exc)}")
