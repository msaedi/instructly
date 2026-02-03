from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.models.payment import PaymentEvent
from app.services import admin_ops_service
from app.services.admin_ops_service import AdminOpsService


class _Intent(SimpleNamespace):
    pass


class _Booking(SimpleNamespace):
    pass


def test_helper_coercions_and_redaction():
    assert admin_ops_service._coerce_int(None) is None
    assert admin_ops_service._coerce_int("12") == 12
    assert admin_ops_service._coerce_int("bad") is None

    assert admin_ops_service._coerce_float(None) is None
    assert admin_ops_service._coerce_float("3.5") == 3.5
    assert admin_ops_service._coerce_float("bad") is None

    assert admin_ops_service._redact_stripe_id(None) is None
    assert admin_ops_service._redact_stripe_id(1234) is None
    assert admin_ops_service._redact_stripe_id("") is None
    assert admin_ops_service._redact_stripe_id("pi_1234567890") == "pi_...7890"
    assert admin_ops_service._redact_stripe_id("1234") == "1234"


def test_extract_amount_cents_prefers_first_valid_key():
    assert admin_ops_service._extract_amount_cents({"amount_cents": "bad"}) is None

    event_data = {
        "amount_cents": "bad",
        "amount_refunded": 1500,
    }
    assert admin_ops_service._extract_amount_cents(event_data) == 1500


def test_infer_failure_category_handles_hints_and_unknown():
    assert (
        admin_ops_service._infer_failure_category("auth_failed", {"error_type": "Card Declined"})
        == "card_declined"
    )
    assert (
        admin_ops_service._infer_failure_category(
            "capture_failed", {"error": "Processing error from stripe"}
        )
        == "processing_error"
    )
    assert (
        admin_ops_service._infer_failure_category("payment_fail", {})
        == "unknown_error"
    )


def test_is_successful_charge_variants():
    assert admin_ops_service._is_successful_charge("capture_failed") is False
    assert admin_ops_service._is_successful_charge("payment_captured") is True
    assert admin_ops_service._is_successful_charge("reauth_and_capture_success") is True
    assert admin_ops_service._is_successful_charge("already_done") is False


def test_payment_amount_resolution_branches(db):
    service = AdminOpsService(db)

    intent = _Intent(amount=10000, application_fee=1000, instructor_payout_cents=7000)
    booking = _Booking(payment_intent=intent, total_price=None)

    assert service._resolve_gross_cents(booking, credits_applied_cents=500) == 10500
    assert service._resolve_platform_fee_cents(booking) == 1000
    assert service._resolve_instructor_payout_cents(booking, platform_fee_cents=1000) == 7000

    intent_no_payout = _Intent(amount=9000, application_fee=None, instructor_payout_cents=None)
    booking_fallback = _Booking(payment_intent=intent_no_payout, total_price=None)
    assert service._resolve_instructor_payout_cents(booking_fallback, platform_fee_cents=0) == 9000

    booking_missing_total = _Booking(payment_intent=None, total_price=None)
    assert service._resolve_gross_cents(booking_missing_total, credits_applied_cents=2500) == 2500

    booking_bad_total = _Booking(payment_intent=None, total_price="not-a-number")
    assert service._resolve_gross_cents(booking_bad_total, credits_applied_cents=1500) == 1500


def test_build_status_timeline_settled_includes_state(db):
    service = AdminOpsService(db)
    booking = _Booking(payment_status="settled", updated_at=datetime(2026, 2, 1, tzinfo=timezone.utc))

    timeline = service._build_status_timeline(booking, [])

    assert timeline
    assert timeline[-1]["state"] == "settled"


def test_build_provider_refs_and_refunds(db):
    service = AdminOpsService(db)
    booking = _Booking(payment_intent_id="pi_1234567890")

    events = [
        PaymentEvent(
            booking_id="01BK",
            event_type="refund_failed",
            event_data={"refund_id": "re_1234", "amount_refunded": 1500},
            created_at=datetime.now(timezone.utc),
        ),
        PaymentEvent(
            booking_id="01BK",
            event_type="refund_refunded",
            event_data={"refund_id": "re_5678", "refund_amount_cents": 2000},
            created_at=datetime.now(timezone.utc),
        ),
        PaymentEvent(
            booking_id="01BK",
            event_type="payment_captured",
            event_data={"charge_id": "ch_9876"},
            created_at=datetime.now(timezone.utc),
        ),
    ]

    refs = service._build_provider_refs(booking, events)
    assert refs["payment_intent"].endswith("7890")
    assert refs["charge"].endswith("9876")

    refunds = service._build_refunds(events)
    statuses = {refund["status"] for refund in refunds}
    assert "failed" in statuses
    assert "succeeded" in statuses
    assert any(refund["amount"] == 20.0 for refund in refunds)


def test_detect_double_charge_across_bookings_and_skips_missing_amount(db):
    service = AdminOpsService(db)
    now = datetime.now(timezone.utc)

    grouped = {
        "bk_1": [
            PaymentEvent(
                booking_id="bk_1",
                event_type="payment_captured",
                event_data={},
                created_at=now,
            ),
            PaymentEvent(
                booking_id="bk_1",
                event_type="payment_captured",
                event_data={"amount_captured_cents": 5000},
                created_at=now,
            ),
        ],
        "bk_2": [
            PaymentEvent(
                booking_id="bk_2",
                event_type="payment_captured",
                event_data={"amount_captured_cents": 5000},
                created_at=now + timedelta(minutes=4),
            )
        ],
    }

    assert service._detect_double_charge(grouped) is True


def test_query_payment_timeline_skips_missing_booking(db):
    service = AdminOpsService(db)

    event = PaymentEvent(
        booking_id="bk_missing",
        event_type="auth_succeeded",
        event_data={"amount_cents": 1000},
        created_at=datetime.now(timezone.utc),
    )
    event.booking = None

    class _Repo:
        def get_payment_events_for_booking(self, *_args, **_kwargs):
            return [event]

    service.payment_repository = _Repo()

    result = service._query_payment_timeline(
        booking_id="bk_missing",
        user_id=None,
        start_time=datetime.now(timezone.utc) - timedelta(hours=1),
        end_time=datetime.now(timezone.utc) + timedelta(hours=1),
    )

    assert result["payments"] == []
    assert result["total_count"] == 0


def test_get_period_dates_custom_branch(monkeypatch, db):
    service = AdminOpsService(db)
    monkeypatch.setattr(AdminOpsService, "VALID_PERIODS", {"custom"})

    start, end = service._get_period_dates("custom")

    assert start == end
