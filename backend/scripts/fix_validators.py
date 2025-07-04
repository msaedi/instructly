#!/usr/bin/env python3
# backend/scripts/fix_validators.py
"""
Script to show the correct Pydantic v2 validator syntax.
Run this from the backend directory to test.
"""

from datetime import date, time, timedelta

import pydantic
from pydantic import BaseModel, ValidationError, field_validator


def main():
    print(f"Pydantic version: {pydantic.__version__}")
    print("-" * 50)

    # Test 1: Simple validator
    class TimeRangeModel(BaseModel):
        start_time: time
        end_time: time

        @field_validator("end_time")
        @classmethod
        def validate_time_order(cls, v, info):
            """Correct Pydantic v2 validator syntax."""
            # info.data contains validated fields so far
            if info.data.get("start_time") and v <= info.data["start_time"]:
                raise ValueError("End time must be after start time")
            return v

    print("Test 1: Time range validation")
    try:
        valid = TimeRangeModel(start_time=time(9, 0), end_time=time(10, 0))
        print(f"✅ Valid: {valid}")
    except Exception as e:
        print(f"❌ Error: {e}")

    try:
        invalid = TimeRangeModel(start_time=time(10, 0), end_time=time(9, 0))
        print(f"❌ Should have failed: {invalid}")
    except ValidationError as e:
        print(f"✅ Failed as expected: {e.errors()[0]['msg']}")

    # Test 2: Multiple validators
    class BookingModel(BaseModel):
        instructor_id: int
        booking_date: date
        start_time: time
        end_time: time

        @field_validator("booking_date")
        @classmethod
        def validate_future_date(cls, v):
            """No info needed for single field validation."""
            if v < date.today():
                raise ValueError("Cannot book for past dates")
            return v

        @field_validator("end_time")
        @classmethod
        def validate_time_order(cls, v, info):
            """Need info to access other fields."""
            if info.data.get("start_time") and v <= info.data["start_time"]:
                raise ValueError("End time must be after start time")
            return v

    print("\nTest 2: Booking validation")
    try:
        valid = BookingModel(
            instructor_id=1, booking_date=date.today() + timedelta(days=1), start_time=time(9, 0), end_time=time(10, 0)
        )
        print(f"✅ Valid booking: {valid}")
    except Exception as e:
        print(f"❌ Error: {e}")

    # Test past date
    try:
        past = BookingModel(
            instructor_id=1, booking_date=date.today() - timedelta(days=1), start_time=time(9, 0), end_time=time(10, 0)
        )
        print(f"❌ Should have failed: {past}")
    except ValidationError as e:
        print(f"✅ Past date rejected: {e.errors()[0]['msg']}")

    # Test invalid time order
    try:
        bad_time = BookingModel(
            instructor_id=1, booking_date=date.today() + timedelta(days=1), start_time=time(10, 0), end_time=time(9, 0)
        )
        print(f"❌ Should have failed: {bad_time}")
    except ValidationError as e:
        print(f"✅ Bad time order rejected: {e.errors()[0]['msg']}")

    print("\n" + "=" * 50)
    print("CORRECT PYDANTIC V2 PATTERNS:")
    print("1. Use @classmethod decorator")
    print("2. Use info.data.get('field') to safely access other fields")
    print("3. Single field validators don't need info parameter")
    print("=" * 50)


if __name__ == "__main__":
    main()
