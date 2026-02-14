from __future__ import annotations

from datetime import date, datetime, time, timezone
from decimal import Decimal
from types import SimpleNamespace

from app.models.booking import Booking, BookingStatus, LocationType, PaymentStatus


def _base_booking() -> Booking:
    booking = Booking(
        id="01ARZ3NDEKTSV4RRFFQ69G5FAV",
        student_id="01ARZ3NDEKTSV4RRFFQ69G5FAA",
        instructor_id="01ARZ3NDEKTSV4RRFFQ69G5FAB",
        instructor_service_id="01ARZ3NDEKTSV4RRFFQ69G5FAC",
        booking_date=date(2026, 1, 1),
        start_time=time(10, 0),
        end_time=time(11, 0),
        booking_start_utc=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
        booking_end_utc=datetime(2026, 1, 1, 11, 0, tzinfo=timezone.utc),
        service_name="Piano Lesson",
        hourly_rate=Decimal("50.00"),
        total_price=Decimal("50.00"),
        duration_minutes=60,
        status=BookingStatus.CONFIRMED,
        location_type=LocationType.ONLINE,
    )
    booking.created_at = datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc)
    booking.updated_at = datetime(2026, 1, 1, 9, 30, tzinfo=timezone.utc)
    return booking


def test_payment_status_missing_is_case_insensitive() -> None:
    assert PaymentStatus("AUTHORIZED") == PaymentStatus.AUTHORIZED
    assert PaymentStatus("settled") == PaymentStatus.SETTLED


def test_booking_helpers_cover_past_and_modifiable_checks() -> None:
    booking = _base_booking()

    assert booking.is_past(date(2026, 1, 2)) is True
    assert booking.is_past(date(2025, 12, 31)) is False

    can_modify = booking.can_be_modified_by
    assert can_modify(booking.student_id) is True
    assert can_modify(booking.instructor_id) is True
    assert can_modify("01ARZ3NDEKTSV4RRFFQ69G5FZZ") is False


def test_booking_to_dict_includes_lock_dispute_and_transfer_satellites() -> None:
    booking = _base_booking()

    booking.__dict__["lock_detail"] = SimpleNamespace(
        locked_at=datetime(2026, 1, 1, 9, 45, tzinfo=timezone.utc),
        locked_amount_cents=5000,
        lock_resolved_at=datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
        lock_resolution="new_lesson_completed",
    )
    booking.__dict__["dispute"] = SimpleNamespace(
        dispute_id="dp_123",
        dispute_status="won",
        dispute_amount=5000,
        dispute_created_at=datetime(2026, 1, 2, 10, 0, tzinfo=timezone.utc),
        dispute_resolved_at=datetime(2026, 1, 4, 10, 0, tzinfo=timezone.utc),
    )
    booking.__dict__["transfer"] = SimpleNamespace(
        stripe_transfer_id="tr_123",
        transfer_failed_at=datetime(2026, 1, 2, 11, 0, tzinfo=timezone.utc),
        transfer_error="network_error",
        transfer_retry_count=2,
        transfer_reversed=True,
        transfer_reversal_id="trr_123",
        transfer_reversal_failed=False,
        transfer_reversal_error=None,
        transfer_reversal_failed_at=datetime(2026, 1, 2, 12, 0, tzinfo=timezone.utc),
        transfer_reversal_retry_count=1,
        refund_id="re_123",
        refund_failed_at=datetime(2026, 1, 3, 11, 0, tzinfo=timezone.utc),
        refund_error="temporary_error",
        refund_retry_count=3,
        payout_transfer_id="po_123",
        advanced_payout_transfer_id="po_adv_123",
        payout_transfer_failed_at=datetime(2026, 1, 3, 12, 0, tzinfo=timezone.utc),
        payout_transfer_error="bank_error",
        payout_transfer_retry_count=4,
    )

    payload = booking.to_dict()

    assert payload["locked_amount_cents"] == 5000
    assert payload["lock_resolution"] == "new_lesson_completed"

    assert payload["dispute_id"] == "dp_123"
    assert payload["dispute_status"] == "won"
    assert payload["dispute_amount"] == 5000

    assert payload["stripe_transfer_id"] == "tr_123"
    assert payload["transfer_error"] == "network_error"
    assert payload["transfer_reversed"] is True
    assert payload["transfer_reversal_id"] == "trr_123"
    assert payload["refund_id"] == "re_123"
    assert payload["payout_transfer_id"] == "po_123"
    assert payload["advanced_payout_transfer_id"] == "po_adv_123"
