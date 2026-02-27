# backend/tests/integration/services/test_bulk_operation_bitmap_patterns.py
"""Bitmap-native coverage for BulkOperationService edge cases."""

from __future__ import annotations

from datetime import date, time, timedelta

from sqlalchemy.orm import Session

from app.models.user import User
from app.schemas.availability_window import SlotOperation
from app.services.bulk_operation_service import BulkOperationService
from app.utils.time_helpers import string_to_time
from tests._utils.bitmap_avail import get_day_windows, seed_day


class TestBulkOperationBitmapPatterns:
    """Exercises bitmap flows that replaced the legacy slot suite."""

    def test_validate_add_operation_timing_rejects_past_dates(
        self, db: Session, test_instructor_with_availability: User
    ) -> None:
        """_validate_add_operation_timing enforces instructor-local past guards."""
        service = BulkOperationService(db)
        instructor_id = test_instructor_with_availability.id
        yesterday = date.today() - timedelta(days=7)
        operation = SlotOperation(
            action="add",
            date=yesterday,
            start_time=time(9, 0),
            end_time=time(10, 0),
        )

        error = service._validate_add_operation_timing(operation, instructor_id)
        assert error is not None
        assert "past date" in error.lower()

    def test_validate_remove_operation_detects_existing_window(
        self, db: Session, test_instructor_with_availability: User
    ) -> None:
        """_validate_remove_operation confirms bitmap windows exist."""
        service = BulkOperationService(db)
        instructor_id = test_instructor_with_availability.id
        today = date.today()
        windows = get_day_windows(db, instructor_id, today)
        if not windows:
            seed_day(db, instructor_id, today, [("08:00:00", "09:00:00")])
            windows = [("08:00:00", "09:00:00")]
        start, end = windows[0]

        operation = SlotOperation(
            action="remove",
            date=today,
            start_time=string_to_time(start),
            end_time=string_to_time(end),
        )

        slot, error = service._validate_remove_operation(instructor_id, operation)
        assert error is None
        assert slot is not None

    def test_get_existing_week_windows_returns_bitmap_windows(
        self, db: Session, test_instructor: User
    ) -> None:
        """_get_existing_week_windows flattens AvailabilityDay rows into strings."""
        service = BulkOperationService(db)
        instructor_id = test_instructor.id
        monday = date.today() - timedelta(days=date.today().weekday())
        tuesday = monday + timedelta(days=1)

        seed_day(db, instructor_id, monday, [("09:00:00", "10:00:00")])
        seed_day(db, instructor_id, tuesday, [("14:00:00", "15:00:00")])

        windows = service._get_existing_week_windows(instructor_id, monday)
        assert windows[monday.isoformat()] == [{"start_time": "09:00:00", "end_time": "10:00:00"}]
        assert windows[tuesday.isoformat()] == [{"start_time": "14:00:00", "end_time": "15:00:00"}]
