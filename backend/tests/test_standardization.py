"""
Test script to verify API response standardization
Run from backend directory: python scripts/test_standardization.py
"""

import json
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import joinedload

from app.database import SessionLocal
from app.models import *
from app.schemas import *


def test_booking_serialization():
    """Test if booking responses serialize correctly"""
    db = SessionLocal()

    print("=== TESTING BOOKING SERIALIZATION ===")

    # Get a sample booking with relationships
    booking = (
        db.query(Booking)
        .options(
            joinedload(Booking.student),
            joinedload(Booking.instructor),
            joinedload(Booking.service),
        )
        .first()
    )

    if booking:
        from app.schemas.booking import BookingResponse

        # Use Pydantic's from_orm method (or model_validate in Pydantic v2)
        try:
            # Try Pydantic v2 method first
            booking_response = BookingResponse.model_validate(booking)
        except AttributeError:
            # Fall back to Pydantic v1 method
            booking_response = BookingResponse.from_orm(booking)

        # Convert to dict using Pydantic's method
        booking_dict = (
            booking_response.model_dump()
            if hasattr(booking_response, "model_dump")
            else booking_response.dict()
        )

        print("\nPydantic serialization output:")
        print(
            f"  total_price type: {type(booking_dict['total_price'])} = {booking_dict['total_price']}"
        )
        print(
            f"  hourly_rate type: {type(booking_dict['hourly_rate'])} = {booking_dict['hourly_rate']}"
        )
        print(f"  booking_date: {booking_dict['booking_date']}")
        print(f"  start_time: {booking_dict['start_time']}")

        # Test JSON serialization
        json_str = (
            booking_response.model_dump_json()
            if hasattr(booking_response, "model_dump_json")
            else booking_response.json()
        )
        parsed = json.loads(json_str)

        print("\nJSON serialization result:")
        print(
            f"  total_price: {parsed['total_price']} (type in JSON: {type(parsed['total_price'])})"
        )
        print(
            f"  hourly_rate: {parsed['hourly_rate']} (type in JSON: {type(parsed['hourly_rate'])})"
        )

        # Verify they're numbers, not strings
        assert isinstance(
            parsed["total_price"], (int, float)
        ), "total_price should be a number!"
        assert isinstance(
            parsed["hourly_rate"], (int, float)
        ), "hourly_rate should be a number!"

        print("\n✅ SUCCESS: Money fields are now serializing as numbers!")

    else:
        print("No bookings found in database")

    db.close()


def test_service_serialization():
    """Test if service responses serialize correctly"""
    db = SessionLocal()

    print("\n=== TESTING SERVICE SERIALIZATION ===")

    service = db.query(Service).first()
    if service:
        from app.schemas.instructor import ServiceResponse

        service_response = ServiceResponse(
            id=service.id,
            skill=service.skill,
            hourly_rate=service.hourly_rate,
            description=service.description,
            duration_override=service.duration,
            duration=service.duration or 60,
        )

        json_str = service_response.model_dump_json()
        parsed = json.loads(json_str)

        print(
            f"Service hourly_rate: {parsed['hourly_rate']} (type: {type(parsed['hourly_rate'])})"
        )

        assert isinstance(
            parsed["hourly_rate"], (int, float)
        ), "hourly_rate should be a number!"
        print("✅ SUCCESS: Service money fields are numbers!")

    db.close()


if __name__ == "__main__":
    test_booking_serialization()
    test_service_serialization()
