"""
Integration tests for checkout race condition handling.
"""

from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from app.core.exceptions import BookingCancelledException, BookingNotFoundException
from app.models.booking import Booking, BookingStatus, PaymentStatus
from app.schemas.payment_schemas import CreateCheckoutRequest
from app.services.booking_service import BookingService
from app.services.config_service import ConfigService
from app.services.pricing_service import PricingService
from app.services.stripe_service import StripeService


def _prepare_pending_booking(db: Session, booking: Booking) -> Booking:
    booking.status = BookingStatus.PENDING.value
    booking.payment_status = None
    booking.confirmed_at = None
    db.commit()
    return booking


def _build_services(db: Session) -> tuple[StripeService, BookingService]:
    stripe_service = StripeService(
        db,
        config_service=ConfigService(db),
        pricing_service=PricingService(db),
    )
    booking_service = BookingService(db)
    return stripe_service, booking_service


def _checkout_payload(booking_id: str) -> CreateCheckoutRequest:
    return CreateCheckoutRequest(
        booking_id=booking_id,
        payment_method_id="pm_test",
        save_payment_method=False,
        requested_credit_cents=0,
    )


def _payment_success(payment_intent_id: str) -> dict:
    return {
        "success": True,
        "payment_intent_id": payment_intent_id,
        "status": "requires_capture",
        "amount": 5000,
        "application_fee": 500,
        "client_secret": None,
    }


def test_checkout_detects_cancelled_booking(
    db: Session, test_booking: Booking, test_student
) -> None:
    booking = _prepare_pending_booking(db, test_booking)
    stripe_service, booking_service = _build_services(db)

    def _cancel_during_payment(*_args, **_kwargs) -> dict:
        target = db.query(Booking).filter(Booking.id == booking.id).first()
        assert target is not None
        target.status = BookingStatus.CANCELLED.value
        target.cancelled_at = datetime.now(timezone.utc)
        db.commit()
        return _payment_success("pi_cancelled")

    with patch.object(
        stripe_service, "process_booking_payment", side_effect=_cancel_during_payment
    ), patch.object(stripe_service, "_void_or_refund_payment") as mock_void:
        with pytest.raises(BookingCancelledException):
            stripe_service.create_booking_checkout(
                current_user=test_student,
                payload=_checkout_payload(booking.id),
                booking_service=booking_service,
            )

    mock_void.assert_called_once_with("pi_cancelled")


def test_checkout_detects_deleted_booking(
    db: Session, test_booking: Booking, test_student
) -> None:
    booking = _prepare_pending_booking(db, test_booking)
    stripe_service, booking_service = _build_services(db)

    def _delete_during_payment(*_args, **_kwargs) -> dict:
        target = db.query(Booking).filter(Booking.id == booking.id).first()
        assert target is not None
        db.delete(target)
        db.commit()
        return _payment_success("pi_deleted")

    with patch.object(
        stripe_service, "process_booking_payment", side_effect=_delete_during_payment
    ), patch.object(stripe_service, "_void_or_refund_payment") as mock_void:
        with pytest.raises(BookingNotFoundException):
            stripe_service.create_booking_checkout(
                current_user=test_student,
                payload=_checkout_payload(booking.id),
                booking_service=booking_service,
            )

    mock_void.assert_called_once_with("pi_deleted")


def test_normal_checkout_still_works(db: Session, test_booking: Booking, test_student) -> None:
    booking = _prepare_pending_booking(db, test_booking)
    stripe_service, booking_service = _build_services(db)

    with patch.object(
        stripe_service, "process_booking_payment", return_value=_payment_success("pi_ok")
    ), patch.object(stripe_service, "_void_or_refund_payment") as mock_void:
        response = stripe_service.create_booking_checkout(
            current_user=test_student,
            payload=_checkout_payload(booking.id),
            booking_service=booking_service,
        )

    db.refresh(booking)
    assert response.success is True
    assert booking.status == BookingStatus.CONFIRMED.value
    assert booking.payment_status == PaymentStatus.AUTHORIZED.value
    mock_void.assert_not_called()


def test_concurrent_checkout_and_cancel(
    db: Session, test_booking: Booking, test_student
) -> None:
    booking = _prepare_pending_booking(db, test_booking)
    stripe_service, booking_service = _build_services(db)

    def _cancel_between_steps(*_args, **_kwargs) -> dict:
        target = db.query(Booking).filter(Booking.id == booking.id).first()
        assert target is not None
        target.status = BookingStatus.CANCELLED.value
        db.commit()
        return _payment_success("pi_race")

    with patch.object(
        stripe_service, "process_booking_payment", side_effect=_cancel_between_steps
    ), patch.object(stripe_service, "_void_or_refund_payment") as mock_void:
        with pytest.raises(BookingCancelledException):
            stripe_service.create_booking_checkout(
                current_user=test_student,
                payload=_checkout_payload(booking.id),
                booking_service=booking_service,
            )

    mock_void.assert_called_once_with("pi_race")
