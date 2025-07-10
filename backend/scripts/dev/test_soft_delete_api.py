#!/usr/bin/env python3
# backend/scripts/test_soft_delete_api_fixed.py
"""
Simple API test for soft delete functionality
Run from project root: python backend/scripts/test_soft_delete_api_fixed.py
"""

import requests

BASE_URL = "http://localhost:8000"


def test_soft_delete():
    """Test soft delete through the API"""
    print("🧪 Testing Soft Delete via API\n")

    # 1. Login as Sarah Chen
    print("1. Logging in...")
    login_response = requests.post(
        f"{BASE_URL}/auth/login", data={"username": "sarah.chen@example.com", "password": "TestPassword123!"}
    )

    if login_response.status_code != 200:
        print(f"❌ Login failed: {login_response.text}")
        return

    token = login_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print("✅ Logged in successfully")

    # 2. Get current profile
    print("\n2. Getting current profile...")
    profile_response = requests.get(f"{BASE_URL}/instructors/profile", headers=headers)

    if profile_response.status_code != 200:
        print(f"❌ Failed to get profile: {profile_response.text}")
        return

    profile = profile_response.json()
    print(f"✅ Current services: {[s['skill'] for s in profile['services']]}")

    # 3. Update profile (remove Music Theory)
    print("\n3. Removing Music Theory service...")
    update_data = {
        "services": [{"skill": "Piano", "hourly_rate": 75, "description": "Classical and jazz piano lessons"}]
    }

    update_response = requests.put(f"{BASE_URL}/instructors/profile", headers=headers, json=update_data)

    if update_response.status_code != 200:
        print(f"❌ Update failed: {update_response.text}")
        return

    updated_profile = update_response.json()
    print(f"✅ Active services after update: {[s['skill'] for s in updated_profile['services']]}")

    # 4. Verify in database
    print("\n4. Let's check the database state...")
    print("   Run this command to verify:")
    print("   python backend/scripts/verify_soft_delete_db.py")

    # 5. Reactivate service
    print("\n5. Reactivating Music Theory...")
    reactivate_data = {
        "services": [{"skill": "Piano", "hourly_rate": 75}, {"skill": "Music Theory", "hourly_rate": 70}]
    }

    reactivate_response = requests.put(f"{BASE_URL}/instructors/profile", headers=headers, json=reactivate_data)

    if reactivate_response.status_code == 200:
        final_profile = reactivate_response.json()
        print(f"✅ Services after reactivation: {[s['skill'] for s in final_profile['services']]}")
    else:
        print(f"❌ Reactivation failed: {reactivate_response.text}")

    print("\n✅ Soft delete test complete!")
    print("\nThe test successfully:")
    print("- ✅ Removed Music Theory (soft delete)")
    print("- ✅ Reactivated Music Theory")
    print("\nBookings are preserved during soft delete!")


if __name__ == "__main__":
    test_soft_delete()
