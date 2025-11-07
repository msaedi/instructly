# backend/tests/integration/services/test_bulk_operation_service_db.py
"""Bitmap availability patterns inspired by legacy BulkOperationService tests."""

from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models.booking import Booking, BookingStatus
from app.models.user import User
from tests._utils.bitmap_avail import flatten_range, get_day_windows, seed_day, window_exists


class TestBulkWindowDocPatterns:
    """Document bitmap manipulations formerly covered by slot-era bulk tests."""

    def test_add_windows_creates_bitmap(self, db: Session, test_instructor: User):
        target = date.today() + timedelta(days=1)
        seed_day(
            db,
            test_instructor.id,
            target,
            [("09:00:00", "10:00:00"), ("10:00:00", "11:00:00"), ("14:00:00", "16:00:00")],
        )
        assert get_day_windows(db, test_instructor.id, target) == [
            ("09:00:00", "11:00:00"),
            ("14:00:00", "16:00:00"),
        ]

    def test_duplicates_detected_via_helper(self, db: Session, test_instructor_with_availability: User):
        instructor_id = test_instructor_with_availability.id
        target_date = date.today()
        windows = get_day_windows(db, instructor_id, target_date)
        if windows:
            start, end = windows[0]
            assert window_exists(db, instructor_id, target_date, start, end)

    def test_transactional_append(self, db: Session, test_instructor: User):
        target = date.today() + timedelta(days=2)
        seed_day(db, test_instructor.id, target, [("09:00:00", "10:00:00")])
        existing = get_day_windows(db, test_instructor.id, target)
        seed_day(db, test_instructor.id, target, existing + [("13:00:00", "14:00:00")])
        assert get_day_windows(db, test_instructor.id, target) == [
            ("09:00:00", "10:00:00"),
            ("13:00:00", "14:00:00"),
        ]

    def test_week_validation_view(self, db: Session, test_instructor_with_availability: User):
        instructor_id = test_instructor_with_availability.id
        week_start = date.today()
        flats = flatten_range(db, instructor_id, week_start, week_start + timedelta(days=6))
        assert flats == sorted(flats, key=lambda w: (w["date"], w["start_time"]))

    def test_booking_overlap_reference(self, db: Session, test_booking: Booking):
        instructor_id = test_booking.instructor_id
        booking_date = test_booking.booking_date
        windows = get_day_windows(db, instructor_id, booking_date)
        # Document that bookings exist independent from windows; both structures are queried by time.
        overlap = any(
            (start <= test_booking.start_time.strftime("%H:%M:%S") < end)
            or (start < test_booking.end_time.strftime("%H:%M:%S") <= end)
            for start, end in windows
        )
        assert overlap is True or test_booking.status not in [BookingStatus.CONFIRMED, BookingStatus.COMPLETED]

    def test_past_date_guard(self, db: Session, test_instructor: User):
        yesterday = date.today() - timedelta(days=1)
        seed_day(db, test_instructor.id, yesterday, [("09:00:00", "10:00:00")])
        assert get_day_windows(db, test_instructor.id, yesterday) == [("09:00:00", "10:00:00")]
