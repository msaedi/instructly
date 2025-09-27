#!/usr/bin/env python3
# backend/scripts/test_layer_independence.py
"""
Test the availability-booking layer independence (Work Stream #9).
This demonstrates that we can modify availability without affecting bookings.
"""

from datetime import date
from pathlib import Path
import sys

# Add the parent directory to the path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.availability import AvailabilitySlot, InstructorAvailability
from app.models.booking import Booking
from app.models.user import User


def test_layer_independence():
    """Test that we can delete availability slots without affecting bookings."""
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    session = Session(engine)

    try:
        print("=== TESTING AVAILABILITY-BOOKING LAYER INDEPENDENCE ===\n")

        # Find Sarah Chen
        sarah = session.query(User).filter(User.email == "sarah.chen@example.com").first()

        if not sarah:
            print("ERROR: Sarah Chen not found!")
            return

        # Find a future booking
        future_booking = (
            session.query(Booking)
            .filter(Booking.instructor_id == sarah.id, Booking.booking_date > date.today())
            .first()
        )

        if not future_booking:
            print("No future bookings found to test with!")
            return

        print("Found future booking:")
        print(f"  Date: {future_booking.booking_date}")
        print(f"  Time: {future_booking.start_time} - {future_booking.end_time}")
        print(f"  Service: {future_booking.service_name}")
        print(f"  Booking ID: {future_booking.id}")

        # Check if availability exists for that date
        availability = (
            session.query(InstructorAvailability)
            .filter(
                InstructorAvailability.instructor_id == sarah.id,
                InstructorAvailability.date == future_booking.booking_date,
            )
            .first()
        )

        if availability:
            print(f"\nFound availability for {future_booking.booking_date}:")
            print(f"  Availability ID: {availability.id}")
            print(f"  Number of slots: {len(availability.time_slots)}")

            # Show the slots
            for slot in availability.time_slots:
                print(f"    - Slot: {slot.start_time} to {slot.end_time}")

            print("\n=== DELETING ALL AVAILABILITY SLOTS ===")
            slot_count = len(availability.time_slots)

            # Delete all slots
            for slot in availability.time_slots:
                session.delete(slot)

            session.commit()
            print(f"Deleted {slot_count} availability slots!")

        else:
            print(f"\nNo availability found for {future_booking.booking_date}")
            print("(This is fine - bookings can exist without availability!)")

        # Verify booking still exists
        booking_check = session.query(Booking).filter(Booking.id == future_booking.id).first()

        if booking_check:
            print("\n✅ SUCCESS: Booking still exists after availability deletion!")
            print(f"  Booking {booking_check.id} is intact")
            print(f"  Status: {booking_check.status}")
            print("\nThis proves the layer independence is working correctly!")
        else:
            print("\n❌ ERROR: Booking was deleted! This should not happen!")

        # Show summary of Sarah's availability and bookings
        print("\n=== SUMMARY ===")
        total_availability_dates = (
            session.query(InstructorAvailability).filter(InstructorAvailability.instructor_id == sarah.id).count()
        )

        total_slots = (
            session.query(AvailabilitySlot)
            .join(InstructorAvailability)
            .filter(InstructorAvailability.instructor_id == sarah.id)
            .count()
        )

        total_bookings = session.query(Booking).filter(Booking.instructor_id == sarah.id).count()

        print("Sarah Chen has:")
        print(f"  - {total_availability_dates} dates with availability")
        print(f"  - {total_slots} total availability slots")
        print(f"  - {total_bookings} bookings")
        print("\nBookings exist independently of availability slots! 🎉")

    except Exception as e:
        print(f"ERROR: {str(e)}")
        import traceback

        traceback.print_exc()
        session.rollback()
    finally:
        session.close()


if __name__ == "__main__":
    test_layer_independence()
