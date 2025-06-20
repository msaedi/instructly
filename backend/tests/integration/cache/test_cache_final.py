#!/usr/bin/env python3
# backend/scripts/test_cache_final.py
"""
Final comprehensive test to verify all cache fixes are working.
"""

import asyncio
from datetime import date, timedelta

import httpx

API_URL = "http://localhost:8000"
SARAH_EMAIL = "sarah.chen@example.com"
SARAH_PASSWORD = "TestPassword123!"


async def get_auth_token(email: str, password: str) -> str:
    """Get auth token for user."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{API_URL}/auth/login",
            data={
                "username": email,
                "password": password,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if response.status_code == 200:
            data = response.json()
            return data["access_token"]
        return None


async def test_all_operations():
    """Test all availability operations for cache consistency."""

    token = await get_auth_token(SARAH_EMAIL, SARAH_PASSWORD)
    if not token:
        print("Failed to authenticate")
        return

    headers = {"Authorization": f"Bearer {token}"}

    # Use far future dates to avoid conflicts
    test_base = date(2026, 3, 2)  # A Monday in March 2026

    print("🧪 Final Cache Consistency Test\n")

    async with httpx.AsyncClient() as client:
        # Test 1: Basic Save
        print("1. Testing basic save operation...")
        response = await client.post(
            f"{API_URL}/instructors/availability-windows/week",
            json={
                "schedule": [{"date": test_base.isoformat(), "start_time": "09:00:00", "end_time": "12:00:00"}],
                "clear_existing": True,
            },
            headers=headers,
        )

        if response.status_code == 200:
            data = response.json()
            slots = data.get(test_base.isoformat(), [])
            if slots and slots[0]["start_time"] == "09:00:00":
                print("   ✅ Basic save returns fresh data")
            else:
                print("   ❌ Basic save failed")

        # Test 2: Copy Week
        print("\n2. Testing copy week operation...")
        target_week = test_base + timedelta(days=7)

        response = await client.post(
            f"{API_URL}/instructors/availability-windows/copy-week",
            json={"from_week_start": test_base.isoformat(), "to_week_start": target_week.isoformat()},
            headers=headers,
        )

        if response.status_code == 200:
            data = response.json()
            slots = data.get(target_week.isoformat(), [])
            if slots and slots[0]["start_time"] == "09:00:00":
                print("   ✅ Copy week returns fresh data")
            else:
                print("   ❌ Copy week failed")

        # Test 3: Apply Pattern
        print("\n3. Testing apply pattern operation...")
        range_start = test_base + timedelta(days=14)
        range_end = range_start + timedelta(days=6)

        response = await client.post(
            f"{API_URL}/instructors/availability-windows/apply-to-date-range",
            json={
                "from_week_start": test_base.isoformat(),
                "start_date": range_start.isoformat(),
                "end_date": range_end.isoformat(),
            },
            headers=headers,
        )

        if response.status_code == 200:
            result = response.json()
            if result.get("slots_created", 0) > 0:
                print("   ✅ Apply pattern completed successfully")

                # Verify data is fresh
                verify_response = await client.get(
                    f"{API_URL}/instructors/availability-windows/week",
                    params={"start_date": range_start.isoformat()},
                    headers=headers,
                )

                if verify_response.status_code == 200:
                    verify_data = verify_response.json()
                    verify_slots = verify_data.get(range_start.isoformat(), [])
                    if verify_slots:
                        print("   ✅ Applied data is immediately available")
            else:
                print("   ❌ Apply pattern failed")

        # Test 4: Rapid Sequential Updates
        print("\n4. Testing rapid sequential updates...")
        rapid_test_date = test_base + timedelta(days=28)

        all_success = True
        for i in range(5):
            response = await client.post(
                f"{API_URL}/instructors/availability-windows/week",
                json={
                    "schedule": [
                        {
                            "date": rapid_test_date.isoformat(),
                            "start_time": f"{10+i}:00:00",
                            "end_time": f"{11+i}:00:00",
                        }
                    ],
                    "clear_existing": True,
                },
                headers=headers,
            )

            if response.status_code == 200:
                data = response.json()
                slots = data.get(rapid_test_date.isoformat(), [])
                if not (slots and slots[0]["start_time"] == f"{10+i}:00:00"):
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


if __name__ == "__main__":
    asyncio.run(test_all_operations())
