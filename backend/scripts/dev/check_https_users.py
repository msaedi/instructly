# backend/scripts/check_https_users.py
"""
Check if users exist when running from HTTPS context
"""
import os
from pathlib import Path
import sys

# Set up environment exactly like run_ssl_simple.py
backend_dir = Path(__file__).parent.parent
os.chdir(backend_dir)
sys.path.insert(0, str(backend_dir))

# Load environment
from dotenv import load_dotenv

env_file = backend_dir / ".env"
if env_file.exists():
    print(f"📄 Loading environment from: {env_file}")
    load_dotenv(env_file)

from app.database import SessionLocal
from app.models.user import User
from app.services.auth_service import AuthService


def check_users():
    """Check users in database"""
    db = SessionLocal()
    auth_service = AuthService(db)

    print("\n🔍 Checking database connection...")
    print(f"   Database URL: {db.bind.url}")

    print("\n👥 Users in database:")
    users = db.query(User).all()
    for user in users:
        print(f"   - {user.email} (ID: {user.id}, Active: {user.is_active})")

    # Check test user specifically
    test_email = "test@example.com"
    test_user = db.query(User).filter(User.email == test_email).first()

    if test_user:
        print(f"\n✅ Test user found: {test_email}")
        # Try to authenticate
        print("🔐 Testing authentication...")
        result = auth_service.authenticate_user(test_email, "password123")
        if result:
            print("   ✅ Authentication successful!")
        else:
            print("   ❌ Authentication failed!")
            # Try to verify password directly
            from passlib.context import CryptContext

            pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
            is_valid = pwd_context.verify("password123", test_user.hashed_password)
            print(f"   Password verify result: {is_valid}")
    else:
        print(f"\n❌ Test user NOT found: {test_email}")

    db.close()


if __name__ == "__main__":
    check_users()
