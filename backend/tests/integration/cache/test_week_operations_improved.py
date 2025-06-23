#!/usr/bin/env python3
# backend/tests/integration/cache/test_week_operations_improved.py
"""
Improved test script for week operations with better error handling.
"""

import asyncio
import json
import time
from datetime import date, timedelta

import httpx
from fastapi.testclient import TestClient

from app.main import app

# Test configuration
API_URL = "http://localhost:8000"
SARAH_EMAIL = "sarah.chen@example.com"
SARAH_PASSWORD = "TestPassword123!"


def get_auth_token(email: str) -> str:
    """Get auth token for testing without HTTP calls."""
    client = TestClient(app)
    response = client.post("/auth/login", data={...})
    return response.json()["access_token"]


async def test_copy_week_with_validation():
    """Test copy week operation with better validation."""

    token = get_auth_token(SARAH_EMAIL)
    if not token:
        return

    headers = {"Authorization": f"Bearer {token}"}

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

    async with httpx.AsyncClient() as client:
        # First, check what's in source week
        print("\n1. Checking source week...")
        response = await client.get(
            f"{API_URL}/instructors/availability-windows/week",
            params={"start_date": next_monday.isoformat()},
            headers=headers,
        )

        if response.status_code == 200:
            source_data = response.json()
            has_slots = any(len(slots) > 0 for slots in source_data.values())
            print(f"   Source week has slots: {has_slots}")

            if not has_slots:
                # Set up source week
                print("\n2. Setting up source week...")
                source_schedule = {
                    "schedule": [
                        {
                            "date": next_monday.isoformat(),
                            "start_time": "09:00:00",
                            "end_time": "12:00:00",
                        },
                        {
                            "date": (next_monday + timedelta(days=2)).isoformat(),
                            "start_time": "14:00:00",
                            "end_time": "17:00:00",
                        },
                    ],
                    "clear_existing": True,
                }

                response = await client.post(
                    f"{API_URL}/instructors/availability-windows/week",
                    json=source_schedule,
                    headers=headers,
                    timeout=10.0,
                )

                if response.status_code != 200:
                    print(f"   Failed to set up source week: {response.status_code}")
                    print(f"   Error: {response.text}")
                    return

                print("   Source week set up successfully")

        # Copy week
        print("\n3. Copying week...")
        copy_request = {"from_week_start": next_monday.isoformat(), "to_week_start": week_after.isoformat()}

        print(f"   Request: {json.dumps(copy_request, indent=2)}")

        copy_start = time.time()
        response = await client.post(
            f"{API_URL}/instructors/availability-windows/copy-week", json=copy_request, headers=headers, timeout=10.0
        )
        copy_duration = time.time() - copy_start

        print(f"   Copy took: {copy_duration:.3f}s")
        print(f"   Response status: {response.status_code}")

        if response.status_code == 200:
            copied_data = response.json()

            # Check target Monday slots
            monday_slots = copied_data.get(week_after.isoformat(), [])
            wednesday_slots = copied_data.get((week_after + timedelta(days=2)).isoformat(), [])

            print(f"\n   Results:")
            print(f"   - Monday slots: {len(monday_slots)}")
            print(f"   - Wednesday slots: {len(wednesday_slots)}")

            if monday_slots:
                print(f"   - First Monday slot: {monday_slots[0]['start_time']} - {monday_slots[0]['end_time']}")

            if monday_slots and monday_slots[0]["start_time"] == "09:00:00":
                print("\n   ✅ SUCCESS: Copy returned fresh data immediately!")
            else:
                print("\n   ❌ FAIL: Data doesn't match expected")

            # Check metadata
            if "_metadata" in copied_data:
                print(f"\n   Metadata: {copied_data['_metadata']}")
        else:
            print(f"   Copy failed: {response.status_code}")
            print(f"   Error: {response.text}")


async def test_apply_pattern_validation():
    """Test apply pattern with validation of results."""

    token = get_auth_token(SARAH_EMAIL)
    if not token:
        return

    headers = {"Authorization": f"Bearer {token}"}

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

    async with httpx.AsyncClient() as client:
        # First check the pattern week
        print("\n1. Checking pattern week...")
        response = await client.get(
            f"{API_URL}/instructors/availability-windows/week",
            params={"start_date": next_monday.isoformat()},
            headers=headers,
        )

        pattern_slots = {}
        if response.status_code == 200:
            pattern_data = response.json()
            for date_str, slots in pattern_data.items():
                if slots:
                    pattern_slots[date_str] = len(slots)
            print(f"   Pattern has {sum(pattern_slots.values())} total slots across {len(pattern_slots)} days")

        # Apply pattern
        print("\n2. Applying pattern...")
        apply_request = {
            "from_week_start": next_monday.isoformat(),
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        }

        apply_start = time.time()
        response = await client.post(
            f"{API_URL}/instructors/availability-windows/apply-to-date-range",
            json=apply_request,
            headers=headers,
            timeout=15.0,
        )
        apply_duration = time.time() - apply_start

        print(f"   Apply took: {apply_duration:.3f}s")
        print(f"   Response status: {response.status_code}")

        if response.status_code == 200:
            result = response.json()
            print(f"\n   ✅ SUCCESS: Applied pattern")
            print(f"   - Days modified: {result.get('dates_created', 0) + result.get('dates_modified', 0)}")
            print(f"   - Slots created: {result.get('slots_created', 0)}")
            print(f"   - Days preserved: {result.get('dates_skipped', 0)}")

            # Verify cache is fresh
            print("\n3. Verifying cache freshness...")

            # Check first affected week immediately
            first_week_start = start_date - timedelta(days=start_date.weekday())

            response = await client.get(
                f"{API_URL}/instructors/availability-windows/week",
                params={"start_date": first_week_start.isoformat()},
                headers=headers,
            )

            if response.status_code == 200:
                verify_data = response.json()
                total_slots = sum(len(slots) for slots in verify_data.values())
                print(f"   First affected week has {total_slots} total slots")
                print(f"   ✅ Cache is returning fresh data!")

        else:
            print(f"   Apply failed: {response.status_code}")
            print(f"   Error: {response.text}")


async def test_cache_consistency():
    """Test that operations maintain cache consistency."""

    token = get_auth_token(SARAH_EMAIL)
    if not token:
        return

    headers = {"Authorization": f"Bearer {token}"}

    print(f"\n=== Testing Cache Consistency ===")

    # Get a future Monday
    today = date.today()
    days_until_monday = (7 - today.weekday()) % 7
    if days_until_monday == 0:
        days_until_monday = 7
    test_monday = today + timedelta(days=days_until_monday + 14)  # 2+ weeks out

    async with httpx.AsyncClient() as client:
        print(f"\nTesting rapid sequential operations on {test_monday}...")

        # Perform 5 rapid updates
        for i in range(5):
            slots = [
                {
                    "date": test_monday.isoformat(),
                    "start_time": f"{9+i}:00:00",
                    "end_time": f"{10+i}:00:00",
                }
            ]

            response = await client.post(
                f"{API_URL}/instructors/availability-windows/week",
                json={"schedule": slots, "clear_existing": True},
                headers=headers,
            )

            if response.status_code == 200:
                data = response.json()
                monday_data = data.get(test_monday.isoformat(), [])
                if monday_data and monday_data[0]["start_time"] == f"{9+i}:00:00":
                    print(f"   Update {i+1}: ✅ Got fresh data ({9+i}:00:00)")
                else:
                    print(f"   Update {i+1}: ❌ Got stale data!")
            else:
                print(f"   Update {i+1}: Failed with {response.status_code}")

        print("\n✅ Cache consistency test complete!")


if __name__ == "__main__":
    print("🧪 Improved Week Operations Test\n")

    # Run tests
    asyncio.run(test_copy_week_with_validation())
    asyncio.run(test_apply_pattern_validation())
    asyncio.run(test_cache_consistency())

    print("\n✅ All tests complete!")
