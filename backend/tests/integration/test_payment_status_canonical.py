"""Integration tests for canonical booking payment_status values."""

from datetime import date, time, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.booking import BookingStatus, PaymentStatus
from app.models.booking_payment import BookingPayment

try:  # pragma: no cover - fallback for direct backend pytest runs
    from backend.tests.factories.booking_builders import create_booking_pg_safe
except ModuleNotFoundError:  # pragma: no cover
    from tests.factories.booking_builders import create_booking_pg_safe


def _service_id_for_instructor(instructor) -> str:
    profile = instructor.instructor_profile
    service = next((svc for svc in profile.instructor_services if svc.is_active), None)
    assert service is not None, "Expected an active instructor service"
    return service.id


def test_payment_status_rejects_legacy_values(db, test_student, test_instructor):
    """Legacy payment_status values should fail the check constraint."""
    booking_date = date.today() + timedelta(days=1)
    start_time = time(10, 0)
    end_time = time(11, 0)

    with pytest.raises(IntegrityError):
        create_booking_pg_safe(
            db,
            student_id=test_student.id,
            instructor_id=test_instructor.id,
            instructor_service_id=_service_id_for_instructor(test_instructor),
            booking_date=booking_date,
            start_time=start_time,
            end_time=end_time,
            status=BookingStatus.CONFIRMED,
            allow_overlap=True,
            service_name="Status Canonical",
            hourly_rate=100.0,
            total_price=100.0,
            duration_minutes=60,
            location_type="neutral_location",
            meeting_location="Test",
            payment_status="captured",
        )

    db.rollback()


def test_payment_status_accepts_canonical_values(db, test_student, test_instructor):
    """Canonical payment_status values should persist successfully."""
    booking_date = date.today() + timedelta(days=2)
    start_time = time(11, 0)
    end_time = time(12, 0)

    booking = create_booking_pg_safe(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor.id,
        instructor_service_id=_service_id_for_instructor(test_instructor),
        booking_date=booking_date,
        start_time=start_time,
        end_time=end_time,
        status=BookingStatus.CONFIRMED,
        allow_overlap=True,
        service_name="Status Canonical",
        hourly_rate=100.0,
        total_price=100.0,
        duration_minutes=60,
        location_type="neutral_location",
        meeting_location="Test",
        payment_status=PaymentStatus.AUTHORIZED.value,
    )

    db.commit()

    bp = db.query(BookingPayment).filter(BookingPayment.booking_id == booking.id).first()
    assert bp is not None
    assert bp.payment_status == PaymentStatus.AUTHORIZED.value
