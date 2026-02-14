"""
Integration tests for admin refund idempotency keys.
"""

from decimal import Decimal
from unittest.mock import patch

from app.models.booking import Booking
from app.models.booking_payment import BookingPayment
from app.services.admin_booking_service import AdminBookingService


def _prepare_booking_for_refund(db, booking):
    booking_id = booking.id
    bp = db.query(BookingPayment).filter_by(booking_id=booking_id).first()
    if bp is None:
        bp = BookingPayment(booking_id=booking_id)
        db.add(bp)
    bp.payment_intent_id = bp.payment_intent_id or "pi_test_admin_refund"
    bp.payment_status = "settled"
    db.commit()
    # Evict the booking (and its payment satellite) from the identity map
    # so that subsequent queries with selectinload properly populate the
    # noload payment_detail relationship.
    db.expunge(bp)
    db.expunge(booking)
    from sqlalchemy.orm import selectinload

    booking = (
        db.query(Booking)
        .options(selectinload(Booking.payment_detail))
        .filter(Booking.id == booking_id)
        .first()
    )
    return booking


@patch("app.services.stripe_service.StripeService.refund_payment")
def test_admin_refund_uses_deterministic_idempotency_key(
    mock_refund_payment,
    client,
    db,
    test_booking,
    auth_headers_admin,
):
    booking = _prepare_booking_for_refund(db, test_booking)
    amount_cents = int(Decimal(str(booking.total_price)) * 100)
    mock_refund_payment.return_value = {
        "refund_id": "re_test_123",
        "amount_refunded": amount_cents,
    }

    response = client.post(
        f"/api/v1/admin/bookings/{booking.id}/refund",
        json={"reason": "platform_error"},
        headers=auth_headers_admin,
    )

    assert response.status_code == 200
    mock_refund_payment.assert_called_once()
    assert (
        mock_refund_payment.call_args.kwargs["idempotency_key"]
        == f"admin_refund_{booking.id}_{amount_cents}"
    )


@patch("app.services.stripe_service.StripeService.refund_payment")
def test_admin_cancel_refund_uses_deterministic_idempotency_key(
    mock_refund_payment,
    db,
    test_booking,
):
    booking = _prepare_booking_for_refund(db, test_booking)
    amount_cents = 5000
    mock_refund_payment.return_value = {
        "refund_id": "re_admin_cancel",
        "amount_refunded": amount_cents,
    }

    service = AdminBookingService(db)
    service._issue_refund(booking=booking, amount_cents=amount_cents, reason="platform_error")

    mock_refund_payment.assert_called_once()
    assert (
        mock_refund_payment.call_args.kwargs["idempotency_key"]
        == f"admin_cancel_{booking.id}_{amount_cents}"
    )
