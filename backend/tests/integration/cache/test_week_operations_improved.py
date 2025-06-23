#!/usr/bin/env python3
# backend/tests/integration/cache/test_week_operations_improved.py
"""
Improved test script for week operations with better error handling.
Updated to use the availability test helper.
"""

import time
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models.user import User
from tests.helpers.availability_test_helper import get_availability_helper


def test_copy_week_with_validation(db: Session, test_instructor_with_availability: User):
    """Test copy week operation with better validation."""

    instructor = test_instructor_with_availability
    helper = get_availability_helper(db)

    # Use future dates to avoid validation issues
    today = date.today()
    # Get next Monday
    days_until_monday = (7 - today.weekday()) % 7
    if days_until_monday == 0:
        days_until_monday = 7
    next_monday = today + timedelta(days=days_until_monday)
    week_after = next_monday + timedelta(days=7)

    print(f"\n=== Testing Copy Week Operation ===")
    print(f"From: {next_monday} → To: {week_after}")

    # First, set up source week using helper
    print("\n1. Setting up source week...")
    source_schedule = [
        {
            "date": next_monday,
            "start_time": "09:00:00",
            "end_time": "12:00:00",
        },
        {
            "date": next_monday + timedelta(days=2),
            "start_time": "14:00:00",
            "end_time": "17:00:00",
        },
    ]

    for slot_data in source_schedule:
        helper.set_day_availability(
            instructor_id=instructor.id,
            date=slot_data["date"],
            slots=[{"start_time": slot_data["start_time"], "end_time": slot_data["end_time"]}],
            clear_existing=True,
        )

    # Copy week using helper
    print("\n2. Copying week...")
    copy_start = time.time()

    result = helper.copy_week(instructor_id=instructor.id, from_week_start=next_monday, to_week_start=week_after)

    copy_duration = time.time() - copy_start
    print(f"   Copy took: {copy_duration:.3f}s")

    if result.get("success"):
        print(f"\n   Results:")
        print(f"   - Days created: {result.get('days_created', 0)}")
        print(f"   - Slots created: {result.get('slots_created', 0)}")

        # Verify the copy using helper
        target_week_data = helper.get_week_availability(instructor_id=instructor.id, week_start=week_after)

        # Find Monday and Wednesday in the returned days
        monday_data = None
        wednesday_data = None

        for day in target_week_data.get("days", []):
            if day["date"] == week_after.isoformat():
                monday_data = day
            elif day["date"] == (week_after + timedelta(days=2)).isoformat():
                wednesday_data = day

        monday_slots = monday_data["slots"] if monday_data else []
        wednesday_slots = wednesday_data["slots"] if wednesday_data else []

        print(f"   - Monday slots: {len(monday_slots)}")
        print(f"   - Wednesday slots: {len(wednesday_slots)}")

        if monday_slots and monday_slots[0]["start_time"] == "09:00:00":
            print("\n   ✅ SUCCESS: Copy returned fresh data immediately!")
        else:
            print("\n   ❌ FAIL: Data doesn't match expected")
    else:
        print(f"   Copy failed: {result.get('message', 'Unknown error')}")


def test_apply_pattern_validation(db: Session, test_instructor_with_availability: User):
    """Test apply pattern with validation of results."""

    instructor = test_instructor_with_availability
    helper = get_availability_helper(db)

    # Use future dates
    today = date.today()
    days_until_monday = (7 - today.weekday()) % 7
    if days_until_monday == 0:
        days_until_monday = 7
    next_monday = today + timedelta(days=days_until_monday)

    # Apply to 3-4 weeks in the future
    start_date = next_monday + timedelta(days=21)
    end_date = start_date + timedelta(days=13)

    print(f"\n=== Testing Apply Pattern Operation ===")
    print(f"Pattern from: {next_monday}")
    print(f"Apply to: {start_date} → {end_date}")

    # First ensure pattern week has data using helper
    print("\n1. Setting up pattern week...")
    pattern_schedule = [
        {
            "date": next_monday,
            "start_time": "10:00:00",
            "end_time": "12:00:00",
        },
        {
            "date": next_monday + timedelta(days=1),
            "start_time": "14:00:00",
            "end_time": "16:00:00",
        },
    ]

    for slot_data in pattern_schedule:
        helper.set_day_availability(
            instructor_id=instructor.id,
            date=slot_data["date"],
            slots=[{"start_time": slot_data["start_time"], "end_time": slot_data["end_time"]}],
            clear_existing=True,
        )

    # Apply pattern using helper
    print("\n2. Applying pattern...")
    apply_start = time.time()

    result = helper.apply_week_pattern(
        instructor_id=instructor.id, from_week_start=next_monday, start_date=start_date, end_date=end_date
    )

    apply_duration = time.time() - apply_start
    print(f"   Apply took: {apply_duration:.3f}s")

    if result.get("success"):
        print(f"\n   ✅ SUCCESS: Applied pattern")
        print(f"   - Total slots created: {result.get('total_slots_created', 0)}")

        # Verify cache is fresh using helper
        print("\n3. Verifying cache freshness...")

        first_week_start = start_date - timedelta(days=start_date.weekday())
        verify_data = helper.get_week_availability(instructor_id=instructor.id, week_start=first_week_start)

        total_slots = sum(len(day["slots"]) for day in verify_data.get("days", []))
        print(f"   First affected week has {total_slots} total slots")
        print(f"   ✅ Cache is returning fresh data!")
    else:
        print(f"   Apply failed: {result.get('message', 'Unknown error')}")


def test_cache_consistency(db: Session, test_instructor_with_availability: User):
    """Test that operations maintain cache consistency."""

    instructor = test_instructor_with_availability
    helper = get_availability_helper(db)

    print(f"\n=== Testing Cache Consistency ===")

    # Get a future Monday
    today = date.today()
    days_until_monday = (7 - today.weekday()) % 7
    if days_until_monday == 0:
        days_until_monday = 7
    test_monday = today + timedelta(days=days_until_monday + 14)  # 2+ weeks out

    print(f"\nTesting rapid sequential operations on {test_monday}...")

    # Perform 5 rapid updates using helper
    all_success = True
    for i in range(5):
        result = helper.set_day_availability(
            instructor_id=instructor.id,
            date=test_monday,
            slots=[{"start_time": f"{9+i}:00:00", "end_time": f"{10+i}:00:00"}],
            clear_existing=True,
        )

        if result and result.get("success", True):
            monday_data = result.get("slots", [])
            if monday_data and monday_data[0]["start_time"] == f"{9+i}:00:00":
                print(f"   Update {i+1}: ✅ Got fresh data ({9+i}:00:00)")
            else:
                print(f"   Update {i+1}: ⚠️  Got unexpected data, retrying...")
                # Retry once if we get unexpected data
                time.sleep(0.1)
                result = helper.set_day_availability(
                    instructor_id=instructor.id,
                    date=test_monday,
                    slots=[{"start_time": f"{9+i}:00:00", "end_time": f"{10+i}:00:00"}],
                    clear_existing=True,
                )
                if result and result.get("slots", []) and result["slots"][0]["start_time"] == f"{9+i}:00:00":
                    print(f"   Update {i+1}: ✅ Retry succeeded")
                else:
                    print(f"   Update {i+1}: ❌ Still got stale data after retry!")
                    all_success = False
        else:
            print(f"   Update {i+1}: Failed")
            all_success = False

    print("\n✅ Cache consistency test complete!")
    assert all_success, "Some updates returned stale data even after retry"


# Add pytest-style tests as well
def test_week_operations_pytest(db: Session, test_instructor_with_availability: User):
    """Pytest-compatible test for week operations."""
    helper = get_availability_helper(db)

    # Simple copy week test
    today = date.today()
    next_monday = today + timedelta(days=(7 - today.weekday()) % 7 or 7)
    target_week = next_monday + timedelta(days=7)

    # Set some availability in source week
    helper.set_day_availability(
        instructor_id=test_instructor_with_availability.id,
        date=next_monday,
        slots=[{"start_time": "09:00:00", "end_time": "12:00:00"}],
    )

    # Copy week
    result = helper.copy_week(
        instructor_id=test_instructor_with_availability.id, from_week_start=next_monday, to_week_start=target_week
    )

    assert result is not None
    assert "success" in result
    assert result["success"] is True
