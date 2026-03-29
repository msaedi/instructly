from __future__ import annotations

import logging
from types import ModuleType
from typing import TYPE_CHECKING, Any, Dict, Optional

from ...models.booking import Booking, PaymentStatus

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from ...models.booking_transfer import BookingTransfer
    from ...repositories.booking_repository import BookingRepository

logger = logging.getLogger(__name__)


def _booking_service_module() -> ModuleType:
    from .. import booking_service as booking_service_module

    return booking_service_module


class BookingCancellationFinalizeMixin:
    if TYPE_CHECKING:
        db: Session
        repository: BookingRepository

        def _ensure_transfer_record(self, booking_id: str) -> BookingTransfer:
            ...

        def _finalize_between_12_24h_cancellation(
            self,
            booking: Booking,
            ctx: Dict[str, Any],
            stripe_results: Dict[str, Any],
            payment_repo: Any,
            credit_service: Any,
            bp: Any,
        ) -> None:
            ...

        def _finalize_under_12h_cancellation(
            self,
            booking: Booking,
            ctx: Dict[str, Any],
            stripe_results: Dict[str, Any],
            payment_repo: Any,
            credit_service: Any,
            bp: Any,
        ) -> None:
            ...

    def _finalize_cancellation(
        self,
        booking: Booking,
        ctx: Dict[str, Any],
        stripe_results: Dict[str, Any],
        payment_repo: Any,
    ) -> None:
        """Finalize cancellation with Stripe results."""
        from ..credit_service import CreditService

        scenario = ctx["scenario"]
        credit_service = CreditService(self.db)
        bp = self.repository.ensure_payment(booking.id)
        if scenario == "over_24h_gaming":
            self._finalize_over_24h_gaming_cancellation(
                booking, ctx, stripe_results, payment_repo, credit_service, bp
            )
        elif scenario == "over_24h_regular":
            self._finalize_over_24h_regular_cancellation(
                booking, ctx, stripe_results, payment_repo, credit_service, bp
            )
        elif scenario == "between_12_24h":
            self._finalize_between_12_24h_cancellation(
                booking, ctx, stripe_results, payment_repo, credit_service, bp
            )
        elif scenario == "under_12h":
            self._finalize_under_12h_cancellation(
                booking, ctx, stripe_results, payment_repo, credit_service, bp
            )
        elif scenario == "under_12h_no_pi":
            self._finalize_under_12h_no_pi_cancellation(
                booking, ctx, payment_repo, credit_service, bp
            )
        elif scenario == "pending_payment":
            self._finalize_pending_payment_cancellation(
                booking, ctx, payment_repo, credit_service, bp
            )
        elif scenario in ("instructor_cancel_over_24h", "instructor_cancel_under_24h"):
            self._finalize_instructor_cancellation(
                booking, ctx, stripe_results, payment_repo, credit_service, bp
            )

    def _cancellation_credit_already_issued(self, payment_repo: Any, booking_id: str) -> bool:
        booking_service_module = _booking_service_module()
        try:
            credits = payment_repo.get_credits_issued_for_source(booking_id)
        except Exception as exc:
            logger.warning("Failed to check existing credits for booking %s: %s", booking_id, exc)
            return False
        cancellation_credit_reasons = booking_service_module.CANCELLATION_CREDIT_REASONS
        return any(
            getattr(credit, "reason", None) in cancellation_credit_reasons
            or getattr(credit, "source_type", None) in cancellation_credit_reasons
            for credit in credits
        )

    def _apply_cancellation_settlement(
        self,
        booking: Booking,
        bp: Any,
        outcome: str,
        *,
        student_credit_cents: Optional[int] = None,
        instructor_payout_cents: Optional[int] = None,
        refunded_cents: Optional[int] = None,
    ) -> None:
        bp.settlement_outcome = outcome
        booking.student_credit_amount = student_credit_cents
        bp.instructor_payout_amount = instructor_payout_cents
        booking.refunded_to_card_amount = refunded_cents

    def _mark_cancellation_capture_failed(self, bp: Any, error: Optional[str]) -> None:
        booking_service_module = _booking_service_module()
        bp.payment_status = PaymentStatus.PAYMENT_METHOD_REQUIRED.value
        bp.capture_failed_at = booking_service_module.datetime.now(
            booking_service_module.timezone.utc
        )
        bp.capture_retry_count = int(bp.capture_retry_count or 0) + 1
        if error:
            bp.auth_last_error = error
            bp.capture_error = error

    def _mark_cancellation_manual_review(self, bp: Any, reason: Optional[str]) -> None:
        bp.payment_status = PaymentStatus.MANUAL_REVIEW.value
        if reason:
            bp.auth_last_error = reason

    def _release_cancellation_reserved_credits(
        self, credit_service: Any, booking_id: str, bp: Any
    ) -> None:
        try:
            credit_service.release_credits_for_booking(booking_id=booking_id, use_transaction=False)
        except Exception as exc:
            logger.warning(
                "Failed to release reserved credits for booking %s: %s",
                booking_id,
                exc,
            )
        bp.credits_reserved_cents = 0

    def _forfeit_cancellation_reserved_credits(
        self, credit_service: Any, booking_id: str, bp: Any
    ) -> None:
        try:
            credit_service.forfeit_credits_for_booking(booking_id=booking_id, use_transaction=False)
        except Exception as exc:
            logger.warning(
                "Failed to forfeit reserved credits for booking %s: %s",
                booking_id,
                exc,
            )
        bp.credits_reserved_cents = 0

    def _record_cancellation_transfer_reversal_failure(
        self,
        *,
        booking_id: str,
        payment_intent_id: Optional[str],
        scenario: str,
        stripe_results: Dict[str, Any],
        payment_repo: Any,
        transfer_record: BookingTransfer,
        bp: Any,
        include_retry_metadata: bool,
    ) -> None:
        booking_service_module = _booking_service_module()
        payment_repo.create_payment_event(
            booking_id=booking_id,
            event_type="transfer_reversal_failed",
            event_data={"payment_intent_id": payment_intent_id, "scenario": scenario},
        )
        transfer_record.transfer_reversal_failed = True
        if include_retry_metadata:
            transfer_record.transfer_reversal_failed_at = booking_service_module.datetime.now(
                booking_service_module.timezone.utc
            )
            transfer_record.transfer_reversal_retry_count = (
                int(getattr(transfer_record, "transfer_reversal_retry_count", 0) or 0) + 1
            )
            transfer_record.transfer_reversal_error = stripe_results.get("error")
        self._mark_cancellation_manual_review(bp, "transfer_reversal_failed")
        logger.error(
            "Transfer reversal failed for booking %s; manual review required",
            booking_id,
        )

    def _issue_cancellation_credit_if_needed(
        self,
        *,
        payment_repo: Any,
        credit_service: Any,
        booking_id: str,
        user_id: str,
        amount_cents: int,
        source_type: str,
        reason: str,
    ) -> bool:
        if self._cancellation_credit_already_issued(payment_repo, booking_id):
            return False
        try:
            credit_service.issue_credit(
                user_id=user_id,
                amount_cents=amount_cents,
                source_type=source_type,
                reason=reason,
                source_booking_id=booking_id,
                use_transaction=False,
            )
        except Exception as exc:
            logger.error("Failed to create platform credit for booking %s: %s", booking_id, exc)
        return True

    def _finalize_over_24h_gaming_cancellation(
        self,
        booking: Booking,
        ctx: Dict[str, Any],
        stripe_results: Dict[str, Any],
        payment_repo: Any,
        credit_service: Any,
        bp: Any,
    ) -> None:
        booking_id = ctx["booking_id"]
        if not stripe_results["capture_success"]:
            payment_repo.create_payment_event(
                booking_id=booking_id,
                event_type="capture_failed_gaming_reschedule_cancel",
                event_data={
                    "payment_intent_id": ctx["payment_intent_id"],
                    "error": stripe_results.get("error"),
                },
            )
            self._mark_cancellation_capture_failed(bp, stripe_results.get("error"))
            return

        capture_data = stripe_results.get("capture_data") or {}
        transfer_record = self._ensure_transfer_record(booking_id)
        transfer_record.stripe_transfer_id = capture_data.get("transfer_id")
        if stripe_results.get("reverse_failed"):
            self._record_cancellation_transfer_reversal_failure(
                booking_id=booking_id,
                payment_intent_id=ctx["payment_intent_id"],
                scenario=ctx["scenario"],
                stripe_results=stripe_results,
                payment_repo=payment_repo,
                transfer_record=transfer_record,
                bp=bp,
                include_retry_metadata=True,
            )
            return
        if stripe_results.get("reverse_reversal_id"):
            transfer_record.transfer_reversal_id = stripe_results.get("reverse_reversal_id")

        credit_amount_cents = ctx["lesson_price_cents"]
        self._forfeit_cancellation_reserved_credits(credit_service, booking_id, bp)
        created_credit = self._issue_cancellation_credit_if_needed(
            payment_repo=payment_repo,
            credit_service=credit_service,
            booking_id=booking_id,
            user_id=ctx["student_id"],
            amount_cents=credit_amount_cents,
            source_type="cancel_credit_12_24",
            reason="Rescheduled booking cancellation (lesson price credit)",
        )
        if created_credit:
            payment_repo.create_payment_event(
                booking_id=booking_id,
                event_type="credit_created_gaming_reschedule_cancel",
                event_data={
                    "hours_before_new": round(ctx["hours_until"], 2),
                    "hours_from_original": round(ctx["hours_from_original"], 2)
                    if ctx["hours_from_original"] is not None
                    else None,
                    "lesson_price_cents": ctx["lesson_price_cents"],
                    "credit_issued_cents": credit_amount_cents,
                    "rescheduled_from": ctx["rescheduled_from_booking_id"],
                    "original_lesson_datetime": ctx["original_lesson_datetime"].isoformat()
                    if ctx["original_lesson_datetime"]
                    else None,
                },
            )
        bp.payment_status = PaymentStatus.SETTLED.value
        self._apply_cancellation_settlement(
            booking,
            bp,
            "student_cancel_12_24_full_credit",
            student_credit_cents=credit_amount_cents,
            instructor_payout_cents=0,
            refunded_cents=0,
        )

    def _finalize_over_24h_regular_cancellation(
        self,
        booking: Booking,
        ctx: Dict[str, Any],
        stripe_results: Dict[str, Any],
        payment_repo: Any,
        credit_service: Any,
        bp: Any,
    ) -> None:
        booking_id = ctx["booking_id"]
        self._release_cancellation_reserved_credits(credit_service, booking_id, bp)
        payment_repo.create_payment_event(
            booking_id=booking_id,
            event_type="auth_released",
            event_data={
                "hours_before": round(ctx["hours_until"], 2),
                "payment_intent_id": ctx["payment_intent_id"],
            },
        )
        if ctx.get("payment_intent_id") and not stripe_results.get("cancel_pi_success"):
            self._mark_cancellation_manual_review(bp, stripe_results.get("error"))
        else:
            bp.payment_status = PaymentStatus.SETTLED.value
        self._apply_cancellation_settlement(
            booking,
            bp,
            "student_cancel_gt24_no_charge",
            student_credit_cents=0,
            instructor_payout_cents=0,
            refunded_cents=0,
        )

    def _finalize_under_12h_no_pi_cancellation(
        self,
        booking: Booking,
        ctx: Dict[str, Any],
        payment_repo: Any,
        credit_service: Any,
        bp: Any,
    ) -> None:
        booking_id = ctx["booking_id"]
        self._release_cancellation_reserved_credits(credit_service, booking_id, bp)
        payment_repo.create_payment_event(
            booking_id=booking_id,
            event_type="capture_skipped_no_intent",
            event_data={"reason": "<12h cancellation without payment_intent"},
        )
        self._mark_cancellation_manual_review(bp, "missing_payment_intent")

    def _finalize_pending_payment_cancellation(
        self,
        booking: Booking,
        ctx: Dict[str, Any],
        payment_repo: Any,
        credit_service: Any,
        bp: Any,
    ) -> None:
        booking_id = ctx["booking_id"]
        self._release_cancellation_reserved_credits(credit_service, booking_id, bp)
        payment_repo.create_payment_event(
            booking_id=booking_id,
            event_type="cancelled_before_payment",
            event_data={"reason": "pending_payment_method"},
        )
        bp.payment_status = PaymentStatus.SETTLED.value
        self._apply_cancellation_settlement(
            booking,
            bp,
            "student_cancel_gt24_no_charge",
            student_credit_cents=0,
            instructor_payout_cents=0,
            refunded_cents=0,
        )

    def _finalize_instructor_cancellation(
        self,
        booking: Booking,
        ctx: Dict[str, Any],
        stripe_results: Dict[str, Any],
        payment_repo: Any,
        credit_service: Any,
        bp: Any,
    ) -> None:
        booking_id = ctx["booking_id"]
        self._release_cancellation_reserved_credits(credit_service, booking_id, bp)
        if stripe_results.get("refund_success"):
            self._finalize_instructor_refund_success(booking, ctx, stripe_results, payment_repo, bp)
        elif stripe_results.get("refund_failed"):
            transfer_record = self._ensure_transfer_record(booking_id)
            booking_service_module = _booking_service_module()
            transfer_record.refund_failed_at = booking_service_module.datetime.now(
                booking_service_module.timezone.utc
            )
            transfer_record.refund_error = stripe_results.get("error")
            transfer_record.refund_retry_count = (
                int(getattr(transfer_record, "refund_retry_count", 0) or 0) + 1
            )
            self._mark_cancellation_manual_review(bp, stripe_results.get("error"))
        elif stripe_results.get("cancel_pi_success") or not ctx.get("payment_intent_id"):
            self._finalize_instructor_cancelled_without_refund(booking, ctx, payment_repo, bp)
        else:
            payment_repo.create_payment_event(
                booking_id=booking_id,
                event_type="instructor_cancel_refund_failed",
                event_data={
                    "hours_before": round(ctx["hours_until"], 2),
                    "payment_intent_id": ctx["payment_intent_id"],
                    "error": stripe_results.get("error"),
                },
            )
            self._mark_cancellation_manual_review(bp, stripe_results.get("error"))

    def _finalize_instructor_refund_success(
        self,
        booking: Booking,
        ctx: Dict[str, Any],
        stripe_results: Dict[str, Any],
        payment_repo: Any,
        bp: Any,
    ) -> None:
        booking_id = ctx["booking_id"]
        refund_data = stripe_results.get("refund_data") or {}
        payment_repo.create_payment_event(
            booking_id=booking_id,
            event_type="instructor_cancel_refunded",
            event_data={
                "hours_before": round(ctx["hours_until"], 2),
                "payment_intent_id": ctx["payment_intent_id"],
                "refund_id": refund_data.get("refund_id"),
                "amount_refunded": refund_data.get("amount_refunded"),
            },
        )
        bp.payment_status = PaymentStatus.SETTLED.value
        transfer_record = self._ensure_transfer_record(booking_id)
        transfer_record.refund_id = refund_data.get("refund_id")
        refund_amount = refund_data.get("amount_refunded")
        if refund_amount is not None:
            try:
                refund_amount = int(refund_amount)
            except (TypeError, ValueError):
                refund_amount = None
        self._apply_cancellation_settlement(
            booking,
            bp,
            "instructor_cancel_full_refund",
            student_credit_cents=0,
            instructor_payout_cents=0,
            refunded_cents=refund_amount or 0,
        )

    def _finalize_instructor_cancelled_without_refund(
        self,
        booking: Booking,
        ctx: Dict[str, Any],
        payment_repo: Any,
        bp: Any,
    ) -> None:
        payment_repo.create_payment_event(
            booking_id=ctx["booking_id"],
            event_type="instructor_cancelled",
            event_data={
                "hours_before": round(ctx["hours_until"], 2),
                "payment_intent_id": ctx["payment_intent_id"],
            }
            if ctx.get("payment_intent_id")
            else {
                "hours_before": round(ctx["hours_until"], 2),
                "reason": "no_payment_intent",
            },
        )
        bp.payment_status = PaymentStatus.SETTLED.value
        self._apply_cancellation_settlement(
            booking,
            bp,
            "instructor_cancel_full_refund",
            student_credit_cents=0,
            instructor_payout_cents=0,
            refunded_cents=0,
        )
