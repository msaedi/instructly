import os
from pathlib import Path
import sys

# Check environment before and after loading
print("1. Initial environment:")
print(f"   DATABASE_URL: {os.environ.get('DATABASE_URL', 'NOT SET')}")
print(f"   database_url: {os.environ.get('database_url', 'NOT SET')}")
print(f"   TEST_DATABASE_URL: {os.environ.get('TEST_DATABASE_URL', 'NOT SET')}")
print(f"   test_database_url: {os.environ.get('test_database_url', 'NOT SET')}")

# Now load like run_ssl.py does
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))
os.chdir(backend_dir)

from dotenv import load_dotenv

load_dotenv()

print("\n2. After load_dotenv:")
print(f"   DATABASE_URL: {os.environ.get('DATABASE_URL', 'NOT SET')}")
print(f"   database_url: {os.environ.get('database_url', 'NOT SET')}")
print(f"   TEST_DATABASE_URL: {os.environ.get('TEST_DATABASE_URL', 'NOT SET')}")
print(f"   test_database_url: {os.environ.get('test_database_url', 'NOT SET')}")

# Check what settings uses
from app.core.config import settings

print(f"\n3. Settings database_url: {settings.database_url}")
