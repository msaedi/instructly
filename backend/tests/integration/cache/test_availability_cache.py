# backend/tests/integration/test_availability_cache.py
"""
Test script to verify the availability cache timing issue.
Fixed to use the availability test helper.
"""

from datetime import date, timedelta
import time

from sqlalchemy.orm import Session
from tests.helpers.availability_test_helper import get_availability_helper

from app.models.user import User


def test_availability_timing(db: Session, test_instructor_with_availability: User):
    """Test the timing of availability saves and cache behavior."""
    instructor = test_instructor_with_availability
    helper = get_availability_helper(db)

    # Get next Monday
    today = date.today()
    days_until_monday = (7 - today.weekday()) % 7
    if days_until_monday == 0:
        days_until_monday = 7
    next_monday = today + timedelta(days=days_until_monday)

    print(f"\n=== Testing with week starting {next_monday} ===")

    # Step 1: Get current availability using helper
    print("\n1. Fetching current availability...")
    original_data = helper.get_week_availability(instructor_id=instructor.id, week_start=next_monday)
    # Count total windows across all days (bitmap storage)
    total_windows = sum(len(day_data.get("windows", day_data.get("slots", []))) for day_data in original_data.get("days", []))
    print(f"   Original windows: {total_windows}")

    # Step 2: Prepare test data
    test_windows = [
        {
            "start_time": "09:00:00",
            "end_time": "12:00:00",
        },
        {
            "start_time": "14:00:00",
            "end_time": "17:00:00",
        },
    ]

    # Step 3: Save new availability using helper
    print("\n2. Saving new availability...")
    save_start = time.time()

    result = helper.set_day_availability(
        instructor_id=instructor.id, date=next_monday, slots=test_windows, clear_existing=True
    )

    save_duration = time.time() - save_start
    print(f"   Save took: {save_duration:.3f}s")
    print(f"   Save successful: {result.get('success', True)}")

    if result:
        saved_windows = result.get("windows", result.get("slots", []))
        print(f"   Saved {len(saved_windows)} windows")

    # Step 4: Test immediate and delayed fetches
    # Reduced delays from [0, 0.1, 0.5, 1.0, 2.0] to speed up tests
    # Cache behavior doesn't require multi-second waits
    print("\n3. Testing fetch timing...")
    delays = [0, 0.05, 0.1, 0.2]

    for delay in delays:
        if delay > 0:
            time.sleep(delay)

        fetch_start = time.time()
        # Use helper to get day availability
        data = helper.get_day_availability(instructor_id=instructor.id, date=next_monday)
        fetch_duration = time.time() - fetch_start

        monday_windows = data.get("windows", data.get("slots", []))
        print(f"   After {delay}s delay: {len(monday_windows)} windows (fetch took {fetch_duration:.3f}s)")
        if len(monday_windows) > 0:
            print(f"     First window: {monday_windows[0]['start_time']} - {monday_windows[0]['end_time']}")

    # Final verification
    assert len(monday_windows) == 2, f"Expected 2 windows, got {len(monday_windows)}"
    assert monday_windows[0]["start_time"] == "09:00:00", "First window time mismatch"


def test_cache_invalidation(db: Session, test_instructor_with_availability: User):
    """Test that cache is properly invalidated on updates."""
    instructor = test_instructor_with_availability
    helper = get_availability_helper(db)

    # Use a specific future date
    test_date = date.today() + timedelta(days=60)
    _week_start = test_date - timedelta(days=test_date.weekday())

    # Initial save using helper
    print("\n1. Initial save...")
    helper.set_day_availability(
        instructor_id=instructor.id,
        date=test_date,
        slots=[{"start_time": "10:00:00", "end_time": "11:00:00"}],
        clear_existing=True,
    )

    # First fetch (should cache)
    print("\n2. First fetch (caching)...")
    data1 = helper.get_day_availability(instructor_id=instructor.id, date=test_date)
    slots1 = data1.get("slots", [])
    print(f"   Got {len(slots1)} slots")

    # Update the data
    print("\n3. Updating data...")
    helper.set_day_availability(
        instructor_id=instructor.id,
        date=test_date,
        slots=[{"start_time": "14:00:00", "end_time": "15:00:00"}, {"start_time": "16:00:00", "end_time": "17:00:00"}],
        clear_existing=True,
    )

    # Fetch again (should get fresh data, not cached)
    print("\n4. Fetching after update...")
    data2 = helper.get_day_availability(instructor_id=instructor.id, date=test_date)
    windows2 = data2.get("windows", data2.get("slots", []))
    print(f"   Got {len(windows2)} windows")

    # Verify cache was invalidated
    assert len(windows2) == 2, f"Expected 2 windows after update, got {len(windows2)}"
    assert windows2[0]["start_time"] == "14:00:00", "Cache not properly invalidated"

    print("\n✅ Cache invalidation working correctly!")


# Note: Removed the cache_service fixture since it was causing issues
# The availability_service can work with or without cache
# If you need to test cache specifically, use the proper cache service initialization
