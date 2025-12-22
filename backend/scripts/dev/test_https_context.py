# backend/scripts/test_https_context.py
"""
Test authentication in the exact same context as HTTPS server
"""
import os
from pathlib import Path
import sys

# Mimic EXACTLY what run_ssl_simple.py does
backend_dir = Path(__file__).parent.parent
os.chdir(backend_dir)
sys.path.insert(0, str(backend_dir))

from dotenv import dotenv_values

env_file = backend_dir / ".env"
if env_file.exists():
    env_values = dotenv_values(env_file)
    for key, value in env_values.items():
        os.environ[key] = value
        os.environ[key.upper()] = value
        os.environ[key.lower()] = value

print("🔍 Testing in HTTPS context...")

from app.core.config import settings
from app.database import SessionLocal

# Now import the app AFTER setting environment
from app.main import app
from app.services.auth_service import AuthService

print("\n📋 Settings check:")
print(f"   secret_key: {settings.secret_key.get_secret_value()[:10]}...")
print(f"   environment: {settings.environment}")
print(f"   rate_limit_enabled: {settings.rate_limit_enabled}")

# Test authentication directly
db = SessionLocal()
auth_service = AuthService(db)

email = "test@example.com"
password = "password123"

print("\n🔐 Testing authentication:")
user = auth_service.authenticate_user(email, password)
if user:
    print("   ✅ Authentication successful!")
else:
    print("   ❌ Authentication failed!")

    # Let's debug why
    user_obj = db.query(auth_service.get_user_model()).filter_by(email=email).first()
    if user_obj:
        print(f"   User exists: {user_obj.email}")
        from argon2 import PasswordHasher
        from argon2.exceptions import VerifyMismatchError

        ph = PasswordHasher()
        try:
            ph.verify(user_obj.hashed_password, password)
            is_valid = True
        except VerifyMismatchError:
            is_valid = False
        print(f"   Password verification: {is_valid}")
    else:
        print("   User not found in database")

db.close()

# Test via TestClient
print("\n📡 Testing via TestClient...")
from fastapi.testclient import TestClient

client = TestClient(app)

# Test login
response = client.post("/auth/login", data={"username": email, "password": password})
print(f"   Status: {response.status_code}")
if response.status_code == 200:
    print("   ✅ Success!")
else:
    print(f"   ❌ Failed: {response.json()}")
