# backend/scripts/test_auth_direct.py
"""
Direct test of authentication in SSL context
"""
import os
import sys
from pathlib import Path

# Set up exactly like run_ssl_simple.py
backend_dir = Path(__file__).parent.parent
os.chdir(backend_dir)
sys.path.insert(0, str(backend_dir))

# Load environment
from dotenv import dotenv_values

env_file = backend_dir / ".env"
env_values = dotenv_values(env_file)

# Set all variations
for key, value in env_values.items():
    os.environ[key] = value
    os.environ[key.upper()] = value
    os.environ[key.lower()] = value

print("🔍 Testing authentication flow directly...")

from passlib.context import CryptContext

# Import after environment is set
from app.database import SessionLocal
from app.models.user import User
from app.services.auth_service import AuthService

db = SessionLocal()
auth_service = AuthService(db)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Test user details
email = "test@example.com"
password = "password123"

print(f"\n1️⃣ Checking user exists...")
user = db.query(User).filter(User.email == email).first()
if user:
    print(f"   ✅ User found: {user.email} (ID: {user.id})")
else:
    print(f"   ❌ User not found!")
    db.close()
    exit(1)

print(f"\n2️⃣ Verifying password hash...")
is_valid = pwd_context.verify(password, user.hashed_password)
print(f"   Password valid: {is_valid}")
print(f"   Hash starts with: {user.hashed_password[:10]}...")

print(f"\n3️⃣ Testing authenticate_user method...")
auth_result = auth_service.authenticate_user(email, password)
if auth_result:
    print(f"   ✅ Authentication successful!")
else:
    print(f"   ❌ Authentication failed!")

print(f"\n4️⃣ Testing token creation...")
token = auth_service.create_access_token(data={"sub": email})
print(f"   Token created: {token[:20]}...")

print(f"\n5️⃣ Testing the login flow (form data)...")


# Simulate the login request
class FakeForm:
    def __init__(self, username, password):
        self.username = username
        self.password = password


form = FakeForm(username=email, password=password)

# Test the actual login logic
user = auth_service.authenticate_user(form.username, form.password)
if user:
    print(f"   ✅ Login would succeed!")
    access_token = auth_service.create_access_token(data={"sub": user.email})
    print(f"   Token: {access_token[:20]}...")
else:
    print(f"   ❌ Login would fail!")

db.close()
