# backend/scripts/test_auth_endpoint.py
"""
Test the auth endpoint directly to debug
"""
import os
import sys
from pathlib import Path

# Setup environment
backend_dir = Path(__file__).parent.parent
os.chdir(backend_dir)
sys.path.insert(0, str(backend_dir))

# Load environment
from dotenv import dotenv_values

env_file = backend_dir / ".env"
env_values = dotenv_values(env_file)
for key, value in env_values.items():
    os.environ[key] = value
    os.environ[key.upper()] = value

print("🔍 Testing auth endpoint logic...")

# Import after environment is set
from app.core.config import settings
from app.database import SessionLocal
from app.services.auth_service import AuthService

# Check settings
print(f"\n📋 Settings check:")
print(f"   secret_key: {settings.secret_key.get_secret_value()[:10]}...")
print(f"   algorithm: {settings.algorithm}")

# Test the exact flow used in the login endpoint
db = SessionLocal()
auth_service = AuthService(db)

# Test data
username = "test@example.com"  # OAuth2 form uses 'username' field
password = "password123"

print(f"\n🔐 Testing login flow:")
print(f"   Username: {username}")
print(f"   Password: {password}")

# This is what the login endpoint does
user = auth_service.authenticate_user(username, password)
if user:
    print(f"   ✅ User authenticated: {user.email}")

    # Check if token creation works (login endpoint does this)
    from datetime import timedelta

    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)

    # The login endpoint creates token differently
    from datetime import datetime

    from jose import jwt

    to_encode = {"sub": user.email}
    expire = datetime.utcnow() + access_token_expires
    to_encode.update({"exp": expire})

    encoded_jwt = jwt.encode(to_encode, settings.secret_key.get_secret_value(), algorithm=settings.algorithm)

    print(f"   ✅ Token created: {encoded_jwt[:20]}...")

    # Try to decode it
    try:
        payload = jwt.decode(encoded_jwt, settings.secret_key.get_secret_value(), algorithms=[settings.algorithm])
        print(f"   ✅ Token decoded: {payload}")
    except Exception as e:
        print(f"   ❌ Token decode failed: {e}")
else:
    print(f"   ❌ Authentication failed!")

db.close()

print("\n📡 Testing via HTTP request to both servers...")
import requests
import urllib3

urllib3.disable_warnings()

# Test both servers
for port, protocol in [(8000, "http"), (8001, "https")]:
    url = f"{protocol}://localhost:{port}/auth/login"
    data = {"username": username, "password": password}

    try:
        response = requests.post(url, data=data, verify=False)
        print(f"\n{protocol.upper()} ({port}): Status {response.status_code}")
        if response.status_code == 200:
            print(f"   ✅ Success: {response.json()}")
        else:
            print(f"   ❌ Failed: {response.text}")
    except Exception as e:
        print(f"\n{protocol.upper()} ({port}): ❌ Error: {e}")
