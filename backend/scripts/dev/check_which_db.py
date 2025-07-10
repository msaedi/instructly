import os
import sys
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

# Load .env file
from dotenv import load_dotenv

load_dotenv(backend_dir / ".env")

# Check environment variables
print("Environment variables check:\n")
print(f"DATABASE_URL (uppercase): {os.environ.get('DATABASE_URL', 'NOT SET')[:50]}...")
print(f"database_url (lowercase): {os.environ.get('database_url', 'NOT SET')[:50]}...")
print(f"TEST_DATABASE_URL: {os.environ.get('TEST_DATABASE_URL', 'NOT SET')[:50]}...")
print(f"test_database_url: {os.environ.get('test_database_url', 'NOT SET')[:50]}...")

# Check what the app actually uses
from app.core.config import settings

print(f"\nSettings database_url: {settings.database_url[:50]}...")

# Check if test database has users
from app.database import SessionLocal
from app.models.user import User

db = SessionLocal()
users = db.query(User).all()
print(f"\nDatabase has {len(users)} users")
for user in users[:5]:  # Show first 5 users
    print(f"  - {user.email} (id: {user.id})")
db.close()
