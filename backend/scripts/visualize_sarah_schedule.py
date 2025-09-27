#!/usr/bin/env python3
# backend/scripts/visualize_sarah_schedule.py
"""
Visualize Sarah Chen's availability and bookings to demonstrate layer independence.
Shows the "rug" (availability) and "people" (bookings) concept.
"""

from datetime import date, timedelta
from pathlib import Path
import sys

# Add the parent directory to the path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.availability import InstructorAvailability
from app.models.booking import Booking
from app.models.user import User


def visualize_schedule():
    """Visualize Sarah's schedule for the next week."""
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    session = Session(engine)

    try:
        # Find Sarah Chen
        sarah = session.query(User).filter(User.email == "sarah.chen@example.com").first()

        if not sarah:
            print("ERROR: Sarah Chen not found!")
            return

        print("=== SARAH CHEN'S SCHEDULE VISUALIZATION ===")
        print("🟦 = Availability (The Rug)")
        print("👤 = Booking (The People)")
        print("=" * 60)

        # Get next 7 days
        start_date = date.today()

        for i in range(7):
            current_date = start_date + timedelta(days=i)
            print(f"\n{current_date.strftime('%A, %B %d, %Y')}:")

            # Get availability for this date
            availability = (
                session.query(InstructorAvailability)
                .filter(InstructorAvailability.instructor_id == sarah.id, InstructorAvailability.date == current_date)
                .first()
            )

            # Get bookings for this date
            bookings = (
                session.query(Booking)
                .filter(Booking.instructor_id == sarah.id, Booking.booking_date == current_date)
                .order_by(Booking.start_time)
                .all()
            )

            if availability and availability.time_slots:
                print("  Availability (Rug):")
                for slot in sorted(availability.time_slots, key=lambda s: s.start_time):
                    print(f"    🟦 {slot.start_time.strftime('%H:%M')} - {slot.end_time.strftime('%H:%M')}")
            else:
                print("  No availability set")

            if bookings:
                print("  Bookings (People):")
                for booking in bookings:
                    print(
                        f"    👤 {booking.start_time.strftime('%H:%M')} - {booking.end_time.strftime('%H:%M')} - {booking.service_name} ({booking.status})"
                    )
            else:
                print("  No bookings")

        print("\n" + "=" * 60)
        print("KEY INSIGHT: Bookings (👤) can exist without availability (🟦)!")
        print("You can 'pull the rug' (delete availability) and the people remain standing!")

        # Show a specific example
        print("\n=== EXAMPLE: LAYER INDEPENDENCE ===")

        # Find a date with both availability and bookings
        example_date = (
            session.query(Booking.booking_date)
            .filter(Booking.instructor_id == sarah.id, Booking.booking_date >= date.today())
            .join(
                InstructorAvailability,
                (InstructorAvailability.instructor_id == Booking.instructor_id)
                & (InstructorAvailability.date == Booking.booking_date),
            )
            .first()
        )

        if example_date:
            example_date = example_date[0]
            print(f"\nExample date: {example_date}")

            avail = (
                session.query(InstructorAvailability)
                .filter(InstructorAvailability.instructor_id == sarah.id, InstructorAvailability.date == example_date)
                .first()
            )

            if avail and avail.time_slots:
                print("Current state:")
                print(f"  - Availability slots: {len(avail.time_slots)}")
                for slot in avail.time_slots:
                    print(f"    🟦 {slot.start_time.strftime('%H:%M')} - {slot.end_time.strftime('%H:%M')}")

            bookings = (
                session.query(Booking)
                .filter(Booking.instructor_id == sarah.id, Booking.booking_date == example_date)
                .all()
            )

            if bookings:
                print(f"  - Bookings: {len(bookings)}")
                for b in bookings:
                    print(f"    👤 {b.start_time.strftime('%H:%M')} - {b.end_time.strftime('%H:%M')} - {b.service_name}")

            print("\nYou can delete the availability (🟦) and bookings (👤) will remain!")

    except Exception as e:
        print(f"ERROR: {str(e)}")
        import traceback

        traceback.print_exc()
    finally:
        session.close()


if __name__ == "__main__":
    visualize_schedule()
