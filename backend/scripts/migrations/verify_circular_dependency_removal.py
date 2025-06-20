#!/usr/bin/env python3
# backend/scripts/test_circular_dependency_fix.py
"""
Test script to verify that removing the circular dependency doesn't break anything.
Tests booking creation, querying, and slot relationships.
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import date, time, timedelta

from app.database import SessionLocal
from app.models.availability import AvailabilitySlot, InstructorAvailability
from app.models.booking import Booking, BookingStatus
from app.models.instructor import InstructorProfile
from app.models.service import Service
from app.models.user import User


def test_circular_dependency_fix():
    """Test that bookings still work after removing circular dependency."""
    db = SessionLocal()

    try:
        print("=== Testing Circular Dependency Fix ===\n")

        # 1. Find test users
        print("1. Finding test users...")
        instructor = db.query(User).filter(User.email == "sarah.chen@example.com").first()
        student = db.query(User).filter(User.email == "john.smith@example.com").first()

        if not instructor or not student:
            print("   ❌ Test users not found!")
            return False

        print(f"   ✓ Found instructor: {instructor.full_name}")
        print(f"   ✓ Found student: {student.full_name}")

        # 2. Get instructor's service
        print("\n2. Getting instructor's service...")
        profile = db.query(InstructorProfile).filter(InstructorProfile.user_id == instructor.id).first()

        service = (
            db.query(Service).filter(Service.instructor_profile_id == profile.id, Service.is_active == True).first()
        )

        if not service:
            print("   ❌ No active service found!")
            return False

        print(f"   ✓ Found service: {service.skill} at ${service.hourly_rate}/hr")

        # 3. Create availability for tomorrow
        print("\n3. Creating availability for tomorrow...")
        tomorrow = date.today() + timedelta(days=1)

        # Check if availability already exists
        availability = (
            db.query(InstructorAvailability)
            .filter(InstructorAvailability.instructor_id == instructor.id, InstructorAvailability.date == tomorrow)
            .first()
        )

        if not availability:
            availability = InstructorAvailability(instructor_id=instructor.id, date=tomorrow, is_cleared=False)
            db.add(availability)
            db.flush()

        # Create a time slot
        slot = AvailabilitySlot(availability_id=availability.id, start_time=time(14, 0), end_time=time(15, 0))
        db.add(slot)
        db.commit()

        print(f"   ✓ Created availability slot: {slot.id}")

        # 4. Create a booking
        print("\n4. Creating a booking...")
        booking = Booking(
            student_id=student.id,
            instructor_id=instructor.id,
            service_id=service.id,
            availability_slot_id=slot.id,
            booking_date=tomorrow,
            start_time=slot.start_time,
            end_time=slot.end_time,
            service_name=service.skill,
            hourly_rate=service.hourly_rate,
            total_price=service.hourly_rate,
            duration_minutes=60,
            status=BookingStatus.CONFIRMED,
            meeting_location="Central Park",
        )
        db.add(booking)
        db.commit()

        print(f"   ✓ Created booking: {booking.id}")

        # 5. Test querying - Find booking from slot (without circular reference)
        print("\n5. Testing queries without circular dependency...")

        # Method 1: Direct query
        slot_booking = db.query(Booking).filter(Booking.availability_slot_id == slot.id).first()

        if slot_booking:
            print(f"   ✓ Found booking for slot via direct query: {slot_booking.id}")
        else:
            print("   ❌ Could not find booking for slot!")
            return False

        # Method 2: Join query
        result = (
            db.query(AvailabilitySlot, Booking)
            .join(Booking, Booking.availability_slot_id == AvailabilitySlot.id)
            .filter(AvailabilitySlot.id == slot.id)
            .first()
        )

        if result:
            print(f"   ✓ Found booking for slot via join: {result[1].id}")
        else:
            print("   ❌ Join query failed!")
            return False

        # 6. Test the is_booked property (if it exists)
        print("\n6. Testing slot methods...")
        try:
            # Close current session to test the property's internal session
            db.close()

            # Re-query the slot with a new session
            db = SessionLocal()
            test_slot = db.query(AvailabilitySlot).filter(AvailabilitySlot.id == slot.id).first()

            if hasattr(test_slot, "is_booked"):
                is_booked = test_slot.is_booked
                print(f"   ✓ Slot.is_booked property works: {is_booked}")
            else:
                print("   ℹ️  Slot.is_booked property not implemented")
        except Exception as e:
            print(f"   ⚠️  Error testing is_booked: {e}")

        # 7. Clean up test data
        print("\n7. Cleaning up test data...")
        # Re-query to get fresh instances in current session
        booking_to_delete = db.query(Booking).filter(Booking.id == booking.id).first()
        slot_to_delete = db.query(AvailabilitySlot).filter(AvailabilitySlot.id == slot.id).first()

        if booking_to_delete:
            db.delete(booking_to_delete)
        if slot_to_delete:
            db.delete(slot_to_delete)
        db.commit()
        print("   ✓ Test data cleaned up")

        print("\n✅ All tests passed! The circular dependency fix is working correctly.")
        return True

    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback

        traceback.print_exc()
        return False
    finally:
        db.close()


if __name__ == "__main__":
    success = test_circular_dependency_fix()
    exit(0 if success else 1)
