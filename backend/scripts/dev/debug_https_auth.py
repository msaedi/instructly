import os
from pathlib import Path
import sys

# Setup paths exactly like run_ssl.py
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))
os.chdir(backend_dir)

from dotenv import load_dotenv

load_dotenv()

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

# Now test authentication directly
from app.database import SessionLocal
from app.models.user import User
from app.services.auth_service import AuthService

print("Direct authentication test:\n")

db = SessionLocal()
auth_service = AuthService(db)
ph = PasswordHasher()

# Test sarah.chen
email = "sarah.chen@example.com"
password = "TestPassword123!"

# Step 1: Get user
user = db.query(User).filter(User.email == email).first()
print(f"1. User found: {user is not None}")
if user:
    print(f"   Email: {user.email}")
    print(f"   ID: {user.id}")
    print(f"   Hash: {user.hashed_password[:20]}...")

# Step 2: Verify password directly
if user:
    try:
        ph.verify(user.hashed_password, password)
        is_valid = True
    except VerifyMismatchError:
        is_valid = False
    print(f"\n2. Direct password verification: {is_valid}")

# Step 3: Test via auth service
result = auth_service.authenticate_user(email, password)
print(f"\n3. Auth service result: {result is not None}")

db.close()

# Now let's check if the HTTPS server is loading something different
print("\n4. Checking Python paths:")
print(f"   Working dir: {os.getcwd()}")
print(f"   Python path: {sys.path[:3]}")
