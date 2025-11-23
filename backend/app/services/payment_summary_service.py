"""Helpers to compute student-facing payment summaries for bookings."""

from __future__ import annotations

from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Dict, Optional, Tuple

from app.models.booking import Booking
from app.repositories.payment_repository import PaymentRepository
from app.repositories.review_repository import ReviewTipRepository
from app.schemas.booking import PaymentSummary

SUCCESSFUL_TIP_STATUSES = {"succeeded", "processing"}


def _to_cents(value: Any) -> int:
    if value is None:
        return 0
    dec_value = Decimal(str(value))
    cents = dec_value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) * 100
    return int(cents.to_integral_value(rounding=ROUND_HALF_UP))


def _credit_applied_cents(payment_repo: PaymentRepository, booking_id: str) -> int:
    credit_applied_cents = 0
    try:
        events = payment_repo.get_payment_events_for_booking(booking_id)
    except Exception:
        return 0

    for ev in events:
        if ev.event_type == "credits_applied":
            data = ev.event_data or {}
            credit_applied_cents = int(data.get("applied_cents", 0) or 0)
        elif credit_applied_cents == 0 and ev.event_type == "auth_succeeded_credits_only":
            data = ev.event_data or {}
            credit_applied_cents = int(
                data.get("credits_applied_cents", data.get("original_amount_cents", 0)) or 0
            )

    return max(0, credit_applied_cents)


def _resolve_tip_info(
    payment_repo: PaymentRepository,
    review_tip_repo: ReviewTipRepository,
    booking_id: str,
) -> Tuple[int, int, Optional[str], Optional[datetime]]:
    tip_record = None
    try:
        tip_record = review_tip_repo.get_by_booking_id(booking_id)
    except Exception:
        tip_record = None

    if not tip_record:
        return 0, 0, None, None

    tip_amount_cents = int(tip_record.amount_cents or 0)
    tip_status = tip_record.status
    tip_paid_cents = 0
    last_updated: Optional[datetime] = tip_record.processed_at

    payment = None
    if tip_record.stripe_payment_intent_id:
        try:
            payment = payment_repo.get_payment_by_intent_id(tip_record.stripe_payment_intent_id)
        except Exception:
            payment = None

    if payment is None and tip_amount_cents > 0:
        try:
            payment = payment_repo.find_payment_by_booking_and_amount(booking_id, tip_amount_cents)
        except Exception:
            payment = None

    if payment is not None:
        tip_status = payment.status or tip_status
        last_updated = payment.updated_at or payment.created_at or last_updated
        if (payment.status or "").lower() in SUCCESSFUL_TIP_STATUSES:
            tip_paid_cents = tip_amount_cents

    return tip_amount_cents, tip_paid_cents, tip_status, last_updated


def build_student_payment_summary(
    *,
    booking: Booking,
    pricing_config: Dict[str, Any],
    payment_repo: PaymentRepository,
    review_tip_repo: ReviewTipRepository,
) -> PaymentSummary:
    lesson_amount_cents = _to_cents(booking.total_price)
    student_fee_pct = Decimal(str(pricing_config.get("student_fee_pct", 0)))
    student_fee_cents = int(
        (Decimal(lesson_amount_cents) * student_fee_pct).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    )
    credit_cents = _credit_applied_cents(payment_repo, booking.id)
    subtotal_cents = max(0, lesson_amount_cents + student_fee_cents - credit_cents)

    tip_amount_cents, tip_paid_cents, tip_status, tip_updated = _resolve_tip_info(
        payment_repo,
        review_tip_repo,
        booking.id,
    )
    total_paid_cents = subtotal_cents + tip_paid_cents

    def _format_amount(cents: int) -> float:
        return float(Decimal(cents) / Decimal(100))

    return PaymentSummary(
        lesson_amount=_format_amount(lesson_amount_cents),
        service_fee=_format_amount(student_fee_cents),
        credit_applied=_format_amount(credit_cents),
        subtotal=_format_amount(subtotal_cents),
        tip_amount=_format_amount(tip_amount_cents),
        tip_paid=_format_amount(tip_paid_cents),
        total_paid=_format_amount(total_paid_cents),
        tip_status=tip_status,
        tip_last_updated=tip_updated.isoformat() if tip_updated else None,
    )
