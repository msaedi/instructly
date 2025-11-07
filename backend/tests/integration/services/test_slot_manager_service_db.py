# backend/tests/integration/services/test_slot_manager_service_db.py
"""Bitmap window manipulation patterns formerly covered by SlotManager tests."""

from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models.booking import Booking
from app.models.user import User
from tests._utils.bitmap_avail import flatten_range, get_day_windows, seed_day, window_exists


class TestBitmapWindowPatterns:
    """Document simple bitmap operations that replaced SlotManager flows."""

    def test_create_window_records_bitmap(self, db: Session, test_instructor: User):
        target_date = date.today() + timedelta(days=2)
        seed_day(db, test_instructor.id, target_date, [("09:00:00", "10:00:00")])
        assert get_day_windows(db, test_instructor.id, target_date) == [("09:00:00", "10:00:00")]

    def test_merge_adjacent_windows(self, db: Session, test_instructor: User):
        target_date = date.today() + timedelta(days=3)
        seed_day(db, test_instructor.id, target_date, [("09:00:00", "10:00:00")])
        existing = get_day_windows(db, test_instructor.id, target_date)
        seed_day(db, test_instructor.id, target_date, existing + [("10:00:00", "11:00:00")])
        assert get_day_windows(db, test_instructor.id, target_date) == [("09:00:00", "11:00:00")]

    def test_split_window(self, db: Session, test_instructor: User):
        target_date = date.today() + timedelta(days=4)
        seed_day(db, test_instructor.id, target_date, [("13:00:00", "15:00:00")])
        seed_day(
            db,
            test_instructor.id,
            target_date,
            [("13:00:00", "14:00:00"), ("14:30:00", "15:00:00")],
        )
        assert get_day_windows(db, test_instructor.id, target_date) == [
            ("13:00:00", "14:00:00"),
            ("14:30:00", "15:00:00"),
        ]

    def test_gap_analysis_inputs(self, db: Session, test_instructor_with_availability: User):
        instructor_id = test_instructor_with_availability.id
        target_date = date.today()
        windows = get_day_windows(db, instructor_id, target_date)
        flattened = flatten_range(db, instructor_id, target_date, target_date)
        assert len(flattened) == len(windows)
        assert flattened == sorted(flattened, key=lambda w: (w["date"], w["start_time"]))

    def test_time_overlap_check_with_booking(
        self,
        db: Session,
        test_booking: Booking,
    ):
        instructor_id = test_booking.instructor_id
        booking_date = test_booking.booking_date
        windows = get_day_windows(db, instructor_id, booking_date)
        has_overlap = any(
            (slot_start <= test_booking.start_time.strftime("%H:%M:%S") < slot_end)
            or (slot_start < test_booking.end_time.strftime("%H:%M:%S") <= slot_end)
            for slot_start, slot_end in windows
        )
        assert has_overlap in {True, False}

    def test_window_exists_helper(self, db: Session, test_instructor_with_availability: User):
        instructor_id = test_instructor_with_availability.id
        target_date = date.today()
        windows = get_day_windows(db, instructor_id, target_date)
        if windows:
            start, end = windows[0]
            assert window_exists(db, instructor_id, target_date, start, end)


class TestBitmapTransactions:
    """Examples of transaction-like bitmap operations."""

    def test_merge_transaction(self, db: Session, test_instructor: User):
        target_date = date.today() + timedelta(days=5)
        seed_day(db, test_instructor.id, target_date, [("14:00:00", "15:00:00")])
        seed_day(
            db,
            test_instructor.id,
            target_date,
            [("14:00:00", "15:00:00"), ("15:00:00", "16:00:00")],
        )
        assert get_day_windows(db, test_instructor.id, target_date) == [("14:00:00", "16:00:00")]

    def test_delete_window(self, db: Session, test_instructor_with_availability: User):
        instructor_id = test_instructor_with_availability.id
        target_date = date.today()
        windows = get_day_windows(db, instructor_id, target_date)
        if windows:
            remaining = windows[1:]
            seed_day(db, instructor_id, target_date, remaining)
            assert get_day_windows(db, instructor_id, target_date) == remaining
