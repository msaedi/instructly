import urllib3

urllib3.disable_warnings()

# Create a special test endpoint that does raw database queries
test_endpoint_code = '''
# Add this temporarily to test_auth.py to debug

@router.get("/db-test")
def test_database():
    """Test raw database access"""
    from app.database import SessionLocal
    from sqlalchemy import text

    db = SessionLocal()
    try:
        # Test 1: Can we connect at all?
        result = db.execute(text("SELECT 1"))
        can_connect = result.scalar() == 1

        # Test 2: Count users
        user_count = db.execute(text("SELECT COUNT(*) FROM users")).scalar()

        # Test 3: Find sarah
        sarah_result = db.execute(
            text("SELECT id, email FROM users WHERE email = :email"),
            {"email": "sarah.chen@example.com"}
        ).first()

        return {
            "can_connect": can_connect,
            "user_count": user_count,
            "sarah_found": sarah_result is not None,
            "sarah_data": dict(sarah_result) if sarah_result else None
        }
    finally:
        db.close()
'''

print("Let's check if HTTPS can access the database at all...")
print("\nYou need to temporarily add this to backend/app/routes/test_auth.py:")
print("=" * 60)
print(test_endpoint_code)
print("=" * 60)
print("\nThen restart the HTTPS server and run this script again.")
