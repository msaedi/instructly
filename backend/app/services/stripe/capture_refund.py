from __future__ import annotations

from importlib import import_module
import logging
import time as _time
from typing import TYPE_CHECKING, Any, Optional, cast

import stripe

from ...core.exceptions import ServiceException
from ..base import BaseService

if TYPE_CHECKING:
    from ...repositories.payment_repository import PaymentRepository
    from ..stripe_service import StripeServiceModuleProtocol

logger = logging.getLogger(__name__)


def _stripe_service_module() -> StripeServiceModuleProtocol:
    return cast("StripeServiceModuleProtocol", import_module("app.services.stripe_service"))


class StripeCaptureRefundMixin(BaseService):
    """Payment capture, refunds, voids, and transfer reversal."""

    payment_repository: PaymentRepository
    stripe_configured: bool

    def _execute_stripe_capture(
        self, payment_intent_id: str, *, idempotency_key: Optional[str] = None
    ) -> Any:
        api_start = _time.time()
        payment_intent = _stripe_service_module().stripe.PaymentIntent.capture(
            payment_intent_id,
            idempotency_key=idempotency_key,
            expand=["latest_charge"],
        )
        api_duration_ms = (_time.time() - api_start) * 1000
        self.logger.info(
            "Stripe PaymentIntent.capture API call took %sms",
            f"{api_duration_ms:.0f}",
            extra={
                "stripe_api_duration_ms": api_duration_ms,
                "payment_intent_id": payment_intent_id,
            },
        )
        return payment_intent

    def _extract_transfer_amount(
        self, payment_intent: Any, transfer_id: Optional[str]
    ) -> Optional[int]:
        if not transfer_id:
            return None
        try:
            transfer = _stripe_service_module().StripeTransfer.retrieve(transfer_id)
            return getattr(transfer, "amount", None)
        except Exception as exc:
            logger.warning(
                "Failed to retrieve transfer %s for capture details: %s",
                transfer_id,
                str(exc),
                exc_info=True,
            )
            metadata = getattr(payment_intent, "metadata", None)
            target_payout = getattr(metadata, "target_instructor_payout_cents", None)
            if not target_payout:
                return None
            try:
                return int(target_payout)
            except (TypeError, ValueError):
                return None

    def _resolve_amount_received(self, payment_intent: Any, amount_received: Any) -> Any:
        if amount_received is None:
            amount_received = getattr(payment_intent, "amount_received", None)
        if amount_received is None:
            fallback_amount = getattr(payment_intent, "amount", None)
            if fallback_amount is not None:
                try:
                    return int(fallback_amount)
                except (TypeError, ValueError):
                    return fallback_amount
        return amount_received

    def _extract_capture_details(
        self, payment_intent: Any
    ) -> tuple[Optional[str], Optional[str], Any, Optional[int]]:
        charge_id = None
        transfer_id = None
        amount_received = None
        transfer_amount = None

        try:
            charge = getattr(payment_intent, "latest_charge", None)
            if charge is None:
                amount_received = getattr(payment_intent, "amount_received", None)
            elif isinstance(charge, str):
                logger.warning(
                    "capture_refund: latest_charge is not expanded for payment intent %s",
                    getattr(payment_intent, "id", None),
                )
                charge_id = charge
                amount_received = getattr(payment_intent, "amount_received", None)
            else:
                charge_id = getattr(charge, "id", None)
                amount_received = getattr(charge, "amount", None)
                if amount_received is None:
                    amount_received = getattr(payment_intent, "amount_received", None)
                transfer_id = getattr(charge, "transfer", None)
                transfer_amount = self._extract_transfer_amount(payment_intent, transfer_id)
        except Exception as exc:
            logger.warning(
                "Failed to extract capture details from payment intent %s: %s",
                getattr(payment_intent, "id", None),
                str(exc),
                exc_info=True,
            )

        amount_received = self._resolve_amount_received(payment_intent, amount_received)
        return charge_id, transfer_id, amount_received, transfer_amount

    @BaseService.measure_operation("stripe_capture_payment_intent")
    def capture_payment_intent(
        self, payment_intent_id: str, *, idempotency_key: Optional[str] = None
    ) -> dict[str, Any]:
        """
        Capture a manual-capture PaymentIntent and return charge and transfer info.
        """
        try:
            payment_intent = self._execute_stripe_capture(
                payment_intent_id,
                idempotency_key=idempotency_key,
            )
            (
                charge_id,
                transfer_id,
                amount_received,
                transfer_amount,
            ) = self._extract_capture_details(payment_intent)
            try:
                self.payment_repository.update_payment_status(
                    payment_intent_id, payment_intent.status
                )
            except Exception as exc:
                logger.warning(
                    "Failed to persist captured payment status for %s: %s",
                    payment_intent_id,
                    str(exc),
                    exc_info=True,
                )
            return {
                "payment_intent": payment_intent,
                "charge_id": charge_id,
                "transfer_id": transfer_id,
                "amount_received": amount_received,
                "transfer_amount": transfer_amount,
            }
        except stripe.StripeError as exc:
            self.logger.error("Stripe error capturing payment intent: %s", exc)
            raise ServiceException(f"Failed to capture payment: {str(exc)}")
        except Exception as exc:
            self.logger.error("Error capturing payment intent: %s", exc)
            raise ServiceException(f"Failed to capture payment: {str(exc)}")

    @BaseService.measure_operation("stripe_get_payment_intent_details")
    def get_payment_intent_capture_details(self, payment_intent_id: str) -> dict[str, Any]:
        """Retrieve a PaymentIntent and extract charge/transfer details without capturing."""
        try:
            payment_intent = _stripe_service_module().stripe.PaymentIntent.retrieve(
                payment_intent_id,
                expand=["latest_charge"],
            )
            (
                charge_id,
                transfer_id,
                amount_received,
                transfer_amount,
            ) = self._extract_capture_details(payment_intent)
            return {
                "payment_intent": payment_intent,
                "charge_id": charge_id,
                "transfer_id": transfer_id,
                "amount_received": amount_received,
                "transfer_amount": transfer_amount,
            }
        except stripe.StripeError as exc:
            self.logger.error("Stripe error retrieving payment intent: %s", exc)
            raise ServiceException(f"Failed to retrieve payment intent: {str(exc)}")
        except Exception as exc:
            self.logger.error("Error retrieving payment intent: %s", exc)
            raise ServiceException(f"Failed to retrieve payment intent: {str(exc)}")

    @BaseService.measure_operation("stripe_reverse_transfer")
    def reverse_transfer(
        self,
        *,
        transfer_id: str,
        amount_cents: Optional[int] = None,
        idempotency_key: Optional[str] = None,
        reason: str = "",
    ) -> dict[str, Any]:
        """Reverse a transfer (full or partial) back to platform balance."""
        try:
            kwargs: dict[str, Any] = {}
            if amount_cents is not None:
                kwargs["amount"] = amount_cents
            if reason:
                kwargs["metadata"] = {"reason": reason}

            api_start = _time.time()
            reversal = _stripe_service_module().stripe.Transfer.create_reversal(
                transfer_id,
                idempotency_key=idempotency_key,
                **kwargs,
            )
            api_duration_ms = (_time.time() - api_start) * 1000
            self.logger.info(
                "Stripe Transfer.create_reversal API call took %sms",
                f"{api_duration_ms:.0f}",
                extra={"stripe_api_duration_ms": api_duration_ms, "transfer_id": transfer_id},
            )
            try:
                reversed_amount = getattr(reversal, "amount_reversed", None) or getattr(
                    reversal, "amount", None
                )
                if (
                    amount_cents is not None
                    and reversed_amount is not None
                    and reversed_amount < amount_cents
                ):
                    self.logger.warning(
                        "Partial reversal for transfer %s: requested=%s reversed=%s",
                        transfer_id,
                        amount_cents,
                        reversed_amount,
                    )
                failure_code = getattr(reversal, "failure_code", None)
                if failure_code:
                    self.logger.error(
                        "Transfer reversal reported failure_code=%s for transfer %s",
                        failure_code,
                        transfer_id,
                    )
            except Exception as exc:
                logger.warning(
                    "Failed to inspect reversal metadata for transfer %s: %s",
                    transfer_id,
                    str(exc),
                    exc_info=True,
                )
            return {"reversal": reversal}
        except stripe.StripeError as exc:
            self.logger.error("Stripe error reversing transfer: %s", exc)
            raise ServiceException(f"Failed to reverse transfer: {str(exc)}")
        except Exception as exc:
            self.logger.error("Error reversing transfer: %s", exc)
            raise ServiceException(f"Failed to reverse transfer: {str(exc)}")

    @BaseService.measure_operation("stripe_cancel_payment_intent")
    def cancel_payment_intent(
        self, payment_intent_id: str, *, idempotency_key: Optional[str] = None
    ) -> dict[str, Any]:
        """Cancel a PaymentIntent to release authorization."""
        try:
            payment_intent = _stripe_service_module().stripe.PaymentIntent.cancel(
                payment_intent_id,
                idempotency_key=idempotency_key,
            )
            try:
                self.payment_repository.update_payment_status(
                    payment_intent_id, payment_intent.status
                )
            except Exception as exc:
                logger.warning(
                    "Failed to persist canceled payment status for %s: %s",
                    payment_intent_id,
                    str(exc),
                    exc_info=True,
                )
            return {"payment_intent": payment_intent}
        except stripe.StripeError as exc:
            self.logger.error("Stripe error canceling payment intent: %s", exc)
            raise ServiceException(f"Failed to cancel payment intent: {str(exc)}")
        except Exception as exc:
            self.logger.error("Error canceling payment intent: %s", exc)
            raise ServiceException(f"Failed to cancel payment intent: {str(exc)}")

    @BaseService.measure_operation("stripe_void_or_refund_payment")
    def _void_or_refund_payment(self, payment_intent_id: Optional[str]) -> None:
        """Void an uncaptured payment or refund a captured payment intent."""
        if not payment_intent_id:
            return
        if not payment_intent_id.startswith("pi_"):
            self.logger.info(
                "Skipping void/refund for non-Stripe payment intent %s",
                payment_intent_id,
            )
            return
        if not self.stripe_configured:
            self.logger.info(
                "Stripe not configured; skipping void/refund for %s", payment_intent_id
            )
            return

        try:
            payment_intent = _stripe_service_module().stripe.PaymentIntent.retrieve(
                payment_intent_id
            )
            status = getattr(payment_intent, "status", None)
            if status == "requires_capture":
                self.cancel_payment_intent(
                    payment_intent_id,
                    idempotency_key=f"void_{payment_intent_id}",
                )
                self.logger.info("Voided uncaptured payment %s", payment_intent_id)
            elif status == "succeeded":
                self.refund_payment(
                    payment_intent_id,
                    reverse_transfer=True,
                    refund_application_fee=True,
                    idempotency_key=f"refund_{payment_intent_id}",
                )
                self.logger.info("Refunded captured payment %s", payment_intent_id)
            else:
                self.logger.info(
                    "Payment %s in state %s; no refund action required",
                    payment_intent_id,
                    status,
                )
        except stripe.StripeError as exc:
            self.logger.error("Failed to void/refund payment %s: %s", payment_intent_id, exc)
        except Exception as exc:
            self.logger.error("Failed to void/refund payment %s: %s", payment_intent_id, exc)

    @BaseService.measure_operation("stripe_refund_payment")
    def refund_payment(
        self,
        payment_intent_id: str,
        *,
        amount_cents: Optional[int] = None,
        reason: str = "requested_by_customer",
        reverse_transfer: bool = True,
        refund_application_fee: bool = False,
        idempotency_key: Optional[str] = None,
    ) -> dict[str, Any]:
        """Issue a refund for a captured PaymentIntent with automatic transfer reversal."""
        try:
            refund_kwargs: dict[str, Any] = {
                "payment_intent": payment_intent_id,
                "reverse_transfer": reverse_transfer,
            }
            if amount_cents is not None:
                refund_kwargs["amount"] = amount_cents
            if reason in {"requested_by_customer", "duplicate", "fraudulent"}:
                refund_kwargs["reason"] = reason
            if refund_application_fee:
                refund_kwargs["refund_application_fee"] = True
            if idempotency_key:
                refund_kwargs["idempotency_key"] = idempotency_key

            refund = _stripe_service_module().StripeRefund.create(**refund_kwargs)
            payment_status = "refunded"
            if refund.status == "failed":
                payment_status = "refund_failed"
            elif refund.status != "succeeded":
                payment_status = "refund_pending"
            try:
                self.payment_repository.update_payment_status(payment_intent_id, payment_status)
            except Exception as exc:
                logger.warning(
                    "Failed to persist refund status for %s: %s",
                    payment_intent_id,
                    str(exc),
                    exc_info=True,
                )
            self.logger.info(
                "Refund created for PI %s: refund_id=%s, amount=%s, reverse_transfer=%s",
                payment_intent_id,
                refund.id,
                refund.amount,
                reverse_transfer,
            )
            return {
                "refund_id": refund.id,
                "status": refund.status,
                "amount_refunded": refund.amount,
                "payment_intent_id": payment_intent_id,
            }
        except stripe.StripeError as exc:
            self.logger.error("Stripe error creating refund: %s", exc)
            raise ServiceException(f"Failed to create refund: {str(exc)}")
        except Exception as exc:
            self.logger.error("Error creating refund: %s", exc)
            raise ServiceException(f"Failed to create refund: {str(exc)}")
