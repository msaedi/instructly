#!/usr/bin/env python3
# backend/scripts/create_test_booking.py
"""
Create a test booking in the database for email testing.
"""

import sys
from datetime import date, time, timedelta
from pathlib import Path

# Add backend to path
sys.path.append(str(Path(__file__).parent.parent))

import os

# Load environment variables
from dotenv import load_dotenv

env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

# Force use of Supabase database
if "database_url" in os.environ:
    os.environ["DATABASE_URL"] = os.environ["database_url"]

from app.database import SessionLocal
from app.models.booking import Booking, BookingStatus
from app.models.instructor import InstructorProfile
from app.models.service import Service
from app.models.user import User


def create_test_booking():
    """Create a test booking for email testing."""
    db = SessionLocal()

    try:
        # Find users
        print("🔍 Looking for users...")
        student = db.query(User).filter(User.role == "student").first()
        instructor = db.query(User).filter(User.role == "instructor").join(InstructorProfile).first()

        if not student:
            print("❌ No student found in database")
            return None

        if not instructor:
            print("❌ No instructor found in database")
            return None

        print(f"✅ Found student: {student.email}")
        print(f"✅ Found instructor: {instructor.email}")

        # Find a service
        service = (
            db.query(Service)
            .filter(Service.instructor_profile_id == instructor.instructor_profile.id, Service.is_active == True)
            .first()
        )

        if not service:
            print("❌ No active service found for instructor")
            # Create a test service
            service = Service(
                instructor_profile_id=instructor.instructor_profile.id,
                skill="Test Piano Lessons",
                hourly_rate=75.00,
                areas_served="Manhattan, Brooklyn",
                min_lesson_duration=60,
                max_lesson_duration=120,
                is_active=True,
            )
            db.add(service)
            db.commit()
            db.refresh(service)
            print("✅ Created test service")
        else:
            print(f"✅ Found service: {service.skill}")

        # Create booking for tomorrow
        tomorrow = date.today() + timedelta(days=1)

        # Check if booking already exists
        existing = (
            db.query(Booking)
            .filter(
                Booking.student_id == student.id,
                Booking.instructor_id == instructor.id,
                Booking.booking_date == tomorrow,
                Booking.status == BookingStatus.CONFIRMED,
            )
            .first()
        )

        if existing:
            print(f"✅ Using existing booking #{existing.id}")
            return existing

        # Create new booking
        booking = Booking(
            student_id=student.id,
            instructor_id=instructor.id,
            service_id=service.id,
            booking_date=tomorrow,
            start_time=time(14, 0),  # 2:00 PM
            end_time=time(15, 0),  # 3:00 PM
            service_name=service.skill,
            hourly_rate=service.hourly_rate,
            total_price=service.hourly_rate,
            duration_minutes=60,
            status=BookingStatus.CONFIRMED,
            location_type="instructor_location",
            meeting_location="123 Music Studio, New York, NY 10001",
            student_note="Looking forward to the lesson!",
            service_area="Manhattan",
        )

        db.add(booking)
        db.commit()
        db.refresh(booking)

        print(f"\n✅ Created test booking #{booking.id}")
        print(f"   Student: {student.email}")
        print(f"   Instructor: {instructor.email}")
        print(f"   Service: {booking.service_name}")
        print(f"   Date: {booking.booking_date}")
        print(f"   Time: {booking.start_time} - {booking.end_time}")
        print(f"   Status: {booking.status}")

        return booking

    except Exception as e:
        print(f"❌ Error creating booking: {str(e)}")
        import traceback

        traceback.print_exc()
        db.rollback()
        return None

    finally:
        db.close()


if __name__ == "__main__":
    booking = create_test_booking()
    if booking:
        print("\n🎉 Test booking ready for email testing!")
        print(f"   Run: python scripts/test_notification_migration.py")
    else:
        print("\n❌ Failed to create test booking")
