import requests
import urllib3

urllib3.disable_warnings()

# Test with sarah.chen account
email = "sarah.chen@example.com"
password = "TestPassword123!"

print("Testing login with sarah.chen@example.com\n")

for port, protocol in [(8000, "http"), (8001, "https")]:
    print(f"{protocol.upper()} on port {port}:")

    url = f"{protocol}://localhost:{port}/auth/login"
    data = {"username": email, "password": password}  # OAuth2 uses 'username' field

    response = requests.post(url, data=data, verify=False)
    print(f"  Status: {response.status_code}")

    if response.status_code == 200:
        token_data = response.json()
        print(f"  ✅ Success! Token: {token_data['access_token'][:30]}...")
    else:
        print(f"  ❌ Failed: {response.text}")
    print()
