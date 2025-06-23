# backend/tests/test_connection.py
"""
Test database connection.
"""


import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

from app.core.config import settings


def test_database_connection():
    """Test that we can connect to the database."""
    database_url = settings.database_url

    if not database_url:
        pytest.skip("DATABASE_URL not set")

    print(f"Testing connection to: {database_url[:50]}...")

    try:
        # Create engine
        engine = create_engine(database_url)

        # Test connection
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            assert result.scalar() == 1

            # Test we can query tables
            result = conn.execute(text("SELECT COUNT(*) FROM users"))
            user_count = result.scalar()
            print(f"✅ Database connection successful. Users table has {user_count} records.")

    except OperationalError as e:
        pytest.fail(f"❌ Failed to connect to database: {str(e)}")
    except Exception as e:
        pytest.fail(f"❌ Database operation failed: {str(e)}")


def test_database_tables_exist():
    """Test that all required tables exist."""
    database_url = settings.database_url

    if not database_url:
        pytest.skip("DATABASE_URL not set")

    engine = create_engine(database_url)

    required_tables = [
        "users",
        "instructor_profiles",
        "services",
        "instructor_availability",
        "availability_slots",
        "blackout_dates",
        "bookings",
        "password_reset_tokens",
    ]

    with engine.connect() as conn:
        # Get all table names
        result = conn.execute(
            text(
                """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
        """
            )
        )

        existing_tables = {row[0] for row in result}

        for table in required_tables:
            assert table in existing_tables, f"Table '{table}' does not exist"

        print(f"✅ All {len(required_tables)} required tables exist")


def test_database_performance():
    """Test basic database performance."""
    database_url = settings.database_url

    if not database_url:
        pytest.skip("DATABASE_URL not set")

    engine = create_engine(database_url)

    import time

    with engine.connect() as conn:
        # Test simple query performance
        start = time.time()
        for _ in range(10):
            conn.execute(text("SELECT 1"))
        elapsed = time.time() - start

        avg_time = elapsed / 10
        print(f"✅ Average query time: {avg_time*1000:.2f}ms")

        # Should be reasonably fast (< 50ms average)
        assert avg_time < 0.05, f"Database queries too slow: {avg_time*1000:.2f}ms average"
