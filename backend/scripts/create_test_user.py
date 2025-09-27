# backend/scripts/create_test_user.py
"""
Create a fresh test user to verify authentication
"""
from pathlib import Path
import sys

# Add backend to path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from passlib.context import CryptContext

from app.database import SessionLocal
from app.models.user import User

# Password context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def create_test_user():
    db = SessionLocal()

    email = "test@example.com"
    password = "password123"

    try:
        # Check if user exists
        existing = db.query(User).filter(User.email == email).first()
        if existing:
            print(f"ℹ️  User {email} already exists")
            # Update password
            existing.hashed_password = pwd_context.hash(password)
            db.commit()
            print("✅ Updated password for existing user")
        else:
            # Create new user
            hashed_password = pwd_context.hash(password)
            user = User(
                email=email, hashed_password=hashed_password, full_name="Test User", role="student", is_active=True
            )
            db.add(user)
            db.commit()
            print(f"✅ Created user: {email}")

        print("\n📧 Login credentials:")
        print(f"   Email: {email}")
        print(f"   Password: {password}")

    except Exception as e:
        print(f"❌ Error: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    create_test_user()
