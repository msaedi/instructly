# backend/scripts/debug_auth_service.py
"""
Debug what's happening in AuthService during HTTPS
"""
import os
from pathlib import Path
import sys

import requests
import urllib3

urllib3.disable_warnings()

# Set up environment like HTTPS server
backend_dir = Path(__file__).parent.parent
os.chdir(backend_dir)
sys.path.insert(0, str(backend_dir))

from dotenv import dotenv_values

env_file = backend_dir / ".env"
env_values = dotenv_values(env_file)
for key, value in env_values.items():
    os.environ[key] = value
    os.environ[key.upper()] = value

# Now let's monkey-patch the auth service to add debugging
print("🔍 Patching AuthService for debugging...")

from app.services import auth_service as auth_module

# Save original authenticate_user method
original_authenticate = auth_module.AuthService.authenticate_user


def debug_authenticate_user(self, email: str, password: str):
    """Wrapped authenticate_user with debugging"""
    print("\n🐛 DEBUG authenticate_user called:")
    print(f"   Email: {email}")
    print(f"   Password: {password}")
    print(f"   Password length: {len(password)}")

    # Check if user exists
    user = self.get_user_by_email(email)
    if user:
        print(f"   ✅ User found: ID={user.id}, Active={user.is_active}")
        print(f"   Hash starts with: {user.hashed_password[:20]}...")

        # Try password verification
        from app.auth import verify_password

        is_valid = verify_password(password, user.hashed_password)
        print(f"   Password valid: {is_valid}")
    else:
        print("   ❌ User not found")

    # Call original method
    result = original_authenticate(self, email, password)
    print(f"   Result: {'User authenticated' if result else 'Authentication failed'}")

    return result


# Apply the patch
auth_module.AuthService.authenticate_user = debug_authenticate_user

print("✅ AuthService patched for debugging")
print("\n📡 Now testing login endpoints...")

# Test both servers
for port, protocol in [(8000, "http"), (8001, "https")]:
    print(f"\n{'='*50}")
    print(f"Testing {protocol.upper()} on port {port}")
    print("=" * 50)

    url = f"{protocol}://localhost:{port}/auth/login"
    data = {"username": "test@example.com", "password": "password123"}

    response = requests.post(url, data=data, verify=False)
    print(f"\nResponse Status: {response.status_code}")
    if response.status_code == 200:
        print("✅ Success: Got token")
    else:
        print(f"❌ Failed: {response.text}")
