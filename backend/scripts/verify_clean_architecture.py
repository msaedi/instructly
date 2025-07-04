#!/usr/bin/env python3
# backend/scripts/verify_clean_architecture.py
"""
Verify that the clean architecture has been implemented correctly.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date, time, timedelta

from pydantic import ValidationError


def test_booking_clean_architecture():
    """Test booking schemas follow clean architecture."""
    print("Testing BookingCreate schema...")

    from app.schemas.booking import BookingCreate

    # Test 1: Valid booking with self-contained time
    try:
        booking = BookingCreate(
            instructor_id=1,
            service_id=2,
            booking_date=date.today() + timedelta(days=1),
            start_time=time(9, 0),
            end_time=time(10, 30),
            student_note="Looking forward to the lesson!",
        )
        print("✅ BookingCreate works with time-based booking")
        print(f"   - Date: {booking.booking_date}")
        print(f"   - Time: {booking.start_time} - {booking.end_time}")
    except Exception as e:
        print(f"❌ BookingCreate failed: {e}")
        return False

    # Test 2: Reject slot_id (clean architecture)
    try:
        bad_booking = BookingCreate(
            availability_slot_id=123,  # Should be rejected!
            instructor_id=1,
            service_id=2,
            booking_date=date.today() + timedelta(days=1),
            start_time=time(9, 0),
            end_time=time(10, 0),
        )
        print("❌ BookingCreate accepted slot_id - architecture violation!")
        return False
    except ValidationError as e:
        error_msg = str(e.errors()[0]["msg"])
        if "Extra inputs are not permitted" in error_msg:
            print("✅ BookingCreate correctly rejects availability_slot_id")
        else:
            print(f"✅ BookingCreate rejects slot_id (error: {error_msg})")
    except Exception as e:
        print(f"✅ BookingCreate rejects slot_id (error type: {type(e).__name__})")

    # Test 3: Validate time order
    try:
        BookingCreate(
            instructor_id=1,
            service_id=2,
            booking_date=date.today() + timedelta(days=1),
            start_time=time(10, 0),
            end_time=time(9, 0),  # Invalid!
        )
        print("❌ BookingCreate accepted invalid time order!")
        return False
    except ValidationError:
        print("✅ BookingCreate validates time order correctly")

    return True


def test_availability_clean_architecture():
    """Test availability schemas follow clean architecture."""
    print("\nTesting Availability schemas...")

    from app.schemas.availability import AvailabilitySlot, AvailabilitySlotCreate

    # Test 1: Single-table design
    try:
        slot = AvailabilitySlotCreate(
            instructor_id=1, date=date.today() + timedelta(days=1), start_time=time(14, 0), end_time=time(15, 0)
        )
        print("✅ AvailabilitySlotCreate uses single-table design")
        print(f"   - Instructor: {slot.instructor_id}")
        print(f"   - Date: {slot.date}")
    except Exception as e:
        print(f"❌ AvailabilitySlotCreate failed: {e}")
        return False

    # Test 2: No is_available field
    slot_data = AvailabilitySlot(id=1, instructor_id=1, date=date.today(), start_time=time(9, 0), end_time=time(10, 0))

    if hasattr(slot_data, "is_available"):
        print("❌ AvailabilitySlot has is_available field - should be removed!")
        return False
    else:
        print("✅ AvailabilitySlot has no is_available field (slots exist = available)")

    return True


def test_dead_code_removal():
    """Test that dead code has been removed."""
    print("\nTesting dead code removal...")

    # Test 1: DayOfWeekEnum should not exist
    try:
        print("❌ DayOfWeekEnum still exists - should be removed!")
        return False
    except (ImportError, AttributeError):
        print("✅ DayOfWeekEnum has been removed")

    # Test 2: DateTimeSlot should only exist in one place
    try:
        print("❌ DateTimeSlot exists in availability.py - should be removed!")
        return False
    except (ImportError, AttributeError):
        print("✅ DateTimeSlot removed from availability.py")

    # Should exist in availability_window
    try:
        print("✅ DateTimeSlot exists only in availability_window.py")
    except ImportError:
        print("❌ DateTimeSlot missing from availability_window.py!")
        return False

    return True


def test_new_patterns():
    """Test new architectural patterns."""
    print("\nTesting new architectural patterns...")

    from app.schemas.booking import AvailabilityCheckRequest, FindBookingOpportunitiesRequest

    # Test 1: AvailabilityCheckRequest uses time-based checking
    try:
        check = AvailabilityCheckRequest(
            instructor_id=1,
            service_id=2,
            booking_date=date.today() + timedelta(days=1),
            start_time=time(14, 0),
            end_time=time(15, 0),
        )
        print("✅ AvailabilityCheckRequest uses instructor/date/time pattern")
    except Exception as e:
        print(f"❌ AvailabilityCheckRequest failed: {e}")
        return False

    # Test 2: New booking opportunities pattern
    try:
        opportunities = FindBookingOpportunitiesRequest(
            instructor_id=1,
            service_id=2,
            date_range_start=date.today(),
            date_range_end=date.today() + timedelta(days=7),
        )
        print("✅ FindBookingOpportunitiesRequest implements new pattern")
    except Exception as e:
        print(f"❌ FindBookingOpportunitiesRequest failed: {e}")
        return False

    return True


def main():
    """Run all verification tests."""
    print("=" * 60)
    print("CLEAN ARCHITECTURE VERIFICATION")
    print("=" * 60)

    all_passed = True

    # Run each test suite
    all_passed &= test_booking_clean_architecture()
    all_passed &= test_availability_clean_architecture()
    all_passed &= test_dead_code_removal()
    all_passed &= test_new_patterns()

    print("\n" + "=" * 60)
    if all_passed:
        print("✅ ALL VERIFICATIONS PASSED!")
        print("Clean architecture has been successfully implemented!")
    else:
        print("❌ Some verifications failed.")
        print("Please check the errors above.")
    print("=" * 60)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
