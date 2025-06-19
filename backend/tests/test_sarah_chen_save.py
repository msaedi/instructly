# backend/tests/test_sarah_chen_save.py
"""
Test saving availability for Sarah Chen (a real instructor)
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import date, timedelta
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models.user import User
from app.models.booking import Booking, BookingStatus
from app.services.availability_service import AvailabilityService
from app.services.cache_service import get_cache_service
from app.schemas.availability_window import WeekSpecificScheduleCreate, DateTimeSlot

def test_sarah_chen():
    """Test Sarah Chen's availability"""
    db = SessionLocal()
    cache_service = get_cache_service()
    availability_service = AvailabilityService(db, cache_service)
    
    # Get Sarah Chen
    sarah = db.query(User).filter(User.email == "sarah.chen@example.com").first()
    if not sarah:
        print("Sarah Chen not found!")
        return
    
    print(f"\n=== Testing Sarah Chen (ID: {sarah.id}) ===")
    
    # Week of June 23
    week_start = date(2025, 6, 23)
    
    # 1. Check current availability and bookings
    print(f"\n1. Current week starting {week_start}:")
    current = availability_service.get_week_availability(sarah.id, week_start)
    
    for i in range(7):
        day = week_start + timedelta(days=i)
        day_str = str(day)
        slots = current.get(day_str, [])
        
        # Check bookings for this day
        bookings = db.query(Booking).filter(
            Booking.instructor_id == sarah.id,
            Booking.booking_date == day,
            Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED])
        ).count()
        
        print(f"\n   {day.strftime('%A %Y-%m-%d')}:")
        print(f"     Slots: {len(slots)}")
        print(f"     Bookings: {bookings}")
        
        if slots:
            for slot in slots[:3]:  # Show first 3
                print(f"       - {slot['start_time']} to {slot['end_time']}")
            if len(slots) > 3:
                print(f"       ... and {len(slots) - 3} more")
    
    # 2. Try to modify Monday's schedule
    print(f"\n2. Modifying Monday {week_start} schedule:")
    print("   Setting to: 9:00-12:00 and 14:00-17:00")
    
    # Clear cache
    cache_service.delete_pattern(f"*{sarah.id}*")
    
    # Create new schedule for Monday only
    new_schedule = WeekSpecificScheduleCreate(
        week_start=week_start,
        schedule=[
            DateTimeSlot(
                date=week_start,
                start_time="09:00:00",
                end_time="12:00:00",
                is_available=True
            ),
            DateTimeSlot(
                date=week_start,
                start_time="14:00:00",
                end_time="17:00:00",
                is_available=True
            )
        ],
        clear_existing=True
    )
    
    # Save
    import asyncio
    result = asyncio.run(availability_service.save_week_availability(sarah.id, new_schedule))
    
    # Check result
    monday_result = result.get(str(week_start), [])
    print(f"\n3. Save result for Monday: {len(monday_result)} slots")
    for slot in monday_result:
        print(f"   - {slot['start_time']} to {slot['end_time']}")
    
    if '_metadata' in result:
        print(f"\n   Metadata: {result['_metadata']}")
    
    # 4. Verify persistence
    db.commit()
    cache_service.delete_pattern(f"*{sarah.id}*")
    
    fresh = availability_service.get_week_availability(sarah.id, week_start)
    monday_fresh = fresh.get(str(week_start), [])
    
    print(f"\n4. After save (fresh query): {len(monday_fresh)} slots")
    for slot in monday_fresh:
        print(f"   - {slot['start_time']} to {slot['end_time']}")
    
    # Verify
    if len(monday_fresh) == 2 and monday_fresh[0]['start_time'] == '09:00:00':
        print("\n✅ SUCCESS: Changes persisted correctly!")
    else:
        print("\n❌ FAILURE: Changes did not persist!")
    
    db.close()

if __name__ == "__main__":
    test_sarah_chen()