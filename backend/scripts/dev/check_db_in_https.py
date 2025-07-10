import requests
import urllib3

urllib3.disable_warnings()

# Add a debug endpoint to check database
debug_code = """
from app.database import SessionLocal, engine
from app.models.user import User
from app.core.config import settings

# Get database URL
db_url = str(engine.url)
# Mask password
if '@' in db_url:
    parts = db_url.split('@')
    masked = parts[0].split(':')[0] + ':****@' + parts[1]
else:
    masked = db_url

db = SessionLocal()
user_count = db.query(User).count()
sarah = db.query(User).filter(User.email == "sarah.chen@example.com").first()
db.close()

return {
    "db_url": masked,
    "user_count": user_count,
    "sarah_exists": sarah is not None,
    "sarah_id": sarah.id if sarah else None
}
"""

print("Checking database connections on both servers...\n")

# Since we can't easily add an endpoint, let's check the connection directly
# by looking at the logs when we try to connect

# First, let's try a different approach - use the test endpoint with debug
for port, protocol in [(8000, "http"), (8001, "https")]:
    url = f"{protocol}://localhost:{port}/test/config-check"

    try:
        response = requests.get(url, verify=False)
        if response.status_code == 200:
            data = response.json()
            print(f"{protocol.upper()} on port {port}:")
            print(f"  Environment: {data.get('environment')}")
            print(f"  Database URL prefix: {data.get('database_url_prefix')}")
            print()
    except Exception as e:
        print(f"{protocol.upper()} error: {e}")
