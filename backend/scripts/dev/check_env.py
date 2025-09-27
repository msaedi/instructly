# backend/scripts/check_env.py
"""
Check environment configuration
"""
from pathlib import Path
import sys

# Add backend to path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

import os

from app.core.config import settings


def check_environment():
    """Check current environment settings"""
    print("🔍 Environment Configuration:")
    print(f"   Environment: {settings.environment}")
    print(f"   Secret Key (first 10 chars): {settings.secret_key.get_secret_value()[:10]}...")
    print(f"   Database URL: {settings.database_url[:30]}...")
    print(f"   Frontend URL: {settings.frontend_url}")
    print(f"   Algorithm: {settings.algorithm}")

    print("\n📁 Working Directory:")
    print(f"   Current dir: {os.getcwd()}")
    print(f"   Backend dir: {backend_dir}")

    print("\n🔑 Environment Variables:")
    print(f"   SECRET_KEY set: {'SECRET_KEY' in os.environ}")
    print(f"   DATABASE_URL set: {'DATABASE_URL' in os.environ}")

    # Check .env file
    env_file = backend_dir / ".env"
    print("\n📄 .env file:")
    print(f"   Exists: {env_file.exists()}")
    if env_file.exists():
        print(f"   Path: {env_file}")


if __name__ == "__main__":
    check_environment()
