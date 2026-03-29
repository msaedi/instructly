from __future__ import annotations

from types import ModuleType
from typing import TYPE_CHECKING, Any, Dict, Optional

from ...models.booking import Booking, PaymentStatus

if TYPE_CHECKING:
    from ...models.booking_transfer import BookingTransfer


def _booking_service_module() -> ModuleType:
    from .. import booking_service as booking_service_module

    return booking_service_module


class BookingCancellationLateFinalizeMixin:
    if TYPE_CHECKING:

        def _ensure_transfer_record(self, booking_id: str) -> BookingTransfer:
            ...

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
            ...

        def _mark_cancellation_capture_failed(self, bp: Any, error: Optional[str]) -> None:
            ...

        def _forfeit_cancellation_reserved_credits(
            self, credit_service: Any, booking_id: str, bp: Any
        ) -> None:
            ...

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
            ...

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
            ...

        def _mark_cancellation_manual_review(self, bp: Any, reason: Optional[str]) -> None:
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
        booking_id = ctx["booking_id"]
        capture_data = stripe_results.get("capture_data") or {}
        transfer_record = self._ensure_transfer_record(booking_id)
        transfer_record.stripe_transfer_id = capture_data.get("transfer_id")
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
            if stripe_results.get("reverse_reversal_id"):
                transfer_record.transfer_reversal_id = stripe_results.get("reverse_reversal_id")

        if not stripe_results["capture_success"]:
            payment_repo.create_payment_event(
                booking_id=booking_id,
                event_type="capture_failed_late_cancel",
                event_data={
                    "payment_intent_id": ctx["payment_intent_id"],
                    "error": stripe_results.get("error"),
                },
            )
            self._mark_cancellation_capture_failed(bp, stripe_results.get("error"))
            return

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

        credit_amount_cents = ctx["lesson_price_cents"]
        self._forfeit_cancellation_reserved_credits(credit_service, booking_id, bp)
        created_credit = self._issue_cancellation_credit_if_needed(
            payment_repo=payment_repo,
            credit_service=credit_service,
            booking_id=booking_id,
            user_id=ctx["student_id"],
            amount_cents=credit_amount_cents,
            source_type="cancel_credit_12_24",
            reason="Cancellation 12-24 hours before lesson (lesson price credit)",
        )
        if created_credit:
            payment_repo.create_payment_event(
                booking_id=booking_id,
                event_type="credit_created_late_cancel",
                event_data={
                    "amount": credit_amount_cents,
                    "lesson_price_cents": ctx["lesson_price_cents"],
                    "total_charged_cents": capture_data.get("amount_received"),
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

    def _finalize_under_12h_cancellation(
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
                event_type="capture_failed_last_minute_cancel",
                event_data={"payment_intent_id": ctx["payment_intent_id"]},
            )
            self._mark_cancellation_capture_failed(bp, stripe_results.get("error"))
            return

        capture_data = stripe_results.get("capture_data") or {}
        transfer_record = self._ensure_transfer_record(booking_id)
        transfer_record.stripe_transfer_id = capture_data.get("transfer_id")
        payment_repo.create_payment_event(
            booking_id=booking_id,
            event_type="captured_last_minute_cancel",
            event_data={
                "payment_intent_id": ctx["payment_intent_id"],
                "amount": capture_data.get("amount_received"),
            },
        )
        if self._finalize_under_12h_transfer_outcome(
            ctx, stripe_results, payment_repo, transfer_record, bp, capture_data
        ):
            return
        self._finalize_under_12h_credit_and_payout(
            booking,
            ctx,
            stripe_results,
            payment_repo,
            credit_service,
            transfer_record,
            bp,
            capture_data,
        )

    def _finalize_under_12h_transfer_outcome(
        self,
        ctx: Dict[str, Any],
        stripe_results: Dict[str, Any],
        payment_repo: Any,
        transfer_record: BookingTransfer,
        bp: Any,
        capture_data: Dict[str, Any],
    ) -> bool:
        booking_id = ctx["booking_id"]
        if stripe_results.get("reverse_failed"):
            self._record_cancellation_transfer_reversal_failure(
                booking_id=booking_id,
                payment_intent_id=ctx["payment_intent_id"],
                scenario=ctx["scenario"],
                stripe_results=stripe_results,
                payment_repo=payment_repo,
                transfer_record=transfer_record,
                bp=bp,
                include_retry_metadata=False,
            )
            return True
        if stripe_results.get("reverse_success"):
            payment_repo.create_payment_event(
                booking_id=booking_id,
                event_type="transfer_reversed_last_minute_cancel",
                event_data={
                    "transfer_id": capture_data.get("transfer_id"),
                    "amount": capture_data.get("transfer_amount"),
                    "original_charge_amount": capture_data.get("amount_received"),
                },
            )
            if stripe_results.get("reverse_reversal_id"):
                transfer_record.transfer_reversal_id = stripe_results.get("reverse_reversal_id")
        return False

    def _finalize_under_12h_credit_and_payout(
        self,
        booking: Booking,
        ctx: Dict[str, Any],
        stripe_results: Dict[str, Any],
        payment_repo: Any,
        credit_service: Any,
        transfer_record: BookingTransfer,
        bp: Any,
        capture_data: Dict[str, Any],
    ) -> None:
        booking_id = ctx["booking_id"]
        if stripe_results.get("payout_failed"):
            self._record_under_12h_payout_failure(
                booking_id,
                stripe_results,
                payment_repo,
                transfer_record,
                bp,
                ctx["payment_intent_id"],
            )
        if stripe_results.get("payout_success"):
            payment_repo.create_payment_event(
                booking_id=booking_id,
                event_type="payout_created_last_minute_cancel",
                event_data={
                    "transfer_id": stripe_results.get("payout_transfer_id"),
                    "payout_amount_cents": stripe_results.get("payout_amount_cents"),
                },
            )
            transfer_record.payout_transfer_id = stripe_results.get("payout_transfer_id")
        credit_return_cents = int(round(ctx["lesson_price_cents"] * 0.5))
        self._forfeit_cancellation_reserved_credits(credit_service, booking_id, bp)
        created_credit = self._issue_cancellation_credit_if_needed(
            payment_repo=payment_repo,
            credit_service=credit_service,
            booking_id=booking_id,
            user_id=ctx["student_id"],
            amount_cents=credit_return_cents,
            source_type="cancel_credit_lt12",
            reason="Cancellation <12 hours before lesson (50% lesson price credit)",
        )
        if created_credit:
            payment_repo.create_payment_event(
                booking_id=booking_id,
                event_type="credit_created_last_minute_cancel",
                event_data={
                    "amount": credit_return_cents,
                    "lesson_price_cents": ctx["lesson_price_cents"],
                    "total_charged_cents": capture_data.get("amount_received"),
                    "payout_amount_cents": stripe_results.get("payout_amount_cents"),
                },
            )
        if bp.payment_status != PaymentStatus.MANUAL_REVIEW.value:
            bp.payment_status = PaymentStatus.SETTLED.value
        payout_amount_cents = stripe_results.get("payout_amount_cents")
        if payout_amount_cents is not None:
            try:
                payout_amount_cents = int(payout_amount_cents)
            except (TypeError, ValueError):
                payout_amount_cents = None
        self._apply_cancellation_settlement(
            booking,
            bp,
            "student_cancel_lt12_split_50_50",
            student_credit_cents=credit_return_cents,
            instructor_payout_cents=payout_amount_cents or 0,
            refunded_cents=0,
        )

    def _record_under_12h_payout_failure(
        self,
        booking_id: str,
        stripe_results: Dict[str, Any],
        payment_repo: Any,
        transfer_record: BookingTransfer,
        bp: Any,
        payment_intent_id: Optional[str],
    ) -> None:
        booking_service_module = _booking_service_module()
        payment_repo.create_payment_event(
            booking_id=booking_id,
            event_type="payout_failed_last_minute_cancel",
            event_data={
                "payment_intent_id": payment_intent_id,
                "payout_amount_cents": stripe_results.get("payout_amount_cents"),
                "error": stripe_results.get("error"),
            },
        )
        transfer_record.payout_transfer_failed_at = booking_service_module.datetime.now(
            booking_service_module.timezone.utc
        )
        transfer_record.payout_transfer_error = stripe_results.get("error")
        transfer_record.payout_transfer_retry_count = (
            int(getattr(transfer_record, "payout_transfer_retry_count", 0) or 0) + 1
        )
        transfer_record.transfer_failed_at = transfer_record.payout_transfer_failed_at
        transfer_record.transfer_error = transfer_record.payout_transfer_error
        transfer_record.transfer_retry_count = (
            int(getattr(transfer_record, "transfer_retry_count", 0) or 0) + 1
        )
        self._mark_cancellation_manual_review(bp, stripe_results.get("error"))
