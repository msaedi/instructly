import json

import requests
import urllib3

urllib3.disable_warnings()

print("Testing database sessions on both servers...\n")

# Create a test that checks the actual database state
test_data = {"email": "sarah.chen@example.com", "password": "TestPassword123!"}

for port, protocol in [(8000, "http"), (8001, "https")]:
    print(f"\n{protocol.upper()} on port {port}:")

    # Use the simple-auth endpoint to check database
    url = f"{protocol}://localhost:{port}/test/simple-auth"

    response = requests.post(url, json=test_data, verify=False)
    if response.status_code == 200:
        result = response.json()
        print(f"  User found: {result.get('user_found')}")
        print(f"  Settings loaded: {json.dumps(result.get('settings_loaded', {}), indent=4)}")
        if result.get("token_created"):
            print("  Token created successfully")
        else:
            print(f"  Token error: {result.get('token_error', 'Unknown')}")
    else:
        print(f"  Request failed: {response.status_code}")
        print(f"  Error: {response.text[:200]}")
