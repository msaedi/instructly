#!/usr/bin/env python3
# backend/scripts/check_db_config.py
"""
Check what data exists in the Supabase database.
"""

import sys
from pathlib import Path

# Add backend to Python path
sys.path.append(str(Path(__file__).parent.parent))

import os

# Load environment variables BEFORE importing app modules
from dotenv import load_dotenv

# Load .env file
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

# Force use of the lowercase database_url from .env
if "database_url" in os.environ:
    os.environ["DATABASE_URL"] = os.environ["database_url"]
    print(f"✅ Using Supabase database URL: {os.environ['DATABASE_URL'][:50]}...")

from sqlalchemy import text

from app.database import SessionLocal
from app.models.booking import Booking
from app.models.user import User


def check_database():
    """Check what's in the database."""
    db = SessionLocal()

    try:
        # Test raw connection
        result = db.execute(text("SELECT current_database(), current_user"))
        row = result.fetchone()
        print(f"\n📊 Connected to database: {row[0]} as user: {row[1]}")

        # Check tables
        result = db.execute(
            text(
                """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name
        """
            )
        )
        tables = [row[0] for row in result.fetchall()]
        print(f"\n📋 Tables in database: {', '.join(tables)}")

        # Count records in each table
        print("\n📈 Record counts:")
        for table in ["users", "instructor_profiles", "services", "bookings", "availability_slots"]:
            try:
                result = db.execute(text(f"SELECT COUNT(*) FROM {table}"))
                count = result.scalar()
                print(f"  - {table}: {count}")
            except Exception as e:
                print(f"  - {table}: Error - {str(e)}")

        # Show some users
        print("\n👥 Users in database:")
        users = db.query(User).limit(10).all()
        if users:
            for user in users:
                print(f"  - {user.id}: {user.email} ({user.role})")
                if user.role == "instructor" and hasattr(user, "instructor_profile"):
                    print(f"    Has profile: {user.instructor_profile is not None}")
        else:
            print("  No users found!")

        # Show bookings
        print("\n📅 Bookings in database:")
        bookings = db.query(Booking).limit(10).all()
        if bookings:
            for booking in bookings:
                print(f"  - {booking.id}: {booking.status} - {booking.service_name} on {booking.booking_date}")
        else:
            print("  No bookings found!")

        # Check for test users specifically
        print("\n🔍 Looking for test users:")
        test_emails = [
            "john.smith@example.com",
            "sarah.chen@example.com",
            "emma.johnson@example.com",
            "michael.rodriguez@example.com",
        ]
        for email in test_emails:
            user = db.query(User).filter(User.email == email).first()
            if user:
                print(f"  ✅ Found: {email} (ID: {user.id})")
            else:
                print(f"  ❌ Not found: {email}")

    except Exception as e:
        print(f"\n❌ Database error: {str(e)}")
        print(f"   Error type: {type(e).__name__}")
        import traceback

        traceback.print_exc()

    finally:
        db.close()


if __name__ == "__main__":
    check_database()
