#!/usr/bin/env python3
# backend/scripts/quick_test_fixes.py
"""Quick test to verify both fixes work correctly."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date, time, timedelta

from pydantic import ValidationError


def test_booking_create_fix():
    """Test that BookingCreate rejects extra fields."""
    from app.schemas.booking import BookingCreate

    print("1. Testing BookingCreate extra field rejection...")

    # Should work
    try:
        booking = BookingCreate(
            instructor_id=1,
            service_id=2,
            booking_date=date.today() + timedelta(days=1),
            start_time=time(9, 0),
            end_time=time(10, 0),
        )
        print("   ✅ Valid booking created")
    except Exception as e:
        print(f"   ❌ Failed: {e}")
        return False

    # Should fail
    try:
        BookingCreate(
            availability_slot_id=123,  # Extra field!
            instructor_id=1,
            service_id=2,
            booking_date=date.today() + timedelta(days=1),
            start_time=time(9, 0),
            end_time=time(10, 0),
        )
        print("   ❌ ERROR: Accepted availability_slot_id!")
        return False
    except ValidationError as e:
        if "Extra inputs are not permitted" in str(e):
            print("   ✅ Correctly rejected availability_slot_id")
        else:
            print(f"   ✅ Rejected with: {e.errors()[0]['msg']}")

    return True


def test_schema_separation():
    """Test that booking and availability schemas are properly separated."""
    print("\n2. Testing schema separation...")

    # Import both modules
    from app.schemas import booking

    # Check what's in booking module
    booking_attrs = dir(booking)

    # These are OK - they're booking-related schemas
    ok_availability_names = ["AvailabilityCheckRequest", "AvailabilityCheckResponse"]

    # These would be problems - actual availability slot schemas
    bad_imports = ["AvailabilitySlot", "AvailabilitySlotCreate", "AvailabilitySlotResponse"]

    found_bad = [imp for imp in bad_imports if imp in booking_attrs]

    if found_bad:
        print(f"   ❌ Found availability slot imports in booking: {found_bad}")
        return False

    print("   ✅ No AvailabilitySlot schemas imported in booking module")

    # Verify the OK ones are there (they should be)
    found_ok = [imp for imp in ok_availability_names if imp in booking_attrs]
    print(f"   ℹ️  Booking module has these schemas: {found_ok}")
    print("      (These are booking schemas despite the names)")

    return True


def main():
    print("QUICK FIX VERIFICATION")
    print("=" * 50)

    success = True

    # Test 1: Extra field rejection
    if not test_booking_create_fix():
        success = False

    # Test 2: Schema separation
    if not test_schema_separation():
        success = False

    print("\n" + "=" * 50)
    if success:
        print("✅ ALL FIXES VERIFIED!")
        print("\nRun the full test suite with:")
        print("  python backend/scripts/run_architecture_tests.py")
        return 0
    else:
        print("❌ Some fixes failed verification")
        return 1


if __name__ == "__main__":
    sys.exit(main())
