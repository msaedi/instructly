import os
from pathlib import Path
import sys

backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))
os.chdir(backend_dir)

from dotenv import load_dotenv

load_dotenv()

from app.core.config import settings

print("Checking database URL methods:\n")
print(f"1. settings.database_url: {settings.database_url[:50]}...")
print(f"2. settings.get_database_url(): {settings.get_database_url()[:50]}...")

# Check if get_database_url has special logic
print(f"\n3. Environment: {settings.environment}")
print(f"4. Is testing environment? {settings.environment == 'testing'}")

# Let's see what triggers test database
import inspect

print("\n5. Source of get_database_url:")
if hasattr(settings, "get_database_url"):
    source = inspect.getsource(settings.get_database_url)
    print(source)
