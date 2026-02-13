from decimal import Decimal
from unittest.mock import patch

import ulid

from app.core.exceptions import ServiceException
from app.core.ulid_helper import generate_ulid
from app.models.audit_log import AuditLog
from app.models.booking import Booking
from app.models.booking_payment import BookingPayment


def _ensure_payment_detail(db, booking: Booking, **fields) -> BookingPayment:
    bp = db.query(BookingPayment).filter(BookingPayment.booking_id == booking.id).one_or_none()
    if bp is None:
        bp = BookingPayment(id=str(ulid.ULID()), booking_id=booking.id)
        db.add(bp)
    for key, value in fields.items():
        setattr(bp, key, value)
    db.flush()
    booking.payment_detail = bp
    return bp


def _prepare_booking_for_refund(db, booking: Booking) -> Booking:
    booking_id = booking.id
    bp = db.query(BookingPayment).filter(BookingPayment.booking_id == booking_id).one_or_none()
    existing_pi = bp.payment_intent_id if bp else None
    _ensure_payment_detail(
        db,
        booking,
        payment_intent_id=existing_pi or "pi_test_123",
        payment_status="settled",
    )
    db.commit()
    # Evict the booking (and its payment satellite) from the identity map
    # so the route's get_booking_with_details + selectinload can build a
    # fresh object with the noload payment_detail properly populated.
    if bp is not None:
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
def test_admin_can_refund_booking(
    mock_refund_payment,
    client,
    db,
    test_booking,
    auth_headers_admin,
):
    booking = _prepare_booking_for_refund(db, test_booking)
    expected_cents = int(Decimal(str(booking.total_price)) * 100)
    mock_refund_payment.return_value = {
        "refund_id": "re_test_123",
        "amount_refunded": expected_cents,
    }

    response = client.post(
        f"/api/v1/admin/bookings/{booking.id}/refund",
        json={"reason": "instructor_no_show", "note": "Instructor no-show"},
        headers=auth_headers_admin,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["refund_id"] == "re_test_123"
    assert data["amount_refunded_cents"] == expected_cents

    mock_refund_payment.assert_called_once()
    assert mock_refund_payment.call_args.kwargs["amount_cents"] == expected_cents

    db.refresh(booking)
    if booking.payment_detail is not None:
        db.refresh(booking.payment_detail)
    assert booking.payment_detail.payment_status == "settled"
    assert booking.payment_detail.settlement_outcome == "instructor_no_show_full_refund"


@patch("app.services.stripe_service.StripeService.refund_payment")
def test_admin_can_partial_refund(
    mock_refund_payment,
    client,
    db,
    test_booking,
    auth_headers_admin,
):
    booking = _prepare_booking_for_refund(db, test_booking)
    mock_refund_payment.return_value = {
        "refund_id": "re_partial",
        "amount_refunded": 5000,
    }

    response = client.post(
        f"/api/v1/admin/bookings/{booking.id}/refund",
        json={"reason": "dispute", "amount_cents": 5000},
        headers=auth_headers_admin,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["amount_refunded_cents"] == 5000
    assert mock_refund_payment.call_args.kwargs["amount_cents"] == 5000


def test_non_admin_cannot_refund(client, db, test_booking, auth_headers):
    booking = _prepare_booking_for_refund(db, test_booking)

    response = client.post(
        f"/api/v1/admin/bookings/{booking.id}/refund",
        json={"reason": "platform_error"},
        headers=auth_headers,
    )

    assert response.status_code == 403


def test_refund_nonexistent_booking(client, auth_headers_admin):
    response = client.post(
        f"/api/v1/admin/bookings/{generate_ulid()}/refund",
        json={"reason": "other"},
        headers=auth_headers_admin,
    )

    assert response.status_code == 404


def test_refund_already_refunded_booking(client, db, test_booking, auth_headers_admin):
    booking = _prepare_booking_for_refund(db, test_booking)
    _ensure_payment_detail(db, booking, payment_status="settled", settlement_outcome="admin_refund")
    booking.refunded_to_card_amount = 5000
    db.commit()

    response = client.post(
        f"/api/v1/admin/bookings/{booking.id}/refund",
        json={"reason": "dispute"},
        headers=auth_headers_admin,
    )

    assert response.status_code == 400
    assert "already refunded" in response.json()["detail"].lower()


def test_refund_rejects_booking_without_payment_intent(client, db, test_booking, auth_headers_admin):
    booking = _prepare_booking_for_refund(db, test_booking)
    _ensure_payment_detail(db, booking, payment_intent_id=None)
    db.commit()

    response = client.post(
        f"/api/v1/admin/bookings/{booking.id}/refund",
        json={"reason": "platform_error"},
        headers=auth_headers_admin,
    )

    assert response.status_code == 400
    assert "no payment" in response.json()["detail"].lower()


@patch("app.services.admin_refund_service.AdminRefundService.resolve_full_refund_cents")
def test_refund_rejects_when_resolved_amount_is_non_positive(
    mock_resolve_full_refund_cents,
    client,
    db,
    test_booking,
    auth_headers_admin,
):
    booking = _prepare_booking_for_refund(db, test_booking)
    mock_resolve_full_refund_cents.return_value = 0

    response = client.post(
        f"/api/v1/admin/bookings/{booking.id}/refund",
        json={"reason": "platform_error"},
        headers=auth_headers_admin,
    )

    assert response.status_code == 400
    assert "refundable amount" in response.json()["detail"].lower()


@patch("app.services.admin_refund_service.AdminRefundService.resolve_full_refund_cents")
def test_refund_rejects_amount_above_full_charge(
    mock_resolve_full_refund_cents,
    client,
    db,
    test_booking,
    auth_headers_admin,
):
    booking = _prepare_booking_for_refund(db, test_booking)
    mock_resolve_full_refund_cents.return_value = 1000

    response = client.post(
        f"/api/v1/admin/bookings/{booking.id}/refund",
        json={"reason": "other", "amount_cents": 1200},
        headers=auth_headers_admin,
    )

    assert response.status_code == 400
    assert "exceeds original charge" in response.json()["detail"].lower()


@patch("app.services.stripe_service.StripeService.refund_payment")
def test_refund_maps_service_exception_to_bad_gateway(
    mock_refund_payment,
    client,
    db,
    test_booking,
    auth_headers_admin,
):
    booking = _prepare_booking_for_refund(db, test_booking)
    mock_refund_payment.side_effect = ServiceException("Stripe unavailable")

    response = client.post(
        f"/api/v1/admin/bookings/{booking.id}/refund",
        json={"reason": "dispute"},
        headers=auth_headers_admin,
    )

    assert response.status_code == 502
    assert "stripe unavailable" in response.json()["detail"].lower()


@patch("app.services.stripe_service.StripeService.refund_payment")
def test_refund_maps_unexpected_exception_to_internal_error(
    mock_refund_payment,
    client,
    db,
    test_booking,
    auth_headers_admin,
):
    booking = _prepare_booking_for_refund(db, test_booking)
    mock_refund_payment.side_effect = RuntimeError("socket closed")

    response = client.post(
        f"/api/v1/admin/bookings/{booking.id}/refund",
        json={"reason": "dispute"},
        headers=auth_headers_admin,
    )

    assert response.status_code == 500
    assert response.json()["detail"] == "Stripe refund failed"


@patch("app.services.admin_refund_service.AdminRefundService.apply_refund_updates")
@patch("app.services.stripe_service.StripeService.refund_payment")
def test_refund_returns_not_found_if_booking_disappears_after_stripe_refund(
    mock_refund_payment,
    mock_apply_refund_updates,
    client,
    db,
    test_booking,
    auth_headers_admin,
):
    booking = _prepare_booking_for_refund(db, test_booking)
    mock_refund_payment.return_value = {"refund_id": "re_missing", "amount_refunded": 1000}
    mock_apply_refund_updates.return_value = None

    response = client.post(
        f"/api/v1/admin/bookings/{booking.id}/refund",
        json={"reason": "other"},
        headers=auth_headers_admin,
    )

    assert response.status_code == 404
    assert "after refund" in response.json()["detail"].lower()


@patch("app.services.stripe_service.StripeService.refund_payment")
def test_instructor_no_show_sets_no_show_status(
    mock_refund_payment,
    client,
    db,
    test_booking,
    auth_headers_admin,
):
    booking = _prepare_booking_for_refund(db, test_booking)
    mock_refund_payment.return_value = {
        "refund_id": "re_no_show",
        "amount_refunded": 5000,
    }

    response = client.post(
        f"/api/v1/admin/bookings/{booking.id}/refund",
        json={"reason": "instructor_no_show"},
        headers=auth_headers_admin,
    )

    assert response.status_code == 200
    db.refresh(booking)
    if booking.payment_detail is not None:
        db.refresh(booking.payment_detail)
    assert booking.status == "NO_SHOW"
    assert booking.payment_detail.payment_status == "settled"
    assert booking.payment_detail.settlement_outcome == "instructor_no_show_full_refund"


@patch("app.services.stripe_service.StripeService.refund_payment")
def test_dispute_sets_cancelled_status(
    mock_refund_payment,
    client,
    db,
    test_booking,
    auth_headers_admin,
):
    booking = _prepare_booking_for_refund(db, test_booking)
    mock_refund_payment.return_value = {
        "refund_id": "re_dispute",
        "amount_refunded": 5000,
    }

    response = client.post(
        f"/api/v1/admin/bookings/{booking.id}/refund",
        json={"reason": "dispute"},
        headers=auth_headers_admin,
    )

    assert response.status_code == 200
    db.refresh(booking)
    assert booking.status == "CANCELLED"


@patch("app.services.stripe_service.StripeService.refund_payment")
def test_refund_creates_audit_log(
    mock_refund_payment,
    client,
    db,
    test_booking,
    auth_headers_admin,
    admin_user,
):
    booking = _prepare_booking_for_refund(db, test_booking)
    mock_refund_payment.return_value = {
        "refund_id": "re_audit",
        "amount_refunded": 5000,
    }

    response = client.post(
        f"/api/v1/admin/bookings/{booking.id}/refund",
        json={"reason": "instructor_no_show", "note": "Test refund"},
        headers=auth_headers_admin,
    )

    assert response.status_code == 200

    log = (
        db.query(AuditLog)
        .filter(AuditLog.entity_id == booking.id, AuditLog.action == "admin_refund")
        .first()
    )
    assert log is not None
    assert log.actor_id == admin_user.id
