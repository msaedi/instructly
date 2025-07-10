import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# Load .env file
load_dotenv()

# Get database URL
db_url = os.getenv("database_url") or os.getenv("DATABASE_URL")

if not db_url:
    print("❌ No database_url found in environment variables")
else:
    # Hide password in output
    if "@" in db_url:
        visible_url = db_url.split("@")[0].rsplit(":", 1)[0] + ":****@" + db_url.split("@")[1]
        print(f"URL found: {visible_url}")

    try:
        engine = create_engine(db_url)
        with engine.connect() as conn:
            # Use text() for SQLAlchemy 2.0 compatibility
            result = conn.execute(text("SELECT version()"))
            version = result.scalar()
            print("\n✅ Connected successfully!")
            print(f"PostgreSQL version: {version}")

            # Test if we can see tables (should be empty for new database)
            result = conn.execute(
                text(
                    """
                SELECT COUNT(*)
                FROM information_schema.tables
                WHERE table_schema = 'public'
            """
                )
            )
            table_count = result.scalar()
            print(f"Number of tables in public schema: {table_count}")

    except Exception as e:
        print(f"\n❌ Connection failed: {e}")
