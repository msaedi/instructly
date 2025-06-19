"""
Test the enhanced booked slots endpoint
Save as: backend/scripts/test_booked_slots_endpoint.py
Run from backend directory: python scripts/test_booked_slots_endpoint.py
"""
import json
from datetime import date, timedelta

import requests

# Configuration
BASE_URL = "http://localhost:8000"  # Update if different
INSTRUCTOR_EMAIL = "sarah.chen@example.com"  # An instructor email
INSTRUCTOR_PASSWORD = "TestPassword123!"


def get_monday_of_current_week():
    today = date.today()
    days_since_monday = today.weekday()
    monday = today - timedelta(days=days_since_monday)
    return monday


def test_endpoint():
    print("=== Testing Enhanced Booked Slots Endpoint ===\n")

    # 1. Login as instructor
    print("1. Logging in as instructor...")
    login_response = requests.post(
        f"{BASE_URL}/auth/login",
        data={"username": INSTRUCTOR_EMAIL, "password": INSTRUCTOR_PASSWORD},
    )

    if login_response.status_code != 200:
        print(f"❌ Login failed: {login_response.status_code}")
        print(login_response.text)
        return

    token = login_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print("✅ Login successful\n")

    # 2. Call the booked slots endpoint
    monday = get_monday_of_current_week()
    print(f"2. Testing endpoint for week starting: {monday}")

    response = requests.get(
        f"{BASE_URL}/instructors/availability-windows/week/booked-slots",
        params={"start_date": monday.isoformat()},
        headers=headers,
    )

    if response.status_code != 200:
        print(f"❌ Endpoint failed: {response.status_code}")
        print(response.text)
        return

    data = response.json()
    print(f"✅ Endpoint successful\n")

    # 3. Check the response structure
    print("3. Response structure:")
    print(f"   - Total booked slots: {len(data.get('booked_slots', []))}")

    if data.get("booked_slots"):
        print("\n4. Sample slot data:")
        slot = data["booked_slots"][0]
        print(json.dumps(slot, indent=2))

        # Check for new fields
        print("\n5. Checking for new fields:")
        required_fields = [
            "booking_id",
            "date",
            "start_time",
            "end_time",
            "student_first_name",
            "student_last_initial",
            "service_name",
            "service_area_short",
            "duration_minutes",
            "location_type",
        ]

        for field in required_fields:
            if field in slot:
                print(f"   ✅ {field}: {slot[field]}")
            else:
                print(f"   ❌ {field}: MISSING")
    else:
        print("\n   ℹ️  No booked slots found for this week")
        print("   Try testing with a different instructor or week")


if __name__ == "__main__":
    test_endpoint()
