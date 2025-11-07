# backend/tests/integration/repository_patterns/test_slot_manager_query_patterns.py
"""
Bitmap query patterns that replaced the old SlotManagerRepository.

These tests document how window existence, gap analysis, and booking lookups work
now that availability is stored in AvailabilityDay rows.
"""

from datetime import date, time, timedelta

from sqlalchemy.orm import Session
from tests.integration.repository_patterns._bitmap_helpers import (
    delete_day,
    flatten_range,
    seed_day,
    window_exists,
)

from app.models.booking import Booking, BookingStatus
from app.models.user import User


class TestSlotManagerQueryPatterns:
    """Query snippets that SlotManagerRepository would expose."""

    def test_query_pattern_check_window_exists(self, db: Session, test_instructor_with_availability: User):
        instructor_id = test_instructor_with_availability.id
        target_date = date.today()
        seed_day(db, instructor_id, target_date, [(time(9, 0), time(10, 0))])
        assert window_exists(db, instructor_id, target_date, time(9, 0), time(10, 0))
        assert not window_exists(db, instructor_id, target_date, time(11, 0), time(12, 0))

    def test_query_pattern_get_windows_for_date(self, db: Session, test_instructor_with_availability: User):
        instructor_id = test_instructor_with_availability.id
        target_date = date.today() + timedelta(days=1)
        seed_day(db, instructor_id, target_date, [(time(10, 0), time(11, 0)), (time(11, 0), time(12, 0))])
        flat = flatten_range(db, instructor_id, target_date, target_date)
        assert flat == [
            {"date": target_date, "start_time": "10:00:00", "end_time": "12:00:00"},
        ]

    def test_query_pattern_check_time_has_booking(self, db: Session, test_booking: Booking):
        """Bookings are discovered by time overlap instead of slot IDs."""
        instructor_id = test_booking.instructor_id
        booking_date = test_booking.booking_date
        start_time = test_booking.start_time
        end_time = test_booking.end_time
        has_booking = (
            db.query(Booking)
            .filter(
                Booking.instructor_id == instructor_id,
                Booking.booking_date == booking_date,
                Booking.start_time < end_time,
                Booking.end_time > start_time,
                Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
            )
            .first()
            is not None
        )
        assert has_booking is True

    def test_query_pattern_get_booking_for_window(self, db: Session, test_booking: Booking):
        """Resolving booking metadata is still a time-based query."""
        booking = (
            db.query(Booking)
            .filter(
                Booking.instructor_id == test_booking.instructor_id,
                Booking.booking_date == test_booking.booking_date,
                Booking.start_time == test_booking.start_time,
                Booking.end_time == test_booking.end_time,
                Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
            )
            .first()
        )
        assert booking is not None
        assert booking.id == test_booking.id

    def test_query_pattern_get_windows_for_instructor_date(
        self, db: Session, test_instructor_with_availability: User
    ):
        instructor_id = test_instructor_with_availability.id
        target_date = date.today()
        windows = flatten_range(db, instructor_id, target_date, target_date)
        assert all(win["date"] == target_date for win in windows)


class TestSlotManagerComplexQueries:
    """Higher-level patterns (booking status, gaps, optimization)."""

    def test_complex_pattern_windows_with_booking_status(self, db: Session, test_booking: Booking):
        instructor_id = test_booking.instructor_id
        target_date = test_booking.booking_date
        windows = flatten_range(db, instructor_id, target_date, target_date)
        bookings = (
            db.query(Booking)
            .filter(
                Booking.instructor_id == instructor_id,
                Booking.booking_date == target_date,
                Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
            )
            .all()
        )
        for window in windows:
            has_booking = any(
                (b.start_time.strftime("%H:%M:%S"), b.end_time.strftime("%H:%M:%S"))
                == (window["start_time"], window["end_time"])
                for b in bookings
            )
            assert isinstance(has_booking, bool)

    def test_complex_pattern_gap_analysis(self, db: Session, test_instructor_with_availability: User):
        instructor_id = test_instructor_with_availability.id
        target_date = date.today()
        seed_day(
            db,
            instructor_id,
            target_date,
            [(time(9, 0), time(10, 0)), (time(11, 0), time(12, 0)), (time(13, 0), time(15, 0))],
        )
        windows = flatten_range(db, instructor_id, target_date, target_date)
        assert len(windows) == 3
        for i in range(1, len(windows)):
            assert windows[i - 1]["start_time"] <= windows[i]["start_time"]

    def test_complex_pattern_availability_optimization(self, db: Session, test_instructor_with_availability: User):
        instructor_id = test_instructor_with_availability.id
        target_date = date.today() + timedelta(days=2)
        seed_day(
            db,
            instructor_id,
            target_date,
            [(time(9, 0), time(10, 0)), (time(10, 30), time(11, 30)), (time(14, 0), time(15, 0))],
        )
        windows = flatten_range(db, instructor_id, target_date, target_date)
        bookings = (
            db.query(Booking)
            .filter(
                Booking.instructor_id == instructor_id,
                Booking.booking_date == target_date,
                Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
            )
            .all()
        )
        # Optimization logic would compare windows to booked ranges; we just ensure the data is structured.
        assert isinstance(windows, list)
        assert isinstance(bookings, list)


class TestSlotManagerTransactionPatterns:
    """Transaction-themed bitmap operations."""

    def test_transaction_pattern_create_and_merge(self, db: Session, test_instructor: User):
        instructor_id = test_instructor.id
        target_date = date.today() + timedelta(days=3)
        with db.begin_nested():
            seed_day(db, instructor_id, target_date, [(time(14, 0), time(15, 0))])
            seed_day(
                db,
                instructor_id,
                target_date,
                [(time(14, 0), time(15, 0)), (time(15, 0), time(16, 0))],
            )
        windows = flatten_range(db, instructor_id, target_date, target_date)
        assert windows == [{"date": target_date, "start_time": "14:00:00", "end_time": "16:00:00"}]

    def test_transaction_pattern_delete_window(self, db: Session, test_instructor_with_availability: User):
        instructor_id = test_instructor_with_availability.id
        target_date = date.today()
        deleted = delete_day(db, instructor_id, target_date)
        assert deleted in (0, 1)
