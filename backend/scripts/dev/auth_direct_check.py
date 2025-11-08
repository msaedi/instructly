# backend/scripts/test_auth_direct.py
"""
Direct test of authentication in SSL context
"""
import os
from pathlib import Path
import sys

# Set up exactly like run_ssl_simple.py
backend_dir = Path(__file__).resolve().parents[2]
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

from passlib.context import CryptContext

# Import after environment is set
from app.database import SessionLocal
from app.models.user import User
from app.services.auth_service import AuthService


def main() -> int:
    print("🔍 Testing authentication flow directly...")

    db = SessionLocal()
    auth_service = AuthService(db)
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

    # Test user details
    email = "test@example.com"
    password = "password123"

    print("\n1️⃣ Checking user exists...")
    user = db.query(User).filter(User.email == email).first()
    if user:
        print(f"   ✅ User found: {user.email} (ID: {user.id})")
    else:
        print("   ❌ User not found!")
        db.close()
        return 1

    print("\n2️⃣ Verifying password hash...")
    is_valid = pwd_context.verify(password, user.hashed_password)
    print(f"   Password valid: {is_valid}")
    print(f"   Hash starts with: {user.hashed_password[:10]}...")

    print("\n3️⃣ Testing authenticate_user method...")
    auth_result = auth_service.authenticate_user(email, password)
    if auth_result:
        print("   ✅ Authentication successful!")
    else:
        print("   ❌ Authentication failed!")

    print("\n4️⃣ Testing token creation...")
    token = auth_service.create_access_token(data={"sub": email})
    print(f"   Token created: {token[:20]}...")

    print("\n5️⃣ Testing the login flow (form data)...")

    # Simulate the login request
    class FakeForm:
        def __init__(self, username: str, password: str):
            self.username = username
            self.password = password

    form = FakeForm(username=email, password=password)

    # Test the actual login logic
    user = auth_service.authenticate_user(form.username, form.password)
    if user:
        print("   ✅ Login would succeed!")
        access_token = auth_service.create_access_token(data={"sub": user.email})
        print(f"   Token: {access_token[:20]}...")
    else:
        print("   ❌ Login would fail!")

    db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
