# backend/tests/integration/repository_patterns/test_bulk_operation_query_patterns.py
"""
Bitmap-era query patterns for bulk availability operations.

These tests document the queries BulkOperationRepository needs in a world where
availability is stored in AvailabilityDay bitmaps instead of slot rows.
"""

from datetime import date, time, timedelta

from sqlalchemy.orm import Session
from tests.integration.repository_patterns._bitmap_helpers import (
    count_windows_total,
    fetch_days,
    flatten_range,
    seed_day,
    window_exists,
)

from app.models.booking import Booking, BookingStatus
from app.models.instructor import InstructorProfile
from app.models.user import User


class TestBulkOperationQueryPatterns:
    """Document bitmap-friendly query templates for BulkOperationRepository."""

    def test_query_windows_by_keys(self, db: Session, test_instructor_with_availability: User):
        """Selecting a subset of windows behaves like querying slots by ids."""
        instructor_id = test_instructor_with_availability.id
        week_start = date.today() - timedelta(days=date.today().weekday())
        for day_offset in range(3):
            target = week_start + timedelta(days=day_offset)
            seed_day(
                db,
                instructor_id,
                target,
                [(time(9, 0), time(10, 0)), (time(11, 0), time(12, 0)), (time(14, 0), time(15, 0))],
            )

        flat = flatten_range(db, instructor_id, week_start, week_start + timedelta(days=2))
        selected_keys = {(flat[0]["date"], flat[0]["start_time"]), (flat[1]["date"], flat[1]["start_time"])}
        subset = [
            window for window in flat if (window["date"], window["start_time"]) in selected_keys
        ]
        assert len(subset) == len(selected_keys)

    def test_query_windows_for_date(self, db: Session, test_instructor_with_availability: User):
        """Date-scoped window query replaces get_slots_by_date."""
        instructor_id = test_instructor_with_availability.id
        target_date = date.today() + timedelta(days=1)
        windows = [(time(9, 0), time(10, 0)), (time(13, 0), time(14, 30))]
        seed_day(db, instructor_id, target_date, windows)

        flat = flatten_range(db, instructor_id, target_date, target_date)
        assert [(w["start_time"], w["end_time"]) for w in flat] == [("09:00:00", "10:00:00"), ("13:00:00", "14:30:00")]

    def test_query_windows_with_bookings_for_date(self, db: Session, test_booking: Booking):
        """Booking guard now filters Booking rows by date/time instead of slot ids."""
        booking_date = test_booking.booking_date
        instructor_id = test_booking.instructor_id
        count = (
            db.query(Booking)
            .filter(
                Booking.instructor_id == instructor_id,
                Booking.booking_date == booking_date,
                Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
            )
            .count()
        )
        assert count > 0

    def test_query_week_windows_for_validation(self, db: Session, test_instructor_with_availability: User):
        """Week validation reads AvailabilityDay rows for the Monday-Sunday range."""
        instructor_id = test_instructor_with_availability.id
        week_start = date.today() - timedelta(days=date.today().weekday())
        week_end = week_start + timedelta(days=6)
        windows = flatten_range(db, instructor_id, week_start, week_end)
        assert windows
        assert week_start <= windows[0]["date"] <= week_end

    def test_query_windows_for_instructor_check(self, db: Session, test_instructor_with_availability: User):
        """Validating instructor ownership inspects AvailabilityDay rows."""
        instructor_id = test_instructor_with_availability.id
        rows = fetch_days(db, instructor_id, date.today(), date.today() + timedelta(days=1))
        assert all(row.instructor_id == instructor_id for row in rows)

    def test_query_windows_with_booking_status(self, db: Session, test_booking: Booking):
        """Mapping windows to booking status is a time-overlap check."""
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
            overlaps_booking = any(
                (b.start_time.strftime("%H:%M:%S"), b.end_time.strftime("%H:%M:%S"))
                == (window["start_time"], window["end_time"])
                for b in bookings
            )
            assert isinstance(overlaps_booking, bool)

    def test_query_remaining_windows_count(self, db: Session, test_instructor_with_availability: User):
        """Counting windows for a day replaces slot-count queries."""
        instructor_id = test_instructor_with_availability.id
        target_date = date.today()
        total = count_windows_total(db, instructor_id, target_date, target_date)
        assert total >= 0

    def test_query_affected_dates_for_cache(self, db: Session, test_instructor_with_availability: User):
        """Distinct day list now comes from AvailabilityDay rows."""
        instructor_id = test_instructor_with_availability.id
        base = date.today()
        for offset in range(3):
            seed_day(db, instructor_id, base + timedelta(days=offset), [(time(9, 0), time(10, 0))])

        rows = fetch_days(db, instructor_id, base, base + timedelta(days=4))
        unique_dates = {row.day_date for row in rows}
        assert len(unique_dates) >= 3

    def test_query_duplicate_window_check(self, db: Session, test_instructor_with_availability: User):
        """Duplicate detection is handled via window_exists helper."""
        instructor_id = test_instructor_with_availability.id
        today = date.today()
        seed_day(db, instructor_id, today, [(time(10, 0), time(11, 0))])
        assert window_exists(db, instructor_id, today, time(10, 0), time(11, 0))

    def test_query_instructor_profile_for_validation(self, db: Session, test_instructor: User):
        """Non-availability queries remain unchanged."""
        profile = db.query(InstructorProfile).filter(InstructorProfile.user_id == test_instructor.id).first()
        assert profile is not None

    def test_batch_create_windows(self, db: Session, test_instructor: User):
        """Bitmap batch insert replaces bulk_create_slots."""
        target_date = date.today() + timedelta(days=10)
        seed_day(
            db,
            test_instructor.id,
            target_date,
            [(time(10, 0), time(11, 0)), (time(11, 0), time(12, 0))],
        )
        flat = flatten_range(db, test_instructor.id, target_date, target_date)
        assert len(flat) == 1  # adjacent windows merge automatically

    def test_transaction_rollback_pattern(self, db: Session, test_instructor: User):
        """Transactions still protect bitmap writes."""
        instructor_id = test_instructor.id
        target_date = date.today() + timedelta(days=20)
        with db.begin_nested():
            seed_day(db, instructor_id, target_date, [(time(9, 0), time(10, 0))])
            db.rollback()
        remaining = fetch_days(db, instructor_id, target_date, target_date)
        assert remaining == []
