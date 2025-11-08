"""Bitmap cleanup tests for instructor deletion."""

from datetime import date, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session
from tests._utils.bitmap_avail import seed_day
from tests.factories.booking_builders import create_booking_pg_safe

from app.models.availability_day import AvailabilityDay
from app.models.service_catalog import InstructorService as Service
from app.models.user import User
from app.services.instructor_service import InstructorService


def test_delete_instructor_purges_orphan_availability(db: Session, test_instructor: User) -> None:
    """Deleting an instructor removes all orphan AvailabilityDay rows immediately."""
    instructor_id = test_instructor.id
    first = date.today() + timedelta(days=1)
    second = date.today() + timedelta(days=2)

    seed_day(db, instructor_id, first, [("09:00:00", "10:00:00")])
    seed_day(db, instructor_id, second, [("14:00:00", "15:00:00")])
    db.commit()

    InstructorService(db).delete_instructor_profile(instructor_id)

    remaining = db.execute(
        select(AvailabilityDay).where(AvailabilityDay.instructor_id == instructor_id)
    ).first()
    assert remaining is None


def test_delete_instructor_keeps_days_with_bookings(
    db: Session, test_instructor: User, test_student: User
) -> None:
    """Availability linked to bookings is preserved even during immediate cleanup."""
    instructor_id = test_instructor.id
    booking_date = date.today() + timedelta(days=3)
    seed_day(db, instructor_id, booking_date, [("10:00:00", "11:00:00")])
    db.commit()

    # Create a booking on that date so the day is protected.
    service = (
        db.query(Service)
        .filter(Service.instructor_profile_id == test_instructor.instructor_profile.id)
        .first()
    )
    assert service is not None
    create_booking_pg_safe(
        db,
        student_id=test_student.id,
        instructor_id=instructor_id,
        instructor_service_id=service.id,
        booking_date=booking_date,
        start_time=time(10, 0),
        end_time=time(11, 0),
        allow_overlap=True,
        service_name=service.description or "Test Service",
        hourly_rate=service.hourly_rate,
        total_price=service.hourly_rate,
        duration_minutes=60,
    )
    db.commit()
