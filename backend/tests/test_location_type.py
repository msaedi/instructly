"""
Test script to verify location_type migration
Save as: backend/scripts/test_location_type.py
Run from backend directory: python scripts/test_location_type.py
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models.booking import Booking

def test_location_type():
    db = SessionLocal()
    
    print("=== Testing location_type Migration ===\n")
    
    # Check existing bookings
    bookings = db.query(Booking).limit(10).all()
    
    print(f"Found {len(bookings)} bookings to check:\n")
    
    for booking in bookings:
        print(f"Booking ID: {booking.id}")
        print(f"  - Student ID: {booking.student_id}")
        print(f"  - Date: {booking.booking_date}")
        print(f"  - Service Area: {booking.service_area}")
        print(f"  - Location Type: {booking.location_type}")
        print(f"  - Display: {booking.location_type_display}")
        print()
    
    # Count by location type
    location_counts = {}
    all_bookings = db.query(Booking).all()
    
    for booking in all_bookings:
        loc_type = booking.location_type or 'None'
        location_counts[loc_type] = location_counts.get(loc_type, 0) + 1
    
    print("\nLocation Type Summary:")
    for loc_type, count in location_counts.items():
        print(f"  {loc_type}: {count} bookings")
    
    db.close()

if __name__ == "__main__":
    test_location_type()