import requests
import urllib3

urllib3.disable_warnings()

print("Testing a simple endpoint without rate limiting...\n")

# Test the root endpoint which has no rate limiting
for port, protocol in [(8000, "http"), (8001, "https")]:
    print(f"{protocol.upper()} on port {port}:")

    # Test root endpoint
    url = f"{protocol}://localhost:{port}/"
    response = requests.get(url, verify=False)
    print(f"  Root endpoint: {response.status_code} - {response.json()}")

    # Test if form data is being received correctly
    test_url = f"{protocol}://localhost:{port}/test/simple-auth"
    data = {"email": "sarah.chen@example.com", "password": "TestPassword123!"}

    response = requests.post(test_url, json=data, verify=False)
    if response.status_code == 200:
        result = response.json()
        print(f"  Simple auth test: user_found={result.get('user_found')}")
    else:
        print(f"  Simple auth test failed: {response.status_code}")
    print()
