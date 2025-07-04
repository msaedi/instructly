#!/usr/bin/env python3
# backend/tests/schemas/debug_validator.py
"""Debug the exact validator issue."""

from datetime import time

from pydantic import BaseModel, ValidationError, field_validator


class TestModelV2(BaseModel):
    """Test with Pydantic v2 syntax."""

    start_time: time
    end_time: time

    @field_validator("end_time")
    def validate_time_order(cls, v, info):
        print(f"Validator called with v={v}")
        print(f"info type: {type(info)}")
        print(f"info.data: {info.data if hasattr(info, 'data') else 'No data attribute'}")

        # This is the correct Pydantic v2 way
        if hasattr(info, "data") and info.data and "start_time" in info.data:
            if v <= info.data["start_time"]:
                raise ValueError("End time must be after start time")
        return v


def test_validator():
    print("Testing Pydantic v2 validator...")

    # Valid case
    try:
        model = TestModelV2(start_time=time(9, 0), end_time=time(10, 0))
        print(f"✅ Valid model created: {model}")
    except Exception as e:
        print(f"❌ Error creating valid model: {e}")

    # Invalid case
    print("\nTesting invalid case...")
    try:
        invalid = TestModelV2(start_time=time(10, 0), end_time=time(9, 0))
        print(f"❌ Should have failed but got: {invalid}")
    except ValidationError as e:
        print(f"✅ Validation failed as expected: {e.errors()[0]['msg']}")
    except Exception as e:
        print(f"❌ Unexpected error: {type(e).__name__}: {e}")


if __name__ == "__main__":
    import pydantic

    print(f"Pydantic version: {pydantic.__version__}")
    test_validator()
