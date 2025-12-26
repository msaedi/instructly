# backend/tests/integration/repository_patterns/test_availability_repository_enhanced.py
"""Additional bitmap availability patterns for complex scenarios."""

from datetime import date, time, timedelta

import pytest
from sqlalchemy import and_
from sqlalchemy.orm import Session
from tests.integration.repository_patterns._bitmap_helpers import (
    fetch_days,
    flatten_windows,
    overlaps,
    seed_day,
    window_exists,
)

from app.models.availability_day import AvailabilityDay
from app.models.booking import Booking, BookingStatus
from app.models.instructor import InstructorProfile
from app.models.service_catalog import InstructorService as Service
from app.models.user import User
from app.utils.bitset import windows_from_bits

try:  # pragma: no cover - fallback for direct backend pytest runs
    from backend.tests.utils.booking_timezone import booking_timezone_fields
except ModuleNotFoundError:  # pragma: no cover
    from tests.utils.booking_timezone import booking_timezone_fields


def get_test_service(db: Session, instructor: User) -> Service:
    """Return the first active service for the instructor."""
    profile = db.query(InstructorProfile).filter(InstructorProfile.user_id == instructor.id).first()
    if not profile:
        raise ValueError(f"No profile for instructor {instructor.id}")
    service = db.query(Service).filter(Service.instructor_profile_id == profile.id, Service.is_active.is_(True)).first()
    if not service:
        raise ValueError("No active service found")
    return service


class TestAvailabilityRepositoryBulkOperations:
    """Stress-style patterns that operate on multiple bitmap rows."""

    def test_bulk_create_windows(self, db: Session, test_instructor: User):
        instructor_id = test_instructor.id
        target_date = date.today() + timedelta(days=30)
        windows = [(time(hour, 0), time(hour + 1, 0)) for hour in range(9, 17)]
        seed_day(db, instructor_id, target_date, windows)
        rows = fetch_days(db, instructor_id, target_date, target_date)
        flat = flatten_windows(rows)
        assert len(flat) == 1
        assert flat[0]["start_time"] == "09:00:00"
        assert flat[0]["end_time"] == "17:00:00"

    def test_bulk_delete_with_bookings(self, db: Session, test_instructor_with_availability: User, test_student: User):
        instructor = test_instructor_with_availability
        target_date = date.today()
        windows = [(time(9, 0), time(10, 0)), (time(11, 0), time(12, 0))]
        seed_day(db, instructor.id, target_date, windows)

        service = get_test_service(db, instructor)
        booking_date = target_date
        start_time = time(9, 0)
        end_time = time(10, 0)
        db.add(
            Booking(
                instructor_id=instructor.id,
                student_id=test_student.id,
                instructor_service_id=service.id,
                booking_date=booking_date,
                start_time=start_time,
                end_time=end_time,
                **booking_timezone_fields(booking_date, start_time, end_time),
                status=BookingStatus.CONFIRMED,
                service_name="Test Service",
                hourly_rate=50.0,
                total_price=50.0,
                duration_minutes=60,
            )
        )
        db.commit()

        deleted = (
            db.query(AvailabilityDay)
            .filter(AvailabilityDay.instructor_id == instructor.id, AvailabilityDay.day_date == target_date)
            .delete(synchronize_session=False)
        )
        db.commit()
        assert deleted == 1

        remaining_booking = (
            db.query(Booking)
            .filter(and_(Booking.instructor_id == instructor.id, Booking.booking_date == target_date))
            .first()
        )
        assert remaining_booking is not None

    def test_find_overlapping_windows(self, db: Session, test_instructor: User):
        instructor_id = test_instructor.id
        target_date = date.today() + timedelta(days=15)
        seed_day(
            db,
            instructor_id,
            target_date,
            [
                (time(8, 0), time(9, 0)),
                (time(9, 30), time(10, 0)),
                (time(10, 30), time(11, 0)),
                (time(11, 30), time(12, 0)),
                (time(12, 30), time(13, 0)),
                (time(13, 30), time(14, 0)),
            ],
        )

        windows = windows_from_bits(fetch_days(db, instructor_id, target_date, target_date)[0].bits or b"")
        conflicts = [w for w in windows if overlaps(w, time(10, 0), time(12, 45))]
        assert len(conflicts) == 3

    def test_concurrent_window_merge(self, db: Session, test_instructor: User):
        instructor_id = test_instructor.id
        target_date = date.today() + timedelta(days=5)
        seed_day(db, instructor_id, target_date, [(time(14, 0), time(15, 0))])
        seed_day(db, instructor_id, target_date, [(time(14, 0), time(15, 0)), (time(14, 30), time(15, 30))])

        windows = windows_from_bits(fetch_days(db, instructor_id, target_date, target_date)[0].bits or b"")
        assert windows == [("14:00:00", "15:30:00")]

class TestAvailabilityRepositoryEdgeCases:
    """Edge scenarios kept for documentation purposes."""

    def test_slot_validation_rules(self, db: Session, test_instructor: User):
        instructor_id = test_instructor.id
        target_date = date.today() + timedelta(days=10)
        with pytest.raises(ValueError):
            seed_day(db, instructor_id, target_date, [(time(10, 0), time(9, 0))])

    def test_window_exists_helper(self, db: Session, test_instructor: User):
        instructor_id = test_instructor.id
        target_date = date.today() + timedelta(days=2)
        seed_day(db, instructor_id, target_date, [(time(9, 0), time(10, 0))])
        assert window_exists(db, instructor_id, target_date, time(9, 0), time(10, 0))
        assert not window_exists(db, instructor_id, target_date, time(11, 0), time(12, 0))
