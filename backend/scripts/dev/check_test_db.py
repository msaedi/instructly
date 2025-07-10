from sqlalchemy import create_engine, text

# Force use of test database
test_db_url = "postgresql://postgres:postgres@localhost:5432/instainstru_test"

print(f"Checking TEST database: {test_db_url}")

try:
    engine = create_engine(test_db_url)
    with engine.connect() as conn:
        # Check if we can connect
        result = conn.execute(text("SELECT current_database()"))
        print(f"✅ Connected to: {result.scalar()}")

        # Count users
        result = conn.execute(text("SELECT COUNT(*) FROM users"))
        user_count = result.scalar()
        print(f"User count: {user_count}")

        # List users if any
        if user_count > 0:
            result = conn.execute(text("SELECT id, email FROM users LIMIT 5"))
            print("Users:")
            for row in result:
                print(f"  - {row.id}: {row.email}")
except Exception as e:
    print(f"❌ Error: {e}")
    print("\nThe local test database might not exist or PostgreSQL might not be running")
