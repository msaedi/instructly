#!/usr/bin/env python3
# backend/tests/integration/cache/test_cache_fix_improved.py
"""
Improved test script with better error handling and diagnostics.
"""

import json
import time
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.auth import create_access_token
from app.models.user import User
from app.services.availability_service import AvailabilityService


def get_auth_token(email: str) -> str:
    """Get auth token for testing without HTTP calls."""
    return create_access_token(data={"sub": email})


def test_basic_save_operation(db: Session, test_instructor_with_availability: User):
    """Test a basic save operation with detailed diagnostics."""

    instructor = test_instructor_with_availability
    availability_service = AvailabilityService(db)

    # Get next Monday
    today = date.today()
    days_until_monday = (7 - today.weekday()) % 7
    if days_until_monday == 0:
        days_until_monday = 7
    next_monday = today + timedelta(days=days_until_monday)

    print(f"\n=== Testing Basic Save Operation for {next_monday} ===")

    # First, check current state
    print("\n1. Checking current availability...")
    current_data = availability_service.get_week_availability(instructor_id=instructor.id, week_start=next_monday)

    current_slots = current_data.get(next_monday.isoformat(), [])
    print(f"   Current slots for Monday: {len(current_slots)}")
    if current_slots:
        print(f"   First slot: {current_slots[0]['start_time']} - {current_slots[0]['end_time']}")

    # Now save new availability
    print("\n2. Saving new availability...")
    test_slots = [{"start_time": "14:00:00", "end_time": "17:00:00"}]

    print(f"   New slots: {json.dumps(test_slots, indent=2)}")

    save_start = time.time()

    result = availability_service.set_day_availability(
        instructor_id=instructor.id, date=next_monday, slots=test_slots, clear_existing=True
    )

    save_duration = time.time() - save_start
    print(f"   Save took: {save_duration:.3f}s")

    if result and result.get("success", True):
        monday_slots = result.get("slots", [])

        if monday_slots:
            print(f"   ✅ SUCCESS: Got {len(monday_slots)} slots")
            print(f"   Slot: {monday_slots[0]['start_time']} - {monday_slots[0]['end_time']}")
        else:
            print("   ❌ FAIL: No slots in response")
    else:
        print(f"   ❌ ERROR: Save operation failed")
        print(f"   Error: {result.get('error', 'Unknown error')}")

    # Verify independently
    print("\n3. Independent verification...")
    time.sleep(0.5)  # Small delay

    verify_data = availability_service.get_week_availability(instructor_id=instructor.id, week_start=next_monday)

    verify_slots = verify_data.get(next_monday.isoformat(), [])
    print(f"   Verified slots: {len(verify_slots)}")
    if verify_slots:
        print(f"   Verified slot: {verify_slots[0]['start_time']} - {verify_slots[0]['end_time']}")

        # Check if it matches what we saved
        if verify_slots[0]["start_time"] == "14:00:00":
            print("   ✅ Cache consistency verified!")
        else:
            print("   ❌ Cache inconsistency detected!")


def test_rapid_updates(db: Session, test_instructor_with_availability: User):
    """Test rapid sequential updates."""

    instructor = test_instructor_with_availability
    availability_service = AvailabilityService(db)

    # Get next Monday
    today = date.today()
    days_until_monday = (7 - today.weekday()) % 7
    if days_until_monday == 0:
        days_until_monday = 7
    next_monday = today + timedelta(days=days_until_monday)

    print(f"\n=== Testing Rapid Sequential Updates ===")

    times = ["09:00:00", "10:00:00", "11:00:00", "12:00:00", "13:00:00"]

    for i, start_time in enumerate(times):
        print(f"\nUpdate {i+1}/5: Setting time to {start_time}")

        test_slots = [{"start_time": start_time, "end_time": "17:00:00"}]

        # Save
        result = availability_service.set_day_availability(
            instructor_id=instructor.id, date=next_monday, slots=test_slots, clear_existing=True
        )

        if result and result.get("success", True):
            slots = result.get("slots", [])
            if slots and slots[0]["start_time"] == start_time:
                print(f"   ✅ Immediately got fresh data: {start_time}")
            else:
                print(f"   ❌ Got stale data!")
        else:
            print(f"   ❌ Failed to save")

        # No delay between updates

    # Final check
    print("\nFinal state check...")
    final_data = availability_service.get_week_availability(instructor_id=instructor.id, week_start=next_monday)

    final_slots = final_data.get(next_monday.isoformat(), [])
    if final_slots:
        print(f"Final slot time: {final_slots[0]['start_time']} (should be 13:00:00)")
        assert final_slots[0]["start_time"] == "13:00:00", "Final slot time doesn't match expected"


# Pytest-style tests
def test_save_and_retrieve(db: Session, test_instructor_with_availability: User):
    """Test saving and retrieving availability data."""
    availability_service = AvailabilityService(db)

    # Use a future date
    test_date = date.today() + timedelta(days=30)

    # Save slots
    result = availability_service.set_day_availability(
        instructor_id=test_instructor_with_availability.id,
        date=test_date,
        slots=[{"start_time": "10:00:00", "end_time": "12:00:00"}],
        clear_existing=True,
    )

    assert result is not None
    assert len(result.get("slots", [])) == 1
    assert result["slots"][0]["start_time"] == "10:00:00"
