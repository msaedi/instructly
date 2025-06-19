#!/usr/bin/env python3
# backend/scripts/test_availability_cache.py
"""
Test script to verify the availability cache timing issue.
This will help us understand the exact timing of cache invalidation and data consistency.
"""

import asyncio
import time
from datetime import date, timedelta

import httpx

# Test configuration
API_URL = "http://localhost:8000"
TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJwcm9maWxpbmdAaW5zdGFpbnN0cnUuY29tIiwiZXhwIjoxNzUwMzA3Mjc0fQ.Kxs4vT2uZTEXi5iR2qmx56zSJlSh9aJQiWvGZZFvEsw"

# Use Sarah Chen instead of profiling user (which has corrupted data)
SARAH_EMAIL = "sarah.chen@example.com"
SARAH_PASSWORD = "TestPassword123!"


async def get_sarah_token():
    """Get auth token for Sarah Chen."""
    async with httpx.AsyncClient() as client:
        # The login endpoint expects form data, not JSON
        response = await client.post(
            f"{API_URL}/auth/login",  # Correct endpoint path
            data={
                "username": SARAH_EMAIL,  # Even though it's an email, the field is "username"
                "password": SARAH_PASSWORD,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if response.status_code == 200:
            data = response.json()
            return data["access_token"]
        else:
            print(f"Login failed: {response.status_code} - {response.text}")
            return None


async def test_availability_timing():
    """Test the timing of availability saves and cache behavior."""

    # Get Sarah's token
    token = await get_sarah_token()
    if not token:
        print("Failed to authenticate as Sarah Chen")
        return

    headers = {"Authorization": f"Bearer {token}"}

    # Get next Monday
    today = date.today()
    days_until_monday = (7 - today.weekday()) % 7
    if days_until_monday == 0:
        days_until_monday = 7
    next_monday = today + timedelta(days=days_until_monday)

    print(f"\n=== Testing with week starting {next_monday} ===")

    async with httpx.AsyncClient() as client:
        # Step 1: Get current availability
        print("\n1. Fetching current availability...")
        response = await client.get(
            f"{API_URL}/instructors/availability-windows/week",
            params={"start_date": next_monday.isoformat()},
            headers=headers,
        )
        original_data = response.json()
        print(f"   Original slots: {len(original_data)}")

        # Step 2: Prepare test data
        test_schedule = {
            "schedule": [
                {
                    "date": next_monday.isoformat(),
                    "start_time": "09:00:00",
                    "end_time": "12:00:00",
                },
                {
                    "date": next_monday.isoformat(),
                    "start_time": "14:00:00",
                    "end_time": "17:00:00",
                },
            ],
            "clear_existing": True,
        }

        # Step 3: Save new availability
        print("\n2. Saving new availability...")
        save_start = time.time()
        response = await client.post(
            f"{API_URL}/instructors/availability-windows/week",
            json=test_schedule,
            headers=headers,
        )
        save_duration = time.time() - save_start
        print(f"   Save took: {save_duration:.3f}s")
        print(f"   Response status: {response.status_code}")

        if response.status_code == 200:
            saved_data = response.json()
            print(f"   Response includes data: {'_metadata' in saved_data}")

        # Step 4: Immediately fetch again (simulating UI refresh)
        print("\n3. Immediately fetching after save...")
        delays = [0, 0.1, 0.5, 1.0, 2.0]

        for delay in delays:
            if delay > 0:
                await asyncio.sleep(delay)

            fetch_start = time.time()
            response = await client.get(
                f"{API_URL}/instructors/availability-windows/week",
                params={"start_date": next_monday.isoformat()},
                headers=headers,
            )
            fetch_duration = time.time() - fetch_start

            if response.status_code == 200:
                data = response.json()
                monday_data = data.get(next_monday.isoformat(), [])
                print(f"   After {delay}s delay: {len(monday_data)} slots (fetch took {fetch_duration:.3f}s)")
                if len(monday_data) > 0:
                    print(f"     First slot: {monday_data[0]['start_time']} - {monday_data[0]['end_time']}")

        # Step 5: Check cache statistics
        print("\n4. Checking cache statistics...")
        response = await client.get(f"{API_URL}/metrics/cache", headers=headers)
        if response.status_code == 200:
            stats = response.json()
            print(f"   Hit rate: {stats.get('hit_rate', 'N/A')}")
            print(f"   Total requests: {stats.get('total_requests', 0)}")


if __name__ == "__main__":
    asyncio.run(test_availability_timing())
