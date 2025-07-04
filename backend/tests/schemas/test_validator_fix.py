# backend/tests/schemas/test_validator_fix.py
"""Quick test to verify Pydantic v2 validators work correctly."""

from datetime import date, time, timedelta

import pytest
from pydantic import ValidationError

from app.schemas.booking import BookingCreate


def test_booking_create_validator_fix():
    """Test that validators work with Pydantic v2 syntax."""
    # Valid booking
    booking = BookingCreate(
        instructor_id=1,
        service_id=1,
        booking_date=date.today() + timedelta(days=1),
        start_time=time(9, 0),
        end_time=time(10, 0),
    )
    assert booking.start_time < booking.end_time

    # Invalid time order
    with pytest.raises(ValidationError) as exc:
        BookingCreate(
            instructor_id=1,
            service_id=1,
            booking_date=date.today() + timedelta(days=1),
            start_time=time(10, 0),
            end_time=time(9, 0),  # Before start
        )
    assert "End time must be after start time" in str(exc.value)


if __name__ == "__main__":
    test_booking_create_validator_fix()
    print("✅ Validator fix works!")
