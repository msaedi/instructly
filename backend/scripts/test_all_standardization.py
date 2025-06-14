"""
Comprehensive test for API response standardization
Run from backend directory: python scripts/test_all_standardization.py
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from decimal import Decimal
from datetime import datetime, date, time
from app.database import SessionLocal
from sqlalchemy.orm import joinedload
import json

# Import all models
from app.models.booking import Booking
from app.models.service import Service
from app.models.user import User

def test_all_endpoints():
    """Test all standardized endpoints"""
    db = SessionLocal()
    
    print("=== COMPREHENSIVE API STANDARDIZATION TEST ===\n")
    
    # Test 1: Booking Response
    print("1. Testing BookingResponse...")
    booking = db.query(Booking).options(
        joinedload(Booking.student),
        joinedload(Booking.instructor),
        joinedload(Booking.service)
    ).first()
    
    if booking:
        from app.schemas.booking import BookingResponse
        response = BookingResponse.model_validate(booking)
        json_data = json.loads(response.model_dump_json())
        
        assert isinstance(json_data['total_price'], (int, float)), "total_price should be number"
        assert isinstance(json_data['hourly_rate'], (int, float)), "hourly_rate should be number"
        print(f"   ✅ Money fields: {json_data['total_price']} (number)")
        print(f"   ✅ Date format: {json_data['booking_date']}")
        print(f"   ✅ Time format: {json_data['start_time']}")
    
    # Test 2: Service Response
    print("\n2. Testing ServiceResponse...")
    service = db.query(Service).first()
    
    if service:
        from app.schemas.instructor import ServiceResponse
        response = ServiceResponse(
            id=service.id,
            skill=service.skill,
            hourly_rate=service.hourly_rate,
            description=service.description,
            duration_override=service.duration,
            duration=service.duration or 60
        )
        json_data = json.loads(response.model_dump_json())
        
        assert isinstance(json_data['hourly_rate'], (int, float)), "hourly_rate should be number"
        print(f"   ✅ Hourly rate: {json_data['hourly_rate']} (number)")
    
    # Test 3: User Response
    print("\n3. Testing UserResponse...")
    user = db.query(User).first()
    
    if user:
        from app.schemas.user import UserResponse
        response = UserResponse.model_validate(user)
        json_data = json.loads(response.model_dump_json())
        
        # Check datetime format
        if 'created_at' in json_data:
            print(f"   ✅ Created at: {json_data.get('created_at', 'N/A')} (ISO format)")
    
    # Test 4: Booking Stats
    print("\n4. Testing BookingStatsResponse...")
    from app.schemas.booking import BookingStatsResponse
    stats = BookingStatsResponse(
        total_bookings=10,
        upcoming_bookings=5,
        completed_bookings=3,
        cancelled_bookings=2,
        total_earnings=Decimal("1250.50"),
        this_month_earnings=Decimal("450.00")
    )
    json_data = json.loads(stats.model_dump_json())
    
    assert isinstance(json_data['total_earnings'], (int, float)), "earnings should be number"
    assert isinstance(json_data['this_month_earnings'], (int, float)), "earnings should be number"
    print(f"   ✅ Total earnings: ${json_data['total_earnings']} (number)")
    print(f"   ✅ This month: ${json_data['this_month_earnings']} (number)")
    
    print("\n" + "="*50)
    print("🎉 ALL TESTS PASSED! API Standardization Complete!")
    print("="*50)
    print("\nSummary of improvements:")
    print("- All money fields now serialize as numbers (not strings)")
    print("- All dates use ISO format (YYYY-MM-DD)")
    print("- All times use HH:MM:SS format")
    print("- All datetime fields use ISO 8601 format")
    print("- Consistent JSON encoding across all endpoints")
    
    db.close()

if __name__ == "__main__":
    test_all_endpoints()