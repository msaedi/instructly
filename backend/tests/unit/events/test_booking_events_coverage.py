"""
Coverage tests for app/events/booking_events.py — targeting uncovered lines:
  L41: BookingReminder.to_dict()
  L52: BookingCompleted.to_dict()

Also covers all event types and their serialization.

Bug hunts:
  - Missing fields in to_dict output
  - Optional field None handling
"""

from datetime import datetime, timezone

from app.events.booking_events import (
    BookingCancelled,
    BookingCompleted,
    BookingCreated,
    BookingReminder,
)


class TestBookingCreated:
    def test_to_dict(self):
        now = datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
        event = BookingCreated(
            booking_id="bk_01ABC",
            student_id="st_01ABC",
            instructor_id="in_01ABC",
            created_at=now,
        )
        result = event.to_dict()
        assert result["booking_id"] == "bk_01ABC"
        assert result["student_id"] == "st_01ABC"
        assert result["instructor_id"] == "in_01ABC"
        assert result["created_at"] == now

    def test_all_fields_present(self):
        event = BookingCreated(
            booking_id="bk_01ABC",
            student_id="st_01ABC",
            instructor_id="in_01ABC",
            created_at=datetime.now(timezone.utc),
        )
        d = event.to_dict()
        assert set(d.keys()) == {"booking_id", "student_id", "instructor_id", "created_at"}


class TestBookingCancelled:
    def test_to_dict_with_refund(self):
        now = datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
        event = BookingCancelled(
            booking_id="bk_01ABC",
            cancelled_by="student",
            cancelled_at=now,
            refund_amount=49.99,
        )
        result = event.to_dict()
        assert result["booking_id"] == "bk_01ABC"
        assert result["cancelled_by"] == "student"
        assert result["refund_amount"] == 49.99

    def test_to_dict_without_refund(self):
        """Optional refund_amount defaults to None."""
        event = BookingCancelled(
            booking_id="bk_01ABC",
            cancelled_by="instructor",
            cancelled_at=datetime.now(timezone.utc),
        )
        result = event.to_dict()
        assert result["refund_amount"] is None

    def test_to_dict_with_zero_refund(self):
        """Edge case: 0.0 refund is valid."""
        event = BookingCancelled(
            booking_id="bk_01ABC",
            cancelled_by="student",
            cancelled_at=datetime.now(timezone.utc),
            refund_amount=0.0,
        )
        result = event.to_dict()
        assert result["refund_amount"] == 0.0


class TestBookingReminder:
    def test_to_dict_24h(self):
        """L41: BookingReminder.to_dict()."""
        event = BookingReminder(
            booking_id="bk_01ABC",
            reminder_type="24h",
        )
        result = event.to_dict()
        assert result["booking_id"] == "bk_01ABC"
        assert result["reminder_type"] == "24h"

    def test_to_dict_1h(self):
        event = BookingReminder(
            booking_id="bk_01ABC",
            reminder_type="1h",
        )
        result = event.to_dict()
        assert result["reminder_type"] == "1h"

    def test_all_fields_present(self):
        event = BookingReminder(booking_id="bk_01ABC", reminder_type="24h")
        d = event.to_dict()
        assert set(d.keys()) == {"booking_id", "reminder_type"}


class TestBookingCompleted:
    def test_to_dict(self):
        """L52: BookingCompleted.to_dict()."""
        now = datetime(2025, 6, 15, 14, 0, 0, tzinfo=timezone.utc)
        event = BookingCompleted(
            booking_id="bk_01ABC",
            completed_at=now,
        )
        result = event.to_dict()
        assert result["booking_id"] == "bk_01ABC"
        assert result["completed_at"] == now

    def test_all_fields_present(self):
        event = BookingCompleted(
            booking_id="bk_01ABC",
            completed_at=datetime.now(timezone.utc),
        )
        d = event.to_dict()
        assert set(d.keys()) == {"booking_id", "completed_at"}
