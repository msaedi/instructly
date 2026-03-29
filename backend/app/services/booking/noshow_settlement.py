from __future__ import annotations

from types import ModuleType
from typing import TYPE_CHECKING, Any, Dict, Optional

from ...models.booking import Booking, PaymentStatus

if TYPE_CHECKING:
    from ...repositories.booking_repository import BookingRepository


def _booking_service_module() -> ModuleType:
    from .. import booking_service as booking_service_module

    return booking_service_module


class BookingNoShowSettlementMixin:
    if TYPE_CHECKING:
        repository: BookingRepository

        def _ensure_transfer_record(self, booking_id: str) -> Any:
            ...

    def _refund_for_instructor_no_show(
        self,
        *,
        stripe_service: Any,
        booking_id: str,
        payment_intent_id: Optional[str],
        payment_status: str,
    ) -> Dict[str, Any]:
        """Refund full amount for instructor no-show or release authorization."""
        result: Dict[str, Any] = {"refund_success": False, "cancel_success": False, "error": None}
        already_captured = payment_status in {
            PaymentStatus.SETTLED.value,
            PaymentStatus.LOCKED.value,
        }
        if not payment_intent_id:
            result["error"] = "missing_payment_intent"
            return result

        if already_captured:
            try:
                refund = stripe_service.refund_payment(
                    payment_intent_id,
                    reverse_transfer=True,
                    refund_application_fee=True,
                    idempotency_key=f"refund_instructor_noshow_{booking_id}",
                )
                result["refund_success"] = True
                result["refund_data"] = refund
            except Exception as exc:
                result["error"] = str(exc)
        else:
            try:
                stripe_service.cancel_payment_intent(
                    payment_intent_id,
                    idempotency_key=f"cancel_instructor_noshow_{booking_id}",
                )
                result["cancel_success"] = True
            except Exception as exc:
                result["error"] = str(exc)

        return result

    def _payout_for_student_no_show(
        self,
        *,
        stripe_service: Any,
        booking_id: str,
        payment_intent_id: Optional[str],
        payment_status: str,
    ) -> Dict[str, Any]:
        """Capture payment if needed for student no-show."""
        result: Dict[str, Any] = {
            "capture_success": False,
            "already_captured": False,
            "error": None,
        }
        already_captured = payment_status in {
            PaymentStatus.SETTLED.value,
            PaymentStatus.LOCKED.value,
        }
        if already_captured:
            result["already_captured"] = True
            return result
        if not payment_intent_id:
            result["error"] = "missing_payment_intent"
            return result

        try:
            capture = stripe_service.capture_payment_intent(
                payment_intent_id,
                idempotency_key=f"capture_student_noshow_{booking_id}",
            )
            result["capture_success"] = True
            result["capture_data"] = capture
        except Exception as exc:
            result["error"] = str(exc)

        return result

    def _finalize_instructor_no_show(
        self,
        *,
        booking: Booking,
        stripe_result: Dict[str, Any],
        credit_service: Any,
        refunded_cents: int,
        locked_booking_id: Optional[str],
    ) -> None:
        """Persist instructor no-show settlement."""
        booking_service_module = _booking_service_module()

        credit_service.release_credits_for_booking(booking_id=booking.id, use_transaction=False)
        bp = self.repository.ensure_payment(booking.id)
        bp.settlement_outcome = "instructor_no_show_full_refund"
        booking.student_credit_amount = 0
        bp.instructor_payout_amount = 0

        if locked_booking_id:
            booking.refunded_to_card_amount = 0
            bp.payment_status = (
                PaymentStatus.SETTLED.value
                if stripe_result.get("skipped") or stripe_result.get("success")
                else PaymentStatus.MANUAL_REVIEW.value
            )
            return

        refund_data = stripe_result.get("refund_data") or {}
        refund_amount = refund_data.get("amount_refunded")
        if refund_amount is not None:
            try:
                refund_amount = int(refund_amount)
            except (TypeError, ValueError):
                refund_amount = None
        booking.refunded_to_card_amount = (
            refund_amount if refund_amount is not None else refunded_cents
        )

        if stripe_result.get("refund_success") or stripe_result.get("cancel_success"):
            if stripe_result.get("refund_success"):
                transfer_record = self._ensure_transfer_record(booking.id)
                transfer_record.refund_id = refund_data.get("refund_id")
            bp.payment_status = PaymentStatus.SETTLED.value
        else:
            transfer_record = self._ensure_transfer_record(booking.id)
            transfer_record.refund_failed_at = booking_service_module.datetime.now(
                booking_service_module.timezone.utc
            )
            transfer_record.refund_error = stripe_result.get("error")
            transfer_record.refund_retry_count = (
                int(getattr(transfer_record, "refund_retry_count", 0) or 0) + 1
            )
            bp.payment_status = PaymentStatus.MANUAL_REVIEW.value

    def _finalize_student_no_show(
        self,
        *,
        booking: Booking,
        stripe_result: Dict[str, Any],
        credit_service: Any,
        payout_cents: int,
        locked_booking_id: Optional[str],
    ) -> None:
        """Persist student no-show settlement."""
        booking_service_module = _booking_service_module()

        credit_service.forfeit_credits_for_booking(booking_id=booking.id, use_transaction=False)
        bp = self.repository.ensure_payment(booking.id)
        bp.settlement_outcome = "student_no_show_full_payout"
        booking.student_credit_amount = 0
        booking.refunded_to_card_amount = 0

        if locked_booking_id:
            bp.instructor_payout_amount = 0
            bp.payment_status = (
                PaymentStatus.SETTLED.value
                if stripe_result.get("skipped") or stripe_result.get("success")
                else PaymentStatus.MANUAL_REVIEW.value
            )
            return

        bp.instructor_payout_amount = payout_cents
        if stripe_result.get("capture_success") or stripe_result.get("already_captured"):
            capture_data = stripe_result.get("capture_data") or {}
            if capture_data.get("transfer_id"):
                transfer_record = self._ensure_transfer_record(booking.id)
                transfer_record.stripe_transfer_id = capture_data.get("transfer_id")
            bp.payment_status = PaymentStatus.SETTLED.value
        else:
            bp.payment_status = PaymentStatus.PAYMENT_METHOD_REQUIRED.value
            bp.capture_failed_at = booking_service_module.datetime.now(
                booking_service_module.timezone.utc
            )
            bp.capture_retry_count = int(bp.capture_retry_count or 0) + 1
            bp.capture_error = stripe_result.get("error")
