"""
Audit script to identify API response inconsistencies
Run from backend directory: python scripts/audit_api_responses.py
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json

from app.database import SessionLocal
from app.models import *
from app.schemas import *


def check_booking_responses():
    """Check booking response types"""
    db = SessionLocal()

    print("=== BOOKING RESPONSE AUDIT ===")

    # Get a sample booking
    booking = db.query(Booking).first()
    if booking:
        print(f"\nRaw database types:")
        print(f"  total_price: {type(booking.total_price)} = {booking.total_price}")
        print(f"  hourly_rate: {type(booking.hourly_rate)} = {booking.hourly_rate}")
        print(f"  booking_date: {type(booking.booking_date)} = {booking.booking_date}")
        print(f"  start_time: {type(booking.start_time)} = {booking.start_time}")
        print(f"  created_at: {type(booking.created_at)} = {booking.created_at}")

        # Check what happens when serialized
        booking_dict = {
            "total_price": booking.total_price,
            "hourly_rate": booking.hourly_rate,
            "booking_date": booking.booking_date,
            "start_time": booking.start_time,
        }

        print(f"\nDefault JSON serialization:")
        try:
            json_str = json.dumps(booking_dict, default=str)
            print(f"  {json_str}")
        except Exception as e:
            print(f"  Error: {e}")

    db.close()


def check_all_schemas():
    """List all response schemas that need standardization"""
    print("\n=== SCHEMAS NEEDING STANDARDIZATION ===")

    schemas_with_money = [
        "BookingResponse",
        "ServiceResponse",
        "InstructorProfileResponse",
        "BookingStatsResponse",
    ]

    schemas_with_dates = [
        "BookingResponse",
        "AvailabilityWindowResponse",
        "BlackoutDateResponse",
        "UserResponse",
    ]

    print("\nSchemas with money fields:")
    for schema in schemas_with_money:
        print(f"  - {schema}")

    print("\nSchemas with date/time fields:")
    for schema in schemas_with_dates:
        print(f"  - {schema}")


if __name__ == "__main__":
    check_booking_responses()
    check_all_schemas()
