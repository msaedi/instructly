#!/usr/bin/env python3
# backend/tests/integration/test_availability_cache.py
"""
Test script to verify the availability cache timing issue.
This will help us understand the exact timing of cache invalidation and data consistency.
"""

import time
from datetime import date, timedelta

import pytest
from sqlalchemy.orm import Session

from app.auth import create_access_token
from app.models.user import User
from app.services.availability_service import AvailabilityService
from app.services.cache_service import CacheService


def get_auth_token(email: str) -> str:
    """Get auth token for testing without HTTP calls."""
    return create_access_token(data={"sub": email})


def test_availability_timing(db: Session, test_instructor_with_availability: User):
    """Test the timing of availability saves and cache behavior."""

    instructor = test_instructor_with_availability
    availability_service = AvailabilityService(db)

    # Get next Monday
    today = date.today()
    days_until_monday = (7 - today.weekday()) % 7
    if days_until_monday == 0:
        days_until_monday = 7
    next_monday = today + timedelta(days=days_until_monday)

    print(f"\n=== Testing with week starting {next_monday} ===")

    # Step 1: Get current availability
    print("\n1. Fetching current availability...")
    original_data = availability_service.get_week_availability(instructor_id=instructor.id, week_start=next_monday)
    print(f"   Original slots: {len(original_data)}")

    # Step 2: Prepare test data
    test_slots = [
        {
            "start_time": "09:00:00",
            "end_time": "12:00:00",
        },
        {
            "start_time": "14:00:00",
            "end_time": "17:00:00",
        },
    ]

    # Step 3: Save new availability
    print("\n2. Saving new availability...")
    save_start = time.time()

    result = availability_service.set_day_availability(
        instructor_id=instructor.id, date=next_monday, slots=test_slots, clear_existing=True
    )

    save_duration = time.time() - save_start
    print(f"   Save took: {save_duration:.3f}s")
    print(f"   Save successful: {result is not None}")

    if result:
        saved_slots = result.get("slots", [])
        print(f"   Saved {len(saved_slots)} slots")

    # Step 4: Test immediate and delayed fetches
    print("\n3. Testing fetch timing...")
    delays = [0, 0.1, 0.5, 1.0, 2.0]

    for delay in delays:
        if delay > 0:
            time.sleep(delay)

        fetch_start = time.time()
        data = availability_service.get_week_availability(instructor_id=instructor.id, week_start=next_monday)
        fetch_duration = time.time() - fetch_start

        monday_data = data.get(next_monday.isoformat(), [])
        print(f"   After {delay}s delay: {len(monday_data)} slots (fetch took {fetch_duration:.3f}s)")
        if len(monday_data) > 0:
            print(f"     First slot: {monday_data[0]['start_time']} - {monday_data[0]['end_time']}")

    # Final verification
    assert len(monday_data) == 2, f"Expected 2 slots, got {len(monday_data)}"
    assert monday_data[0]["start_time"] == "09:00:00", "First slot time mismatch"


def test_cache_invalidation(db: Session, test_instructor_with_availability: User, cache_service: CacheService):
    """Test that cache is properly invalidated on updates."""

    instructor = test_instructor_with_availability
    availability_service = AvailabilityService(db)

    # Use a specific future date
    test_date = date.today() + timedelta(days=60)
    week_start = test_date - timedelta(days=test_date.weekday())

    # Initial save
    print("\n1. Initial save...")
    availability_service.set_day_availability(
        instructor_id=instructor.id,
        date=test_date,
        slots=[{"start_time": "10:00:00", "end_time": "11:00:00"}],
        clear_existing=True,
    )

    # First fetch (should cache)
    print("\n2. First fetch (caching)...")
    data1 = availability_service.get_week_availability(instructor_id=instructor.id, week_start=week_start)
    slots1 = data1.get(test_date.isoformat(), [])
    print(f"   Got {len(slots1)} slots")

    # Update the data
    print("\n3. Updating data...")
    availability_service.set_day_availability(
        instructor_id=instructor.id,
        date=test_date,
        slots=[{"start_time": "14:00:00", "end_time": "15:00:00"}, {"start_time": "16:00:00", "end_time": "17:00:00"}],
        clear_existing=True,
    )

    # Fetch again (should get fresh data, not cached)
    print("\n4. Fetching after update...")
    data2 = availability_service.get_week_availability(instructor_id=instructor.id, week_start=week_start)
    slots2 = data2.get(test_date.isoformat(), [])
    print(f"   Got {len(slots2)} slots")

    # Verify cache was invalidated
    assert len(slots2) == 2, f"Expected 2 slots after update, got {len(slots2)}"
    assert slots2[0]["start_time"] == "14:00:00", "Cache not properly invalidated"

    print("\n✅ Cache invalidation working correctly!")


# Pytest fixture for cache service
@pytest.fixture
def cache_service(db: Session):
    """Get cache service instance."""
    from app.core.config import settings

    return CacheService(redis_url=settings.redis_url)
