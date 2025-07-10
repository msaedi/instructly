# backend/scripts/test_https_auth.py
"""
Test HTTPS authentication with more debugging
"""
import requests
import urllib3

urllib3.disable_warnings()


def test_https_login():
    """Test HTTPS login with debugging"""

    # Test endpoints
    print("🔍 Testing HTTPS endpoints...")

    # 1. Check health endpoint
    try:
        health = requests.get("https://localhost:8001/health", verify=False)
        print(f"✅ Health check: {health.json()}")
    except Exception as e:
        print(f"❌ Health check failed: {e}")
        return

    # 2. Test login with form data
    print("\n🔐 Testing login...")
    login_url = "https://localhost:8001/auth/login"

    # Try different content types
    print("\n1️⃣ Testing with form-urlencoded:")
    data = "username=test@example.com&password=password123"
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    response = requests.post(login_url, data=data, headers=headers, verify=False)
    print(f"   Status: {response.status_code}")
    print(f"   Response: {response.text[:200]}...")

    # 3. Check if it's a secret key issue
    print("\n🔑 Checking environment...")
    try:
        env_check = requests.get("https://localhost:8001/", verify=False)
        print(f"   Root endpoint: {env_check.json()}")
    except Exception as e:
        print(f"   Error: {e}")


if __name__ == "__main__":
    test_https_login()
