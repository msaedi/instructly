#!/usr/bin/env python3
# backend/tests/schemas/run_validator_test.py
"""Direct test of the validator fixes."""

import os
import sys

# Add the backend directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from datetime import date, time, timedelta

from pydantic import ValidationError

try:
    from app.schemas.booking import BookingCreate

    print("Testing BookingCreate with valid data...")
    booking = BookingCreate(
        instructor_id=1,
        service_id=1,
        booking_date=date.today() + timedelta(days=1),
        start_time=time(9, 0),
        end_time=time(10, 0),
    )
    print("✅ Valid booking created successfully!")
    print(f"   Start: {booking.start_time}, End: {booking.end_time}")

    print("\nTesting BookingCreate with invalid time order...")
    try:
        invalid_booking = BookingCreate(
            instructor_id=1,
            service_id=1,
            booking_date=date.today() + timedelta(days=1),
            start_time=time(10, 0),
            end_time=time(9, 0),  # Before start time
        )
        print("❌ Should have raised ValidationError!")
    except ValidationError as e:
        print("✅ ValidationError raised as expected!")
        print(f"   Error: {e.errors()[0]['msg']}")

    print("\nTesting BookingCreate with past date...")
    try:
        past_booking = BookingCreate(
            instructor_id=1,
            service_id=1,
            booking_date=date.today() - timedelta(days=1),
            start_time=time(9, 0),
            end_time=time(10, 0),
        )
        print("❌ Should have raised ValidationError!")
    except ValidationError as e:
        print("✅ ValidationError raised as expected!")
        print(f"   Error: {e.errors()[0]['msg']}")

    print("\nTesting that extra fields are rejected...")
    try:
        slot_booking = BookingCreate(
            availability_slot_id=123,  # Should be rejected
            instructor_id=1,
            service_id=1,
            booking_date=date.today() + timedelta(days=1),
            start_time=time(9, 0),
            end_time=time(10, 0),
        )
        print("❌ Should have raised ValidationError!")
    except ValidationError as e:
        print("✅ ValidationError raised as expected!")
        print(f"   Error: {e.errors()[0]['msg']}")

except Exception as e:
    print(f"❌ Error: {type(e).__name__}: {e}")
    import traceback

    traceback.print_exc()

print("\nValidator test complete!")
