"""
Check current query performance for booked slots endpoint
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from sqlalchemy import text
from datetime import date, timedelta
import logging

# Enable SQL logging
logging.basicConfig()
logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)

def check_current_queries():
    db = SessionLocal()
    
    print("=== Checking Current Query Pattern ===\n")
    
    # Simulate the current endpoint query
    start_date = date.today()
    week_dates = [start_date + timedelta(days=i) for i in range(7)]
    
    # This is what the endpoint currently does
    from app.models.booking import Booking
    from app.models.availability import AvailabilitySlot, InstructorAvailability
    from app.models.user import User
    from app.models.service import Service
    
    result = (
        db.query(
            Booking.booking_date.label("date"),
            AvailabilitySlot.start_time,
            AvailabilitySlot.end_time,
            User.full_name.label("student_name"),
            Service.skill.label("service_name")
        )
        .join(AvailabilitySlot, Booking.availability_slot_id == AvailabilitySlot.id)
        .join(InstructorAvailability, AvailabilitySlot.availability_id == InstructorAvailability.id)
        .join(User, Booking.student_id == User.id)
        .join(Service, Booking.service_id == Service.id)
        .filter(
            InstructorAvailability.instructor_id == 117,  # Example instructor
            Booking.booking_date.in_(week_dates),
            Booking.status.in_(['CONFIRMED', 'COMPLETED'])
        )
        .all()
    )
    
    print(f"\nFound {len(result)} booked slots")
    
    # Check what additional data we'd need for the preview
    print("\nData available in current query:")
    if result:
        first = result[0]
        print(f"  - Date: {first.date}")
        print(f"  - Time: {first.start_time} - {first.end_time}")
        print(f"  - Student name: {first.student_name}")
        print(f"  - Service: {first.service_name}")
    
    print("\nData NOT available that A-Team needs:")
    print("  - booking_id (for navigation)")
    print("  - location_type (not in model yet)")
    print("  - duration_minutes")
    print("  - service areas")
    print("  - meeting_location")
    
    db.close()

if __name__ == "__main__":
    check_current_queries()