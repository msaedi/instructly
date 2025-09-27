#!/usr/bin/env python3
# backend/scripts/check_bookings.py
"""
Script to check bookings in the database, specifically for Sarah Chen.
This helps verify Work Stream #9 implementation.
"""

from datetime import date
from pathlib import Path
import sys

# Add the parent directory to the path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.enums import RoleName
from app.models.booking import Booking
from app.models.instructor import InstructorProfile
from app.models.service import Service
from app.models.user import User


def check_bookings():
    """Check bookings in the database."""
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    session = Session(engine)

    try:
        print("=== CHECKING BOOKINGS FOR SARAH CHEN ===\n")

        # Find Sarah Chen
        sarah = session.query(User).filter(User.email == "sarah.chen@example.com").first()

        if not sarah:
            print("ERROR: Sarah Chen not found in database!")
            print("\nAll instructor emails:")
            instructors = session.query(User).filter(User.role == RoleName.INSTRUCTOR).all()
            for inst in instructors:
                print(f"  - {inst.email}")
            return

        print(f"Found Sarah Chen: ID={sarah.id}, Email={sarah.email}")

        # Get her profile
        profile = session.query(InstructorProfile).filter(InstructorProfile.user_id == sarah.id).first()

        if profile:
            print(f"Profile ID: {profile.id}")

            # Get her services
            services = session.query(Service).filter(Service.instructor_profile_id == profile.id).all()

            print(f"\nServices ({len(services)} total):")
            for svc in services:
                status = "ACTIVE" if svc.is_active else "INACTIVE"
                print(f"  - {svc.skill} (${svc.hourly_rate}/hr) - {status}")

        # Check bookings AS INSTRUCTOR
        instructor_bookings = (
            session.query(Booking).filter(Booking.instructor_id == sarah.id).order_by(Booking.booking_date).all()
        )

        print(f"\n=== BOOKINGS WHERE SARAH IS INSTRUCTOR: {len(instructor_bookings)} total ===")

        if instructor_bookings:
            # Group by status
            past = [b for b in instructor_bookings if b.booking_date < date.today()]
            today = [b for b in instructor_bookings if b.booking_date == date.today()]
            future = [b for b in instructor_bookings if b.booking_date > date.today()]

            print(f"  - Past bookings: {len(past)}")
            print(f"  - Today's bookings: {len(today)}")
            print(f"  - Future bookings: {len(future)}")

            # Show details of first few
            print("\nFirst 5 bookings:")
            for booking in instructor_bookings[:5]:
                print(f"\n  Booking ID: {booking.id}")
                print(f"  Date: {booking.booking_date} {booking.start_time}-{booking.end_time}")
                print(f"  Service: {booking.service_name} (${booking.hourly_rate}/hr)")
                print(f"  Status: {booking.status}")
                print(f"  availability_slot_id: {booking.availability_slot_id}")

                # Get student name
                student = session.query(User).filter(User.id == booking.student_id).first()
                if student:
                    print(f"  Student: {student.full_name}")
        else:
            print("  No bookings found!")

        # Check bookings AS STUDENT (should be none)
        student_bookings = session.query(Booking).filter(Booking.student_id == sarah.id).count()

        print(f"\n=== BOOKINGS WHERE SARAH IS STUDENT: {student_bookings} ===")

        # Overall booking stats
        print("\n=== OVERALL BOOKING STATS ===")
        total_bookings = session.query(Booking).count()
        print(f"Total bookings in system: {total_bookings}")

        # Check bookings with null availability_slot_id (Work Stream #9)
        null_slot_bookings = session.query(Booking).filter(Booking.availability_slot_id is None).count()
        print(f"Bookings with NULL availability_slot_id: {null_slot_bookings}")
        print(f"Bookings with availability_slot_id set: {total_bookings - null_slot_bookings}")

        # Check if any bookings have deprecated services
        if profile:
            inactive_service_bookings = (
                session.query(Booking)
                .join(Service)
                .filter(Service.instructor_profile_id == profile.id, Service.is_active == False)
                .count()
            )
            print(f"\nSarah's bookings with inactive services: {inactive_service_bookings}")

    except Exception as e:
        print(f"ERROR: {str(e)}")
        import traceback

        traceback.print_exc()
    finally:
        session.close()


if __name__ == "__main__":
    check_bookings()
