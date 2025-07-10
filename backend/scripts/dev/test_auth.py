# backend/scripts/test_auth.py
"""
Test authentication directly against the backend
"""
import requests


def test_login(base_url: str, email: str, password: str):
    """Test login endpoint"""
    url = f"{base_url}/auth/login"
    data = {"username": email, "password": password}  # FastAPI OAuth2 expects 'username' field

    print(f"🔍 Testing login to: {url}")
    print(f"📧 Email: {email}")

    try:
        response = requests.post(url, data=data)
        print(f"📡 Status: {response.status_code}")

        if response.status_code == 200:
            print("✅ Login successful!")
            print(f"🔑 Token: {response.json()['access_token'][:20]}...")
        else:
            print("❌ Login failed!")
            print(f"📋 Response: {response.text}")

    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    # Test both HTTP and HTTPS
    print("=== Testing HTTP Backend ===")
    test_login("http://localhost:8000", "test@example.com", "password123")

    print("\n=== Testing HTTPS Backend ===")
    # Note: Use verify=False for self-signed certificates
    import urllib3

    urllib3.disable_warnings()

    # For HTTPS with self-signed cert
    url = "https://localhost:8001/auth/login"
    data = {"username": "test@example.com", "password": "password123"}

    try:
        response = requests.post(url, data=data, verify=False)
        print(f"📡 HTTPS Status: {response.status_code}")
        if response.status_code == 200:
            print("✅ HTTPS Login successful!")
    except Exception as e:
        print(f"❌ HTTPS Error: {e}")
