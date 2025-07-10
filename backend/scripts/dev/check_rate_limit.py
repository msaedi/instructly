# backend/scripts/check_rate_limit.py
"""
Check if rate limiting is affecting HTTPS
"""
import requests
import urllib3

urllib3.disable_warnings()

print("🔍 Checking rate limiting...")

# Check Redis connection
try:
    import redis

    r = redis.Redis(host="localhost", port=6379)
    r.ping()
    print("✅ Redis is running")

    # Clear any rate limit keys
    keys = r.keys("rate_limit:*")
    if keys:
        print(f"Found {len(keys)} rate limit keys")
        for key in keys:
            print(f"  - {key}")
        r.delete(*keys)
        print("✅ Cleared rate limit keys")
except Exception as e:
    print(f"❌ Redis error: {e}")

# Test login multiple times
print("\n🔐 Testing multiple login attempts...")
for i in range(5):
    for port, protocol in [(8000, "http"), (8001, "https")]:
        response = requests.post(
            f"{protocol}://localhost:{port}/auth/login",
            data={"username": "test@example.com", "password": "password123"},
            verify=False,
        )
        print(f"Attempt {i+1} - {protocol.upper()}: {response.status_code}")
        if response.status_code == 429:
            print(f"  Rate limited: {response.json()}")
