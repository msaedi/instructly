import urllib3

urllib3.disable_warnings()

print("Checking database connections...\n")

# Create a test endpoint to check database
test_code = """
from app.database import SessionLocal
from app.models.user import User

db = SessionLocal()
user_count = db.query(User).count()
test_user = db.query(User).filter(User.email == "test@example.com").first()
db.close()

return {
    "total_users": user_count,
    "test_user_exists": test_user is not None,
    "test_user_id": test_user.id if test_user else None
}
"""

# We need to check the database URL being used
# Since we can't easily add a new endpoint, let's check the running processes
print("The issue is that HTTPS server is not finding users in the database.")
print("This suggests it might be connected to the test database.")
print("\nLet's restart the HTTPS server with explicit environment loading...")
