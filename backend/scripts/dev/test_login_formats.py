# backend/scripts/test_login_formats.py
"""
Test different login request formats
"""
import requests
import urllib3

urllib3.disable_warnings()

# Test credentials
username = "test@example.com"
password = "password123"

print("🔍 Testing different login request formats...")

# Test both HTTP and HTTPS
for port, protocol in [(8000, "http"), (8001, "https")]:
    print(f"\n{'='*50}")
    print(f"Testing {protocol.upper()} on port {port}")
    print("=" * 50)

    base_url = f"{protocol}://localhost:{port}"

    # 1. Test with form-urlencoded (OAuth2 standard)
    print("\n1️⃣ Form-urlencoded format:")
    response = requests.post(
        f"{base_url}/auth/login",
        data={"username": username, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        verify=False,
    )
    print(f"   Status: {response.status_code}")
    if response.status_code == 200:
        print(f"   ✅ Token: {response.json()['access_token'][:20]}...")
    else:
        print(f"   ❌ Error: {response.text}")

    # 2. Test with JSON (common mistake)
    print("\n2️⃣ JSON format (should fail):")
    response = requests.post(f"{base_url}/auth/login", json={"username": username, "password": password}, verify=False)
    print(f"   Status: {response.status_code}")
    print(f"   Response: {response.text[:100]}...")

    # 3. Test with wrong field names
    print("\n3️⃣ Wrong field names (email instead of username):")
    response = requests.post(
        f"{base_url}/auth/login",
        data={"email": username, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        verify=False,
    )
    print(f"   Status: {response.status_code}")
    print(f"   Response: {response.text[:100]}...")

    # 4. Test health endpoint to verify server is running
    print("\n4️⃣ Health check:")
    response = requests.get(f"{base_url}/api/v1/health", verify=False)
    print(f"   Status: {response.status_code}")
    print(f"   Response: {response.json()}")
