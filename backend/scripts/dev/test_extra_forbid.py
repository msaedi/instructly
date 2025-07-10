#!/usr/bin/env python3
# backend/scripts/test_extra_forbid.py
"""Test that BookingCreate properly rejects extra fields."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date, time, timedelta

from pydantic import ValidationError


def main():
    print("Testing BookingCreate extra field rejection...")
    print("=" * 60)

    from app.schemas.booking import BookingCreate

    # Test 1: Valid booking
    print("\nTest 1: Creating valid booking...")
    try:
        booking = BookingCreate(
            instructor_id=1,
            service_id=2,
            booking_date=date.today() + timedelta(days=1),
            start_time=time(9, 0),
            end_time=time(10, 0),
        )
        print("✅ Valid booking created successfully")
    except Exception as e:
        print(f"❌ Failed to create valid booking: {e}")
        return 1

    # Test 2: Reject availability_slot_id
    print("\nTest 2: Rejecting availability_slot_id...")
    try:
        bad_booking = BookingCreate(
            availability_slot_id=123,  # Should be rejected!
            instructor_id=1,
            service_id=2,
            booking_date=date.today() + timedelta(days=1),
            start_time=time(9, 0),
            end_time=time(10, 0),
        )
        print("❌ ERROR: BookingCreate accepted availability_slot_id!")
        print(f"   Got: {bad_booking}")
        return 1
    except ValidationError as e:
        print("✅ BookingCreate correctly rejected availability_slot_id")
        error_msg = str(e.errors()[0]["msg"])
        print(f"   Error: {error_msg}")
        if "Extra inputs are not permitted" in error_msg:
            print("   ✅ Correct error message")
        else:
            print(f"   ⚠️  Unexpected error message: {error_msg}")

    # Test 3: Reject any extra field
    print("\nTest 3: Rejecting other extra fields...")
    try:
        BookingCreate(
            instructor_id=1,
            service_id=2,
            booking_date=date.today() + timedelta(days=1),
            start_time=time(9, 0),
            end_time=time(10, 0),
            some_random_field="should fail",  # Any extra field
        )
        print("❌ ERROR: BookingCreate accepted extra field!")
        return 1
    except ValidationError:
        print("✅ BookingCreate correctly rejected extra field")

    print("\n" + "=" * 60)
    print("✅ ALL TESTS PASSED! Clean architecture enforced.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
