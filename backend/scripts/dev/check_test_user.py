import sys
from pathlib import Path

backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from dotenv import load_dotenv

load_dotenv(backend_dir / ".env")

from app.database import SessionLocal
from app.models.user import User

db = SessionLocal()

# Check for both test users
test_emails = ["test@example.com", "sarah.chen@example.com"]

print("Checking for test users:\n")
for email in test_emails:
    user = db.query(User).filter(User.email == email).first()
    if user:
        print(f"✅ {email} exists (ID: {user.id})")
    else:
        print(f"❌ {email} NOT FOUND")

# Show all users with 'test' in email
print("\nAll users with 'test' in email:")
test_users = db.query(User).filter(User.email.contains("test")).all()
for user in test_users:
    print(f"  - {user.email} (ID: {user.id})")

db.close()
