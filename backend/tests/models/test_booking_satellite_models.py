from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.models.booking import Booking
from app.models.booking_dispute import BookingDispute
from app.models.booking_lock import BookingLock
from app.models.booking_no_show import BookingNoShow
from app.models.booking_payment import BookingPayment
from app.models.booking_reschedule import BookingReschedule
from app.models.booking_transfer import BookingTransfer


def _create_non_conflicting_booking(db, source_booking: Booking, day_offset: int = 2) -> Booking:
    start_utc = source_booking.booking_start_utc + timedelta(days=day_offset)
    end_utc = source_booking.booking_end_utc + timedelta(days=day_offset)
    new_booking = Booking(
        student_id=source_booking.student_id,
        instructor_id=source_booking.instructor_id,
        instructor_service_id=source_booking.instructor_service_id,
        booking_date=source_booking.booking_date + timedelta(days=day_offset),
        start_time=source_booking.start_time,
        end_time=source_booking.end_time,
        booking_start_utc=start_utc,
        booking_end_utc=end_utc,
        lesson_timezone=source_booking.lesson_timezone,
        instructor_tz_at_booking=source_booking.instructor_tz_at_booking,
        student_tz_at_booking=source_booking.student_tz_at_booking,
        service_name=source_booking.service_name,
        hourly_rate=source_booking.hourly_rate,
        total_price=source_booking.total_price,
        duration_minutes=source_booking.duration_minutes,
        status=source_booking.status,
        location_type=source_booking.location_type,
    )
    db.add(new_booking)
    db.flush()
    return new_booking


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


def test_booking_reschedule_defaults_relationship_and_unique(db, test_booking) -> None:
    reschedule = BookingReschedule(
        booking_id=test_booking.id,
        rescheduled_to_booking_id=None,
    )
    db.add(reschedule)
    db.flush()

    assert reschedule.late_reschedule_used is False
    assert reschedule.reschedule_count == 0
    assert reschedule.booking is not None
    assert reschedule.booking.id == test_booking.id
    assert test_booking.id in repr(reschedule)

    with db.begin_nested():
        duplicate = BookingReschedule(booking_id=test_booking.id)
        db.add(duplicate)
        with pytest.raises(IntegrityError):
            db.flush()


def test_booking_reschedule_dual_fk_relationship_and_set_null(db, test_booking) -> None:
    rescheduled_to = _create_non_conflicting_booking(db, test_booking, day_offset=3)
    reschedule = BookingReschedule(
        booking_id=test_booking.id,
        rescheduled_to_booking_id=rescheduled_to.id,
        reschedule_count=1,
    )
    db.add(reschedule)
    db.flush()
    db.refresh(reschedule)

    assert reschedule.booking is not None
    assert reschedule.booking.id == test_booking.id
    assert reschedule.rescheduled_to is not None
    assert reschedule.rescheduled_to.id == rescheduled_to.id
    assert reschedule.booking.id != reschedule.rescheduled_to.id

    booking_with_reschedule = (
        db.query(Booking)
        .options(selectinload(Booking.reschedule_detail))
        .filter(Booking.id == test_booking.id)
        .one()
    )
    assert booking_with_reschedule.reschedule_detail is not None
    assert booking_with_reschedule.reschedule_detail.rescheduled_to_booking_id == rescheduled_to.id

    db.delete(rescheduled_to)
    db.flush()
    db.refresh(reschedule)

    assert reschedule.rescheduled_to_booking_id is None
    assert reschedule.rescheduled_to is None


def test_satellite_rows_deleted_when_booking_deleted(db, test_booking) -> None:
    db.add(BookingDispute(booking_id=test_booking.id, dispute_status="won"))
    db.add(BookingTransfer(booking_id=test_booking.id, stripe_transfer_id="tr_cascade"))
    db.add(BookingNoShow(booking_id=test_booking.id, no_show_type="instructor"))
    db.add(BookingLock(booking_id=test_booking.id, locked_amount_cents=900))
    db.add(BookingPayment(booking_id=test_booking.id, payment_status="authorized"))
    db.add(BookingReschedule(booking_id=test_booking.id, reschedule_count=1))
    db.flush()

    db.delete(test_booking)
    db.flush()

    assert db.query(BookingDispute).filter_by(booking_id=test_booking.id).one_or_none() is None
    assert db.query(BookingTransfer).filter_by(booking_id=test_booking.id).one_or_none() is None
    assert db.query(BookingNoShow).filter_by(booking_id=test_booking.id).one_or_none() is None
    assert db.query(BookingLock).filter_by(booking_id=test_booking.id).one_or_none() is None
    assert db.query(BookingPayment).filter_by(booking_id=test_booking.id).one_or_none() is None
    assert db.query(BookingReschedule).filter_by(booking_id=test_booking.id).one_or_none() is None
