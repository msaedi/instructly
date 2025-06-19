"""
Test the endpoint with a specific week that has bookings
Save as: backend/scripts/test_specific_week.py
"""
import json
from datetime import date

import requests

BASE_URL = "http://localhost:8000"
INSTRUCTOR_EMAIL = "sarah.chen@example.com"
INSTRUCTOR_PASSWORD = "TestPassword123!"


def test_week_with_bookings():
    print("=== Testing Week with Known Bookings ===\n")

    # Login
    login_response = requests.post(
        f"{BASE_URL}/auth/login",
        data={"username": INSTRUCTOR_EMAIL, "password": INSTRUCTOR_PASSWORD},
    )

    token = login_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Test week of June 16, 2025 (which has bookings based on your data)
    test_date = date(2025, 6, 16)  # This is a Monday

    print(f"Testing week starting: {test_date}")

    response = requests.get(
        f"{BASE_URL}/instructors/availability-windows/week/booked-slots",
        params={"start_date": test_date.isoformat()},
        headers=headers,
    )

    data = response.json()

    print(f"\nFound {len(data.get('booked_slots', []))} booked slots")

    if data.get("booked_slots"):
        print("\nSlot details:")
        for i, slot in enumerate(data["booked_slots"], 1):
            print(f"\n--- Slot {i} ---")
            print(json.dumps(slot, indent=2))


if __name__ == "__main__":
    test_week_with_bookings()
