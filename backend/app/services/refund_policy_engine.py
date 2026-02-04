"""Refund policy evaluation logic for MCP refunds."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from app.models.booking import Booking, BookingStatus
from app.models.payment import PaymentIntent
from app.schemas.admin_refund import RefundReasonCode


@dataclass(frozen=True)
class RefundPolicyResult:
    eligible: bool
    reason: str | None = None
    method: str | None = None
    policy_basis: str = ""
    student_card_refund_cents: int = 0
    student_credit_cents: int = 0
    instructor_payout_delta_cents: int = 0
    platform_fee_refunded_cents: int = 0

    def to_payload(self) -> dict[str, object]:
        return {
            "eligible": self.eligible,
            "reason": self.reason,
            "method": self.method,
            "policy_basis": self.policy_basis,
            "student_card_refund_cents": int(self.student_card_refund_cents),
            "student_credit_cents": int(self.student_credit_cents),
            "instructor_payout_delta_cents": int(self.instructor_payout_delta_cents),
            "platform_fee_refunded_cents": int(self.platform_fee_refunded_cents),
        }

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> "RefundPolicyResult":
        def _coerce_str(value: object | None) -> str | None:
            return value if isinstance(value, str) else None

        def _coerce_int(value: object | None) -> int:
            if isinstance(value, bool):
                return int(value)
            if isinstance(value, int):
                return value
            if isinstance(value, float):
                return int(value)
            if isinstance(value, str):
                try:
                    return int(value)
                except ValueError:
                    return 0
            return 0

        return cls(
            eligible=bool(payload.get("eligible")),
            reason=_coerce_str(payload.get("reason")),
            method=_coerce_str(payload.get("method")),
            policy_basis=_coerce_str(payload.get("policy_basis")) or "",
            student_card_refund_cents=_coerce_int(payload.get("student_card_refund_cents")),
            student_credit_cents=_coerce_int(payload.get("student_credit_cents")),
            instructor_payout_delta_cents=_coerce_int(payload.get("instructor_payout_delta_cents")),
            platform_fee_refunded_cents=_coerce_int(payload.get("platform_fee_refunded_cents")),
        )


class RefundPolicyEngine:
    """Determines refund eligibility and method based on business rules."""

    def evaluate(
        self,
        booking: Booking,
        payment: PaymentIntent,
        reason_code: RefundReasonCode,
        requested_amount_cents: int,
    ) -> RefundPolicyResult:
        payment_status = (booking.payment_status or payment.status or "").lower()
        if payment_status not in {"authorized", "captured", "settled"}:
            return RefundPolicyResult(
                eligible=False,
                reason=f"Payment status '{payment_status or 'unknown'}' cannot be refunded",
                policy_basis="Payment not refundable in current status",
            )

        if (
            booking.status == BookingStatus.COMPLETED
            and reason_code == RefundReasonCode.CANCEL_POLICY
        ):
            return RefundPolicyResult(
                eligible=False,
                reason="Completed lessons cannot be refunded under cancellation policy",
                policy_basis="Completed lessons are not eligible for cancellation refunds",
            )

        if not booking.booking_start_utc:
            return RefundPolicyResult(
                eligible=False,
                reason="Booking start time unavailable for refund policy evaluation",
                policy_basis="Booking start time missing",
            )

        now = datetime.now(timezone.utc)
        scheduled_start = booking.booking_start_utc
        if scheduled_start.tzinfo is None:
            scheduled_start = scheduled_start.replace(tzinfo=timezone.utc)
        hours_before_lesson = (scheduled_start - now).total_seconds() / 3600

        method = "card"
        policy_basis = ""
        student_card_refund_cents = requested_amount_cents
        student_credit_cents = 0

        if hours_before_lesson >= 24:
            method = "card"
            policy_basis = ">=24 hours before lesson: full card refund"
            student_card_refund_cents = requested_amount_cents
            student_credit_cents = 0
        elif 12 <= hours_before_lesson < 24:
            method = "credit"
            policy_basis = "12-24 hours before lesson: 100% lesson credit (no card refund)"
            student_card_refund_cents = 0
            student_credit_cents = requested_amount_cents
        else:
            method = "credit"
            policy_basis = "<12 hours before lesson: 50% lesson credit"
            student_card_refund_cents = 0
            student_credit_cents = int(round(requested_amount_cents * 0.5))

        if reason_code in {
            RefundReasonCode.DUPLICATE,
            RefundReasonCode.INSTRUCTOR_NO_SHOW,
        }:
            method = "card"
            policy_basis = f"{reason_code.value}: full card refund (policy override)"
            student_card_refund_cents = requested_amount_cents
            student_credit_cents = 0

        platform_fee_cents = int(payment.application_fee or 0)
        gross_cents = int(payment.amount or 0)
        platform_fee_portion = 0
        if gross_cents > 0 and platform_fee_cents > 0:
            platform_fee_portion = int(
                round(platform_fee_cents * (requested_amount_cents / gross_cents))
            )

        instructor_payout_delta_cents = -1 * max(0, requested_amount_cents - platform_fee_portion)
        platform_fee_refunded_cents = platform_fee_portion if student_card_refund_cents > 0 else 0

        return RefundPolicyResult(
            eligible=True,
            method=method,
            policy_basis=policy_basis,
            student_card_refund_cents=student_card_refund_cents,
            student_credit_cents=student_credit_cents,
            instructor_payout_delta_cents=instructor_payout_delta_cents,
            platform_fee_refunded_cents=platform_fee_refunded_cents,
        )
