#!/usr/bin/env python3
# backend/scripts/setup_test_database.py
"""
Safe test database setup script for InstaInstru.

This script helps developers set up a local test database that is safe to use
for running tests. It ensures the test database is clearly named and separate
from any production data.
"""

import sys
from pathlib import Path
from urllib.parse import urlparse, urlunparse

# Add the parent directory to the path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError


def create_test_database():
    """Create a test database for running tests safely."""
    print("=" * 60)
    print("InstaInstru Test Database Setup")
    print("=" * 60)
    print()

    # Get database connection info
    print("This script will help you create a safe test database.")
    print("The test database will be used for running automated tests.")
    print()
    print("⚠️  IMPORTANT: Never use your production database for testing!")
    print("⚠️  Tests will DELETE ALL DATA after each test run!")
    print()

    # Default values for local PostgreSQL
    default_host = "localhost"
    default_port = "5432"
    default_user = "postgres"
    default_db_name = "instainstru_test"

    print("Enter your PostgreSQL connection details (press Enter for defaults):")
    print()

    host = input(f"Host [{default_host}]: ").strip() or default_host
    port = input(f"Port [{default_port}]: ").strip() or default_port
    user = input(f"Username [{default_user}]: ").strip() or default_user
    password = input("Password: ").strip()

    if not password:
        print("\n❌ Password is required for PostgreSQL connection.")
        return False

    test_db_name = input(f"Test database name [{default_db_name}]: ").strip() or default_db_name

    # Validate test database name
    if "test" not in test_db_name.lower():
        print(f"\n⚠️  WARNING: Database name '{test_db_name}' doesn't contain 'test'.")
        confirm = input("Are you sure you want to use this name? (yes/no): ")
        if confirm.lower() != "yes":
            print("Setup cancelled.")
            return False

    # Build connection URLs
    # Connect to default 'postgres' database to create our test database
    admin_url = f"postgresql://{user}:{password}@{host}:{port}/postgres"
    test_url = f"postgresql://{user}:{password}@{host}:{port}/{test_db_name}"

    print(f"\nAttempting to create database '{test_db_name}'...")

    try:
        # Connect to PostgreSQL
        engine = create_engine(admin_url)

        with engine.connect() as conn:
            # Need to set isolation level for CREATE DATABASE
            conn.execute(text("COMMIT"))

            # Check if database already exists
            result = conn.execute(text("SELECT 1 FROM pg_database WHERE datname = :dbname"), {"dbname": test_db_name})
            exists = result.scalar() is not None

            if exists:
                print(f"\n⚠️  Database '{test_db_name}' already exists.")
                confirm = input("Do you want to DROP and recreate it? (yes/no): ")
                if confirm.lower() == "yes":
                    # Drop existing database
                    conn.execute(text(f'DROP DATABASE "{test_db_name}"'))
                    print(f"Dropped existing database '{test_db_name}'")
                else:
                    print("Using existing database.")
                    print_success_message(test_url)
                    return True

            # Create the database
            conn.execute(text(f'CREATE DATABASE "{test_db_name}"'))
            print(f"✅ Successfully created database '{test_db_name}'")

    except OperationalError as e:
        print(f"\n❌ Failed to connect to PostgreSQL: {e}")
        print("\nMake sure PostgreSQL is running and your credentials are correct.")
        return False
    except Exception as e:
        print(f"\n❌ Error creating database: {e}")
        return False

    # Verify we can connect to the new test database
    try:
        test_engine = create_engine(test_url)
        with test_engine.connect() as conn:
            result = conn.execute(text("SELECT current_database()"))
            db_name = result.scalar()
            print(f"✅ Successfully connected to test database: {db_name}")
    except Exception as e:
        print(f"\n❌ Failed to connect to test database: {e}")
        return False

    print_success_message(test_url)
    return True


def print_success_message(test_url):
    """Print success message with next steps."""
    # Mask password in URL for display
    parsed = urlparse(test_url)
    display_url = urlunparse(parsed._replace(netloc=f"{parsed.username}:****@{parsed.hostname}:{parsed.port}"))

    print("\n" + "=" * 60)
    print("✅ Test Database Setup Complete!")
    print("=" * 60)
    print()
    print("Next steps:")
    print()
    print("1. Add this to your .env file:")
    print(f"   test_database_url={test_url}")
    print()
    print("2. Run tests with:")
    print("   pytest")
    print()
    print("3. The test database will be automatically cleaned after each test.")
    print()
    print("⚠️  REMINDER: Never use your production database URL for test_database_url!")
    print("=" * 60)


def check_env_file():
    """Check if .env file exists and has test_database_url."""
    env_path = Path(__file__).parent.parent / ".env"

    if env_path.exists():
        with open(env_path, "r") as f:
            content = f.read()
            if "test_database_url" in content.lower():
                print("\n✅ Found test_database_url in .env file")
                print("   Make sure it points to a test database, not production!")
                return True

    return False


def main():
    """Main entry point."""
    print("🔧 InstaInstru Test Database Setup Tool")
    print()

    # Check current .env status
    has_test_db = check_env_file()

    if has_test_db:
        print("\nYou already have test_database_url configured.")
        confirm = input("Do you want to set up a new test database? (yes/no): ")
        if confirm.lower() != "yes":
            print("Setup cancelled.")
            return

    # Create test database
    success = create_test_database()

    if not success:
        print("\n❌ Test database setup failed.")
        sys.exit(1)


if __name__ == "__main__":
    main()
