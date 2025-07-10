# backend/scripts/debug_settings.py
"""
Debug how settings are loaded in different contexts
"""
import os
import sys
from pathlib import Path

# Setup exactly like run_ssl_simple.py
backend_dir = Path(__file__).parent.parent
os.chdir(backend_dir)
sys.path.insert(0, str(backend_dir))

# Load environment
from dotenv import load_dotenv

env_file = backend_dir / ".env"
load_dotenv(env_file, override=True)

# Check environment
print("🔍 Environment variables after dotenv:")
print(f"   SECRET_KEY: {'SECRET_KEY' in os.environ}")
print(f"   secret_key: {'secret_key' in os.environ}")
print(f"   First 10 chars of SECRET_KEY: {os.environ.get('SECRET_KEY', 'NOT SET')[:10]}")
print(f"   First 10 chars of secret_key: {os.environ.get('secret_key', 'NOT SET')[:10]}")

# Now import settings and check what it sees
print("\n📋 Settings values:")
from app.core.config import settings

print(f"   secret_key from settings: {settings.secret_key.get_secret_value()[:10]}...")
print(f"   algorithm: {settings.algorithm}")
print(f"   database_url: {settings.database_url[:30]}...")

# Test JWT creation/verification
print("\n🔐 Testing JWT:")
from app.database import SessionLocal
from app.services.auth_service import AuthService

db = SessionLocal()
auth_service = AuthService(db)

# Create a token
token = auth_service.create_access_token(data={"sub": "test@example.com"})
print(f"   Created token: {token[:20]}...")

# Verify the token
try:
    payload = auth_service.decode_access_token(token)
    print(f"   ✅ Token decoded successfully: {payload}")
except Exception as e:
    print(f"   ❌ Token decode failed: {e}")

db.close()
