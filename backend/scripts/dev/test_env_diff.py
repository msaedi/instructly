import requests
import urllib3

urllib3.disable_warnings()

# Test simple authentication
print("Testing environment differences...\n")

# Check which secret key is being used
for port, protocol in [(8000, "http"), (8001, "https")]:
    print(f"\n{protocol.upper()} on port {port}:")

    # Test with the simple auth endpoint
    url = f"{protocol}://localhost:{port}/test/simple-auth"
    data = {"email": "test@example.com", "password": "password123"}

    try:
        response = requests.post(url, json=data, verify=False)
        if response.status_code == 200:
            result = response.json()
            print(f"  User found: {result.get('user_found')}")
            print(f"  Secret key preview: {result.get('settings_loaded', {}).get('secret_key_first_10')}")
            print(f"  Token created: {result.get('token_created', False)}")
        else:
            print(f"  Error: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"  Connection error: {e}")
