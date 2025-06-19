# backend/test_auth.py
import requests

response = requests.post(
    "http://localhost:8000/auth/login",
    data={"username": "profiling@instainstru.com", "password": "TestPassword123!"},
)

print(f"Status: {response.status_code}")
print(f"Response: {response.json()}")

if response.status_code == 200:
    token = response.json()["access_token"]
    print(f"\nToken: {token}")

    # Test metrics endpoint
    metrics_response = requests.get(
        "http://localhost:8000/metrics/performance",
        headers={"Authorization": f"Bearer {token}"},
    )
    print(f"\nMetrics Status: {metrics_response.status_code}")
    print(f"Metrics: {metrics_response.json()}")
