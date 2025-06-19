#!/usr/bin/env python3
# backend/scripts/test_performance.py
"""
Performance test script for InstaInstru availability operations.
Tests the optimized apply_pattern_to_date_range function.
"""

import os
import sys
import time
import asyncio
from datetime import date, time as datetime_time, timedelta

# Add parent directory to path so we can import app modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from app.database import get_db
from app.services.week_operation_service import WeekOperationService
from app.services.availability_service import AvailabilityService
from app.services.conflict_checker import ConflictChecker
from app.schemas.availability_window import WeekSpecificScheduleCreate, DateTimeSlot
from app.models.availability import InstructorAvailability
from app.models.instructor import InstructorProfile

async def test_apply_pattern_performance():
    """Test the performance of apply_pattern_to_date_range."""
    db = next(get_db())
    elapsed = 0  # Initialize to avoid UnboundLocalError
    
    try:
        # Create services
        availability_service = AvailabilityService(db)
        conflict_checker = ConflictChecker(db)
        week_service = WeekOperationService(db, availability_service, conflict_checker)
        
        # First, find a valid instructor
        instructor_profile = db.query(InstructorProfile).first()
        if not instructor_profile:
            print("❌ No instructor profiles found in database!")
            print("   Please run: python scripts/reset_and_seed_database.py")
            return 0
        
        instructor_id = instructor_profile.user_id
        print(f"✅ Using instructor ID: {instructor_id}")
        
        # Use dates far in the future to avoid conflicts with existing data
        from_week_start = date(2025, 12, 1)  # December 2025 - far future Monday
        start_date = date(2026, 1, 5)  # January 2026
        end_date = date(2026, 2, 28)  # February 2026 (55 days)
        
        print(f"Testing apply_pattern_to_date_range performance...")
        print(f"Date range: {start_date} to {end_date} ({(end_date - start_date).days + 1} days)")
        
        # Clear any existing availability for the test dates to avoid conflicts
        print("\n🧹 Clearing test date ranges...")
        
        # Clear source week
        existing_source = db.query(InstructorAvailability).filter(
            InstructorAvailability.instructor_id == instructor_id,
            InstructorAvailability.date >= from_week_start,
            InstructorAvailability.date < from_week_start + timedelta(days=7)
        ).all()
        
        for entry in existing_source:
            db.delete(entry)
        
        # Clear target range
        existing_target = db.query(InstructorAvailability).filter(
            InstructorAvailability.instructor_id == instructor_id,
            InstructorAvailability.date >= start_date,
            InstructorAvailability.date <= end_date
        ).all()
        
        for entry in existing_target:
            db.delete(entry)
        
        db.commit()
        print("✅ Test ranges cleared")
        
        # First, create some test availability for the source week
        print("\n📝 Setting up test data...")
        
        # Create a sample week pattern (Monday to Friday, 2 slots per day)
        test_slots = []
        for day_offset in range(5):  # Monday to Friday
            slot_date = from_week_start + timedelta(days=day_offset)
            test_slots.extend([
                DateTimeSlot(
                    date=slot_date,
                    start_time=datetime_time(9, 0),
                    end_time=datetime_time(12, 0)
                ),
                DateTimeSlot(
                    date=slot_date,
                    start_time=datetime_time(14, 0),
                    end_time=datetime_time(17, 0)
                )
            ])
        
        week_data = WeekSpecificScheduleCreate(
            week_start=from_week_start,
            schedule=test_slots,
            clear_existing=True
        )
        
        # Save the test availability
        await availability_service.save_week_availability(instructor_id, week_data)
        
        # Verify source week has data
        source_week = availability_service.get_week_availability(instructor_id, from_week_start)
        print(f"✅ Source week has availability for {len(source_week)} days")
        total_slots = sum(len(slots) for slots in source_week.values())
        print(f"   Total slots in source week: {total_slots}")
        
        # Run the actual performance test
        print("\n🚀 Running performance test...")
        print("   Applying pattern to date range...")
        start_time = time.time()
        
        result = await week_service.apply_pattern_to_date_range(
            instructor_id=instructor_id,
            from_week_start=from_week_start,
            start_date=start_date,
            end_date=end_date
        )
        
        elapsed = time.time() - start_time
        
        print(f"\n📊 Results:")
        print(f"Time taken: {elapsed:.2f} seconds")
        print(f"Days created: {result.get('dates_created', 0)}")
        print(f"Days modified: {result.get('dates_modified', 0)}")
        print(f"Days skipped: {result.get('dates_skipped', 0)}")
        print(f"Slots created: {result.get('slots_created', 0)}")
        print(f"Slots skipped: {result.get('slots_skipped', 0)}")
        print(f"Performance: {((end_date - start_date).days + 1) / elapsed:.1f} days/second")
        
        # Expected slots calculation
        weekdays_in_range = sum(1 for i in range((end_date - start_date).days + 1) 
                               if (start_date + timedelta(days=i)).weekday() < 5)
        expected_slots = weekdays_in_range * 2  # 2 slots per weekday
        
        print(f"\n📈 Analysis:")
        print(f"Expected weekdays: {weekdays_in_range}")
        print(f"Expected slots: {expected_slots}")
        print(f"Actual slots created: {result.get('slots_created', 0)}")
        
        if elapsed < 1.0:
            print("✅ EXCELLENT: Sub-second performance!")
        elif elapsed < 5.0:
            print("✅ GOOD: Acceptable performance")
        else:
            print("⚠️  SLOW: Performance needs optimization")
        
        # Cleanup test data (optional)
        print("\n🧹 Cleaning up test data...")
        # You might want to delete the test availability here
            
    except Exception as e:
        print(f"\n❌ Error during test: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()
    
    return elapsed

async def test_with_bookings():
    """Test performance with existing bookings (more realistic scenario)."""
    print("\n" + "="*50)
    print("Testing with existing bookings...")
    
    # This would test the scenario where some dates have bookings
    # and the system needs to preserve them
    # TODO: Implement if needed
    pass

if __name__ == "__main__":
    print("InstaInstru Performance Test")
    print("=" * 50)
    asyncio.run(test_apply_pattern_performance())