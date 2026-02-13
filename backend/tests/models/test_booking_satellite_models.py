from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.booking_dispute import BookingDispute
from app.models.booking_lock import BookingLock
from app.models.booking_no_show import BookingNoShow
from app.models.booking_payment import BookingPayment
from app.models.booking_transfer import BookingTransfer


def test_booking_dispute_relationship_and_repr(db, test_booking) -> None:
    dispute = BookingDispute(
        booking_id=test_booking.id,
        dispute_id="dp_test_123",
        dispute_status="needs_response",
        dispute_amount=2500,
        dispute_created_at=datetime.now(timezone.utc),
    )
    db.add(dispute)
    db.flush()

    assert dispute.booking is not None
    assert dispute.booking.id == test_booking.id
    assert "needs_response" in repr(dispute)


def test_booking_transfer_defaults_and_unique_booking_id(db, test_booking) -> None:
    transfer = BookingTransfer(
        booking_id=test_booking.id,
        stripe_transfer_id="tr_test_123",
    )
    db.add(transfer)
    db.flush()

    assert transfer.transfer_retry_count == 0
    assert transfer.transfer_reversed is False
    assert transfer.transfer_reversal_retry_count == 0
    assert transfer.refund_retry_count == 0
    assert transfer.payout_transfer_retry_count == 0
    assert transfer.booking is not None
    assert transfer.booking.id == test_booking.id
    assert test_booking.id in repr(transfer)

    with db.begin_nested():
        duplicate = BookingTransfer(booking_id=test_booking.id)
        db.add(duplicate)
        with pytest.raises(IntegrityError):
            db.flush()


def test_booking_no_show_relationship_defaults_and_repr(db, test_booking, test_student) -> None:
    no_show = BookingNoShow(
        booking_id=test_booking.id,
        no_show_reported_by=test_student.id,
        no_show_type="student",
    )
    db.add(no_show)
    db.flush()

    assert no_show.no_show_disputed is False
    assert no_show.no_show_reporter is not None
    assert no_show.no_show_reporter.id == test_student.id
    assert "student" in repr(no_show)


def test_booking_lock_relationship_and_repr(db, test_booking) -> None:
    lock = BookingLock(
        booking_id=test_booking.id,
        locked_at=datetime.now(timezone.utc),
        locked_amount_cents=1800,
        lock_resolution="completed",
    )
    db.add(lock)
    db.flush()

    assert lock.booking is not None
    assert lock.booking.id == test_booking.id
    assert "completed" in repr(lock)


def test_booking_payment_defaults_relationship_and_unique(db, test_booking) -> None:
    payment = BookingPayment(
        booking_id=test_booking.id,
        payment_status="scheduled",
        payment_method_id="pm_test_123",
    )
    db.add(payment)
    db.flush()

    assert payment.auth_failure_count == 0
    assert payment.credits_reserved_cents == 0
    assert payment.capture_retry_count == 0
    assert payment.booking is not None
    assert payment.booking.id == test_booking.id
    assert "scheduled" in repr(payment)

    with db.begin_nested():
        duplicate = BookingPayment(booking_id=test_booking.id)
        db.add(duplicate)
        with pytest.raises(IntegrityError):
            db.flush()


def test_satellite_rows_deleted_when_booking_deleted(db, test_booking) -> None:
    db.add(BookingDispute(booking_id=test_booking.id, dispute_status="won"))
    db.add(BookingTransfer(booking_id=test_booking.id, stripe_transfer_id="tr_cascade"))
    db.add(BookingNoShow(booking_id=test_booking.id, no_show_type="instructor"))
    db.add(BookingLock(booking_id=test_booking.id, locked_amount_cents=900))
    db.add(BookingPayment(booking_id=test_booking.id, payment_status="authorized"))
    db.flush()

    db.delete(test_booking)
    db.flush()

    assert db.query(BookingDispute).filter_by(booking_id=test_booking.id).one_or_none() is None
    assert db.query(BookingTransfer).filter_by(booking_id=test_booking.id).one_or_none() is None
    assert db.query(BookingNoShow).filter_by(booking_id=test_booking.id).one_or_none() is None
    assert db.query(BookingLock).filter_by(booking_id=test_booking.id).one_or_none() is None
    assert db.query(BookingPayment).filter_by(booking_id=test_booking.id).one_or_none() is None
