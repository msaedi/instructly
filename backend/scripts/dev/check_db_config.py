import os
import sys
from pathlib import Path

backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))
os.chdir(backend_dir)

from dotenv import load_dotenv

load_dotenv()

# Check the database module
from app import database
from app.core.config import settings

print("Checking database configuration:\n")
print(f"1. Settings database_url: {settings.database_url[:50]}...")
print(f"2. Engine URL: {database.engine.url}")

# Check if there's any test-related logic
print(f"\n3. Is pytest running? {hasattr(sys, '_called_from_test')}")
print(f"4. Is test in sys.argv? {'test' in ' '.join(sys.argv)}")
print(f"5. Current working directory: {os.getcwd()}")

# Check environment
print(f"\n6. NODE_ENV: {os.environ.get('NODE_ENV', 'NOT SET')}")
print(f"7. TESTING: {os.environ.get('TESTING', 'NOT SET')}")
print(f"8. ENV: {os.environ.get('ENV', 'NOT SET')}")
