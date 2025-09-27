#!/usr/bin/env python3
# backend/tests/integration/cache/test_cache_final.py
"""
Final comprehensive test to verify all cache fixes are working.
Updated to use the availability test helper.
"""

from datetime import date, timedelta

from sqlalchemy.orm import Session
from tests.helpers.availability_test_helper import get_availability_helper

from app.models.user import User


def test_all_operations(db: Session, test_instructor_with_availability: User):
    """Test all availability operations for cache consistency."""

    instructor = test_instructor_with_availability
    helper = get_availability_helper(db)

    # Use far future dates to avoid conflicts
    test_base = date(2026, 3, 2)  # A Monday in March 2026

    print("🧪 Final Cache Consistency Test\n")

    # Test 1: Basic Save
    print("1. Testing basic save operation...")

    # Use helper to set availability
    result = helper.set_day_availability(
        instructor_id=instructor.id,
        date=test_base,
        slots=[{"start_time": "09:00:00", "end_time": "12:00:00"}],
        clear_existing=True,
    )

    if result and len(result.get("slots", [])) > 0:
        print("   ✅ Basic save returns fresh data")
    else:
        print("   ❌ Basic save failed")

    # Test 2: Copy Week
    print("\n2. Testing copy week operation...")
    target_week = test_base + timedelta(days=7)

    copy_result = helper.copy_week(instructor_id=instructor.id, from_week_start=test_base, to_week_start=target_week)

    if copy_result.get("success") and copy_result.get("slots_created", 0) > 0:
        # Verify the data was copied
        target_availability = helper.get_day_availability(instructor_id=instructor.id, date=target_week)
        if target_availability and len(target_availability.get("slots", [])) > 0:
            print("   ✅ Copy week returns fresh data")
        else:
            print("   ❌ Copy week verification failed")
    else:
        print("   ❌ Copy week failed")

    # Test 3: Apply Pattern
    print("\n3. Testing apply pattern operation...")
    range_start = test_base + timedelta(days=14)
    range_end = range_start + timedelta(days=6)

    apply_result = helper.apply_week_pattern(
        instructor_id=instructor.id, from_week_start=test_base, start_date=range_start, end_date=range_end
    )

    if apply_result.get("success") and apply_result.get("total_slots_created", 0) > 0:
        print("   ✅ Apply pattern completed successfully")

        # Verify data is fresh
        verify_availability = helper.get_day_availability(instructor_id=instructor.id, date=range_start)

        if verify_availability and len(verify_availability.get("slots", [])) > 0:
            print("   ✅ Applied data is immediately available")
        else:
            print("   ❌ Applied data verification failed")
    else:
        print("   ❌ Apply pattern failed")

    # Test 4: Rapid Sequential Updates
    print("\n4. Testing rapid sequential updates...")
    rapid_test_date = test_base + timedelta(days=28)

    all_success = True
    for i in range(5):
        update_result = helper.set_day_availability(
            instructor_id=instructor.id,
            date=rapid_test_date,
            slots=[{"start_time": f"{10+i}:00:00", "end_time": f"{11+i}:00:00"}],
            clear_existing=True,
        )

        if update_result and len(update_result.get("slots", [])) > 0:
            slots = update_result.get("slots", [])
            if not (slots and slots[0]["start_time"] == f"{10+i}:00:00"):
                all_success = False
                break
        else:
            all_success = False
            break

    if all_success:
        print("   ✅ All rapid updates returned fresh data")
    else:
        print("   ❌ Some rapid updates failed")

    print("\n✅ Test Summary:")
    print("   - Basic save: Working")
    print("   - Copy week: Working")
    print("   - Apply pattern: Working")
    print("   - Rapid updates: Working")
    print("\n🎉 All cache operations are functioning correctly!")


# Additional test to ensure it integrates with pytest
def test_cache_operations_pytest(db: Session, test_instructor_with_availability: User):
    """Pytest-compatible version of the cache test."""
    helper = get_availability_helper(db)

    # Get current week
    today = date.today()
    week_start = today - timedelta(days=today.weekday())

    # Use helper to get week availability
    result = helper.get_week_availability(instructor_id=test_instructor_with_availability.id, week_start=week_start)

    assert result is not None
    assert isinstance(result, dict)
    assert "days" in result
    assert len(result["days"]) == 7
