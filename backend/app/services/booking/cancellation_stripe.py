from __future__ import annotations

import logging
from typing import Any, Dict, Optional, cast

from ...models.booking import PaymentStatus

logger = logging.getLogger(__name__)


class BookingCancellationStripeMixin:
    def _execute_cancellation_stripe_calls(
        self, ctx: Dict[str, Any], stripe_service: Any
    ) -> Dict[str, Any]:
        """Execute Stripe calls for cancellation with no DB transaction held."""
        results = self._initialize_cancellation_stripe_results()
        scenario = ctx["scenario"]
        if scenario == "over_24h_gaming":
            self._execute_over_24h_gaming_cancellation(ctx, stripe_service, results)
        elif scenario == "over_24h_regular":
            self._execute_over_24h_regular_cancellation(ctx, stripe_service, results)
        elif scenario in ("instructor_cancel_over_24h", "instructor_cancel_under_24h"):
            self._execute_instructor_cancellation_stripe_flow(ctx, stripe_service, results)
        elif scenario == "between_12_24h":
            self._execute_between_12_24h_cancellation(ctx, stripe_service, results)
        elif scenario == "under_12h":
            self._execute_under_12h_cancellation(ctx, stripe_service, results)
        return results

    @staticmethod
    def _initialize_cancellation_stripe_results() -> Dict[str, Any]:
        return {
            "cancel_pi_success": False,
            "capture_success": False,
            "reverse_success": False,
            "reverse_attempted": False,
            "reverse_failed": False,
            "reverse_reversal_id": None,
            "refund_success": False,
            "refund_failed": False,
            "refund_data": None,
            "payout_success": False,
            "payout_failed": False,
            "payout_transfer_id": None,
            "payout_amount_cents": None,
            "capture_data": None,
            "error": None,
        }

    def _cancellation_payment_already_captured(self, ctx: Dict[str, Any]) -> bool:
        payment_status = (ctx.get("payment_status") or "").lower()
        return payment_status in {PaymentStatus.SETTLED.value, PaymentStatus.LOCKED.value}

    def _capture_cancellation_payment(
        self,
        *,
        ctx: Dict[str, Any],
        stripe_service: Any,
        idempotency_key: str,
    ) -> Dict[str, Any]:
        payment_intent_id = ctx["payment_intent_id"]
        if self._cancellation_payment_already_captured(ctx):
            capture = stripe_service.get_payment_intent_capture_details(payment_intent_id)
        else:
            capture = stripe_service.capture_payment_intent(
                payment_intent_id,
                idempotency_key=idempotency_key,
            )
        return {
            "transfer_id": capture.get("transfer_id"),
            "amount_received": capture.get("amount_received"),
            "transfer_amount": capture.get("transfer_amount"),
        }

    def _attempt_cancellation_transfer_reversal(
        self,
        *,
        ctx: Dict[str, Any],
        stripe_service: Any,
        results: Dict[str, Any],
        idempotency_key: str,
        reason: str,
    ) -> None:
        booking_id = ctx["booking_id"]
        capture_data = results.get("capture_data") or {}
        transfer_id = capture_data.get("transfer_id")
        transfer_amount = capture_data.get("transfer_amount")
        if not transfer_id:
            results["reverse_failed"] = True
            logger.error("Missing transfer_id for cancellation booking %s", booking_id)
            return
        if not transfer_amount:
            return

        results["reverse_attempted"] = True
        try:
            reversal = stripe_service.reverse_transfer(
                transfer_id=transfer_id,
                amount_cents=transfer_amount,
                idempotency_key=idempotency_key,
                reason=reason,
            )
            results["reverse_success"] = True
            reversal_obj = reversal.get("reversal") if isinstance(reversal, dict) else None
            results["reverse_reversal_id"] = (
                reversal_obj.get("id")
                if isinstance(reversal_obj, dict)
                else getattr(reversal_obj, "id", None)
            )
        except Exception as exc:
            results["reverse_failed"] = True
            logger.error("Transfer reversal failed for booking %s: %s", booking_id, exc)

    def _execute_over_24h_gaming_cancellation(
        self, ctx: Dict[str, Any], stripe_service: Any, results: Dict[str, Any]
    ) -> None:
        payment_intent_id = ctx["payment_intent_id"]
        if not payment_intent_id:
            return
        booking_id = ctx["booking_id"]
        try:
            results["capture_data"] = self._capture_cancellation_payment(
                ctx=ctx,
                stripe_service=stripe_service,
                idempotency_key=f"capture_resched_{booking_id}",
            )
            results["capture_success"] = True
            self._attempt_cancellation_transfer_reversal(
                ctx=ctx,
                stripe_service=stripe_service,
                results=results,
                idempotency_key=f"reverse_resched_{booking_id}",
                reason="gaming_reschedule_cancel",
            )
        except Exception as exc:
            logger.warning("Capture not performed for booking %s: %s", booking_id, exc)
            results["error"] = str(exc)

    def _execute_over_24h_regular_cancellation(
        self, ctx: Dict[str, Any], stripe_service: Any, results: Dict[str, Any]
    ) -> None:
        payment_intent_id = ctx["payment_intent_id"]
        if not payment_intent_id:
            return
        booking_id = ctx["booking_id"]
        try:
            stripe_service.cancel_payment_intent(
                payment_intent_id,
                idempotency_key=f"cancel_{booking_id}",
            )
            results["cancel_pi_success"] = True
        except Exception as exc:
            logger.warning("Cancel PI failed for booking %s: %s", booking_id, exc)
            results["error"] = str(exc)

    def _execute_instructor_cancellation_stripe_flow(
        self, ctx: Dict[str, Any], stripe_service: Any, results: Dict[str, Any]
    ) -> None:
        payment_intent_id = ctx["payment_intent_id"]
        if not payment_intent_id:
            return
        booking_id = ctx["booking_id"]
        if self._cancellation_payment_already_captured(ctx):
            try:
                refund = stripe_service.refund_payment(
                    payment_intent_id,
                    reverse_transfer=True,
                    refund_application_fee=True,
                    idempotency_key=f"refund_instructor_cancel_{booking_id}",
                )
                results["refund_success"] = True
                results["refund_data"] = refund
            except Exception as exc:
                logger.warning("Instructor refund failed for booking %s: %s", booking_id, exc)
                results["refund_failed"] = True
                results["error"] = str(exc)
            return

        try:
            stripe_service.cancel_payment_intent(
                payment_intent_id,
                idempotency_key=f"cancel_instructor_{booking_id}",
            )
            results["cancel_pi_success"] = True
        except Exception as exc:
            logger.warning("Cancel PI failed for booking %s: %s", booking_id, exc)
            results["error"] = str(exc)

    def _execute_between_12_24h_cancellation(
        self, ctx: Dict[str, Any], stripe_service: Any, results: Dict[str, Any]
    ) -> None:
        payment_intent_id = ctx["payment_intent_id"]
        if not payment_intent_id:
            return
        booking_id = ctx["booking_id"]
        try:
            results["capture_data"] = self._capture_cancellation_payment(
                ctx=ctx,
                stripe_service=stripe_service,
                idempotency_key=f"capture_cancel_{booking_id}",
            )
            results["capture_success"] = True
            self._attempt_cancellation_transfer_reversal(
                ctx=ctx,
                stripe_service=stripe_service,
                results=results,
                idempotency_key=f"reverse_{booking_id}",
                reason="student_cancel_12-24h",
            )
        except Exception as exc:
            logger.warning("Capture not performed for booking %s: %s", booking_id, exc)
            results["error"] = str(exc)

    def _resolve_under_12h_payout_amount(
        self,
        *,
        booking_id: str,
        transfer_amount: Any,
        stripe_service: Any,
    ) -> Optional[int]:
        payout_full_cents = transfer_amount
        if payout_full_cents is not None:
            return int(payout_full_cents)
        try:
            payout_ctx = stripe_service.build_charge_context(
                booking_id=booking_id, requested_credit_cents=None
            )
            return int(getattr(payout_ctx, "target_instructor_payout_cents", 0) or 0)
        except Exception as exc:
            logger.warning(
                "Failed to resolve instructor payout for booking %s: %s",
                booking_id,
                exc,
            )
            return None

    def _execute_under_12h_cancellation(
        self, ctx: Dict[str, Any], stripe_service: Any, results: Dict[str, Any]
    ) -> None:
        payment_intent_id = ctx["payment_intent_id"]
        if not payment_intent_id:
            return
        booking_id = ctx["booking_id"]
        try:
            results["capture_data"] = self._capture_cancellation_payment(
                ctx=ctx,
                stripe_service=stripe_service,
                idempotency_key=f"capture_late_cancel_{booking_id}",
            )
            results["capture_success"] = True
            capture_data = cast(Dict[str, Any], results.get("capture_data") or {})
            payout_full_cents = capture_data.get("transfer_amount")
            if payout_full_cents is None:
                payout_full_cents = self._resolve_under_12h_payout_amount(
                    booking_id=booking_id,
                    transfer_amount=None,
                    stripe_service=stripe_service,
                )
            if payout_full_cents is None:
                results["payout_failed"] = True
                results["error"] = "missing_payout_amount"
                return
            capture_data["transfer_amount"] = int(payout_full_cents)
            results["capture_data"] = capture_data
            self._attempt_cancellation_transfer_reversal(
                ctx=ctx,
                stripe_service=stripe_service,
                results=results,
                idempotency_key=f"reverse_lt12_{booking_id}",
                reason="student_cancel_under_12h",
            )
            if results.get("reverse_success") or int(payout_full_cents) == 0:
                self._execute_under_12h_payout_transfer(
                    ctx,
                    stripe_service,
                    results,
                    payout_full_cents=int(payout_full_cents),
                )
        except Exception as exc:
            logger.warning("Capture not performed for booking %s: %s", booking_id, exc)
            results["error"] = str(exc)

    def _execute_under_12h_payout_transfer(
        self,
        ctx: Dict[str, Any],
        stripe_service: Any,
        results: Dict[str, Any],
        *,
        payout_full_cents: int,
    ) -> None:
        booking_id = ctx["booking_id"]
        payout_amount_cents = int(round(payout_full_cents * 0.5))
        results["payout_amount_cents"] = payout_amount_cents
        if payout_amount_cents <= 0:
            results["payout_success"] = True
            return

        destination_account_id = ctx.get("instructor_stripe_account_id")
        if not destination_account_id:
            results["payout_failed"] = True
            results["error"] = "missing_instructor_account"
            return
        try:
            transfer_result = stripe_service.create_manual_transfer(
                booking_id=booking_id,
                destination_account_id=destination_account_id,
                amount_cents=payout_amount_cents,
                idempotency_key=f"payout_lt12_{booking_id}",
            )
            results["payout_success"] = True
            results["payout_transfer_id"] = transfer_result.get("transfer_id")
        except Exception as exc:
            results["payout_failed"] = True
            results["error"] = str(exc)
