from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.models.booking import BookingStatus
from app.schemas.admin_refund import RefundReasonCode
from app.services.refund_policy_engine import RefundPolicyEngine, RefundPolicyResult


def test_refund_policy_result_from_payload_coerces_types_safely():
    payload = {
        "eligible": True,
        "reason": 123,
        "method": "credit",
        "policy_basis": None,
        "student_card_refund_cents": True,
        "student_credit_cents": 2.75,
        "instructor_payout_delta_cents": "not-an-int",
        "platform_fee_refunded_cents": "7",
    }

    result = RefundPolicyResult.from_payload(payload)

    assert result.eligible is True
    assert result.reason is None
    assert result.method == "credit"
    assert result.policy_basis == ""
    assert result.student_card_refund_cents == 1
    assert result.student_credit_cents == 2
    assert result.instructor_payout_delta_cents == 0
    assert result.platform_fee_refunded_cents == 7


def test_refund_policy_engine_rejects_non_refundable_payment_status():
    engine = RefundPolicyEngine()
    booking = SimpleNamespace(
        status=BookingStatus.CONFIRMED,
        payment_status="processing",
        booking_start_utc=datetime.now(timezone.utc) + timedelta(hours=30),
    )
    payment = SimpleNamespace(status="processing", amount=10000, application_fee=1000)

    result = engine.evaluate(booking, payment, RefundReasonCode.GOODWILL, requested_amount_cents=1000)

    assert result.eligible is False
    assert "cannot be refunded" in (result.reason or "")


def test_refund_policy_engine_rejects_missing_booking_start_time():
    engine = RefundPolicyEngine()
    booking = SimpleNamespace(
        status=BookingStatus.CONFIRMED,
        payment_status="authorized",
        booking_start_utc=None,
    )
    payment = SimpleNamespace(status="authorized", amount=10000, application_fee=1000)

    result = engine.evaluate(booking, payment, RefundReasonCode.GOODWILL, requested_amount_cents=2000)

    assert result.eligible is False
    assert result.policy_basis == "Booking start time missing"


def test_refund_policy_engine_handles_naive_start_time_for_window_logic():
    engine = RefundPolicyEngine()
    booking = SimpleNamespace(
        status=BookingStatus.CONFIRMED,
        payment_status="authorized",
        booking_start_utc=(datetime.now(timezone.utc) + timedelta(hours=18)).replace(tzinfo=None),
    )
    payment = SimpleNamespace(status="authorized", amount=10000, application_fee=1000)

    result = engine.evaluate(
        booking,
        payment,
        RefundReasonCode.GOODWILL,
        requested_amount_cents=3000,
    )

    assert result.eligible is True
    assert result.method == "credit"
    assert result.student_card_refund_cents == 0
    assert result.student_credit_cents == 3000


def test_refund_policy_engine_zero_gross_skips_platform_fee_proration():
    engine = RefundPolicyEngine()
    booking = SimpleNamespace(
        status=BookingStatus.CONFIRMED,
        payment_status="authorized",
        booking_start_utc=datetime.now(timezone.utc) + timedelta(hours=30),
    )
    payment = SimpleNamespace(status="authorized", amount=0, application_fee=500)

    result = engine.evaluate(
        booking,
        payment,
        RefundReasonCode.GOODWILL,
        requested_amount_cents=1200,
    )

    assert result.eligible is True
    assert result.platform_fee_refunded_cents == 0
    assert result.instructor_payout_delta_cents == -1200
