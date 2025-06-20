#!/usr/bin/env python3
# backend/scripts/test_cache_fix_improved.py
"""
Improved test script with better error handling and diagnostics.
"""

import asyncio
import json
import time
from datetime import date, timedelta

import httpx

# Test configuration
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
        else:
            print(f"Login failed: {response.status_code} - {response.text}")
            return None


async def test_basic_save_operation():
    """Test a basic save operation with detailed diagnostics."""

    token = await get_auth_token(SARAH_EMAIL, SARAH_PASSWORD)
    if not token:
        print("Failed to authenticate")
        return

    headers = {"Authorization": f"Bearer {token}"}

    # Get next Monday
    today = date.today()
    days_until_monday = (7 - today.weekday()) % 7
    if days_until_monday == 0:
        days_until_monday = 7
    next_monday = today + timedelta(days=days_until_monday)

    print(f"\n=== Testing Basic Save Operation for {next_monday} ===")

    async with httpx.AsyncClient() as client:
        # First, check current state
        print("\n1. Checking current availability...")
        response = await client.get(
            f"{API_URL}/instructors/availability-windows/week",
            params={"start_date": next_monday.isoformat()},
            headers=headers,
        )

        if response.status_code == 200:
            current_data = response.json()
            current_slots = current_data.get(next_monday.isoformat(), [])
            print(f"   Current slots for Monday: {len(current_slots)}")
            if current_slots:
                print(f"   First slot: {current_slots[0]['start_time']} - {current_slots[0]['end_time']}")

        # Now save new availability
        print("\n2. Saving new availability...")
        test_schedule = {
            "schedule": [
                {
                    "date": next_monday.isoformat(),
                    "start_time": "14:00:00",
                    "end_time": "17:00:00",
                }
            ],
            "clear_existing": True,
        }

        print(f"   Request body: {json.dumps(test_schedule, indent=2)}")

        save_start = time.time()
        response = await client.post(
            f"{API_URL}/instructors/availability-windows/week", json=test_schedule, headers=headers, timeout=10.0
        )
        save_duration = time.time() - save_start

        print(f"   Save took: {save_duration:.3f}s")
        print(f"   Response status: {response.status_code}")

        if response.status_code == 200:
            saved_data = response.json()
            monday_slots = saved_data.get(next_monday.isoformat(), [])

            if monday_slots:
                print(f"   ✅ SUCCESS: Got {len(monday_slots)} slots")
                print(f"   Slot: {monday_slots[0]['start_time']} - {monday_slots[0]['end_time']}")
            else:
                print("   ❌ FAIL: No slots in response")

            # Check for metadata
            if "_metadata" in saved_data:
                print(f"   Metadata: {saved_data['_metadata']}")
        else:
            print(f"   ❌ ERROR: {response.status_code}")
            try:
                error_detail = response.json()
                print(f"   Error details: {json.dumps(error_detail, indent=2)}")
            except:
                print(f"   Response text: {response.text}")

        # Verify independently
        print("\n3. Independent verification...")
        await asyncio.sleep(0.5)  # Small delay

        response = await client.get(
            f"{API_URL}/instructors/availability-windows/week",
            params={"start_date": next_monday.isoformat()},
            headers=headers,
        )

        if response.status_code == 200:
            verify_data = response.json()
            verify_slots = verify_data.get(next_monday.isoformat(), [])
            print(f"   Verified slots: {len(verify_slots)}")
            if verify_slots:
                print(f"   Verified slot: {verify_slots[0]['start_time']} - {verify_slots[0]['end_time']}")

                # Check if it matches what we saved
                if verify_slots[0]["start_time"] == "14:00:00":
                    print("   ✅ Cache consistency verified!")
                else:
                    print("   ❌ Cache inconsistency detected!")


async def test_rapid_updates():
    """Test rapid sequential updates."""

    token = await get_auth_token(SARAH_EMAIL, SARAH_PASSWORD)
    if not token:
        return

    headers = {"Authorization": f"Bearer {token}"}

    # Get next Monday
    today = date.today()
    days_until_monday = (7 - today.weekday()) % 7
    if days_until_monday == 0:
        days_until_monday = 7
    next_monday = today + timedelta(days=days_until_monday)

    print(f"\n=== Testing Rapid Sequential Updates ===")

    async with httpx.AsyncClient() as client:
        times = ["09:00:00", "10:00:00", "11:00:00", "12:00:00", "13:00:00"]

        for i, start_time in enumerate(times):
            print(f"\nUpdate {i+1}/5: Setting time to {start_time}")

            test_schedule = {
                "schedule": [
                    {
                        "date": next_monday.isoformat(),
                        "start_time": start_time,
                        "end_time": "17:00:00",
                    }
                ],
                "clear_existing": True,
            }

            # Save
            response = await client.post(
                f"{API_URL}/instructors/availability-windows/week", json=test_schedule, headers=headers, timeout=10.0
            )

            if response.status_code == 200:
                data = response.json()
                slots = data.get(next_monday.isoformat(), [])
                if slots and slots[0]["start_time"] == start_time:
                    print(f"   ✅ Immediately got fresh data: {start_time}")
                else:
                    print(f"   ❌ Got stale data!")
            else:
                print(f"   ❌ Failed with status {response.status_code}")

            # No delay between updates

        # Final check
        print("\nFinal state check...")
        response = await client.get(
            f"{API_URL}/instructors/availability-windows/week",
            params={"start_date": next_monday.isoformat()},
            headers=headers,
        )

        if response.status_code == 200:
            final_data = response.json()
            final_slots = final_data.get(next_monday.isoformat(), [])
            if final_slots:
                print(f"Final slot time: {final_slots[0]['start_time']} (should be 13:00:00)")


if __name__ == "__main__":
    print("🧪 Improved Cache Test\n")

    # Run tests
    asyncio.run(test_basic_save_operation())
    asyncio.run(test_rapid_updates())

    print("\n✅ Test complete!")
