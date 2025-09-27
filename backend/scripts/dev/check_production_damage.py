#!/usr/bin/env python3
# backend/scripts/check_production_damage.py
"""
Script to check if production database was affected by test runs.

This script helps identify if your production database has been
accidentally wiped by test runs and provides recovery guidance.
"""

from datetime import datetime
import os
from pathlib import Path
import sys

# Add the parent directory to the path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError


def check_production_database():
    """Check production database for signs of test damage."""
    print("=" * 60)
    print("Production Database Damage Assessment")
    print("=" * 60)
    print()

    # Load environment
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)

    # Get production database URL (lowercase)
    prod_url = os.getenv("database_url")

    if not prod_url:
        print("❌ No database_url found in environment.")
        print("   Please set database_url to your production database.")
        return

    # Safety check - make sure this looks like production
    if "test" in prod_url.lower():
        print("⚠️  WARNING: Your DATABASE_URL contains 'test'.")
        print("   This might not be your production database.")
        confirm = input("Continue anyway? (yes/no): ")
        if confirm.lower() != "yes":
            return

    print("Connecting to production database...")
    print("(This is read-only - no data will be modified)")
    print()

    try:
        engine = create_engine(prod_url)

        with engine.connect() as conn:
            # Get database name
            result = conn.execute(text("SELECT current_database()"))
            db_name = result.scalar()
            print(f"Connected to database: {db_name}")
            print()

            # Check table existence
            tables_query = text(
                """
                SELECT tablename
                FROM pg_tables
                WHERE schemaname = 'public'
                ORDER BY tablename
            """
            )
            result = conn.execute(tables_query)
            tables = [row[0] for row in result]

            print(f"Found {len(tables)} tables:")
            for table in tables:
                print(f"  - {table}")
            print()

            # Expected tables
            expected_tables = [
                "users",
                "instructor_profiles",
                "services",
                "availability_slots",
                "bookings",
                "blackout_dates",
                "password_reset_tokens",
                "alembic_version",
            ]

            missing_tables = set(expected_tables) - set(tables)
            if missing_tables:
                print("⚠️  WARNING: Missing expected tables:")
                for table in missing_tables:
                    print(f"  - {table}")
                print()

            # Check data in each table
            print("Checking data in tables:")
            print("-" * 40)

            damage_indicators = []

            for table in expected_tables:
                if table not in tables:
                    continue

                if table == "alembic_version":
                    continue  # Skip migration table

                # Count rows
                count_query = text(f"SELECT COUNT(*) FROM {table}")
                count = conn.execute(count_query).scalar()

                # Get latest record date if applicable
                date_info = ""
                if table in ["users", "bookings", "availability_slots"]:
                    try:
                        date_query = text(
                            f"""
                            SELECT MAX(created_at)
                            FROM {table}
                            WHERE created_at IS NOT NULL
                        """
                        )
                        latest = conn.execute(date_query).scalar()
                        if latest:
                            days_ago = (datetime.now() - latest).days
                            date_info = f" (latest: {days_ago} days ago)"
                    except:
                        pass

                print(f"{table:25} {count:8,} rows{date_info}")

                # Check for damage indicators
                if count == 0 and table in ["users", "instructor_profiles"]:
                    damage_indicators.append(f"{table} is empty")

                if table == "users" and count > 0:
                    # Check for test users
                    test_query = text(
                        """
                        SELECT COUNT(*)
                        FROM users
                        WHERE email LIKE '%@example.com'
                    """
                    )
                    test_count = conn.execute(test_query).scalar()
                    if test_count > 0:
                        print(f"  ⚠️  Found {test_count} test users (@example.com)")
                        damage_indicators.append(f"Found {test_count} test users")

            print("-" * 40)

            # Check for recent deletions
            print("\nChecking for recent mass deletions...")

            # PostgreSQL doesn't track deletions by default, but we can check patterns
            if "bookings" in tables:
                # Check for gaps in IDs (might indicate deletions)
                gap_query = text(
                    """
                    WITH id_sequence AS (
                        SELECT
                            id,
                            lead(id) OVER (ORDER BY id) as next_id
                        FROM bookings
                    )
                    SELECT COUNT(*) as gap_count
                    FROM id_sequence
                    WHERE next_id - id > 100
                """
                )
                gaps = conn.execute(gap_query).scalar()
                if gaps and gaps > 0:
                    print(f"  ⚠️  Found {gaps} large gaps in booking IDs")
                    damage_indicators.append(f"{gaps} ID gaps in bookings")

            # Summary
            print("\n" + "=" * 60)
            print("DAMAGE ASSESSMENT SUMMARY")
            print("=" * 60)

            if damage_indicators:
                print("\n🚨 POTENTIAL DAMAGE DETECTED:")
                for indicator in damage_indicators:
                    print(f"  - {indicator}")

                print("\nRECOVERY RECOMMENDATIONS:")
                print("1. Check your latest backup immediately")
                print("2. Compare current data with expected data")
                print("3. Look for missing users or bookings")
                print("4. Implement the test database safety fix ASAP")
                print("5. Consider enabling PostgreSQL audit logging")
            else:
                print("\n✅ No obvious signs of test damage detected.")
                print("   However, you should still:")
                print("   1. Implement the test database safety fix")
                print("   2. Verify your data integrity manually")
                print("   3. Ensure you have recent backups")

            print("\n" + "=" * 60)

    except OperationalError as e:
        print(f"\n❌ Failed to connect to database: {e}")
    except Exception as e:
        print(f"\n❌ Error checking database: {e}")


def main():
    """Main entry point."""
    print("🔍 InstaInstru Production Database Damage Check")
    print()
    print("This script will check your production database for signs")
    print("of accidental test wipes. It performs READ-ONLY checks.")
    print()

    confirm = input("Check production database? (yes/no): ")
    if confirm.lower() != "yes":
        print("Check cancelled.")
        return

    print()
    check_production_database()


if __name__ == "__main__":
    main()
