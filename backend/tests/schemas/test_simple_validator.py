# backend/tests/schemas/test_simple_validator.py
"""Test Pydantic v2 validator syntax."""

from datetime import time

from pydantic import BaseModel, ValidationError, field_validator
import pytest


class TimeRangeModel(BaseModel):
    """Model for testing time range validation."""

    start_time: time
    end_time: time

    @field_validator("end_time")
    def validate_time_order(cls, v, info):
        """Test the correct Pydantic v2 syntax."""
        # info.data contains already validated fields
        if info.data and "start_time" in info.data:
            if v <= info.data["start_time"]:
                raise ValueError("End time must be after start time")
        return v


def test_pydantic_v2_validator():
    """Test that our validator syntax works."""
    # Valid case
    model = TimeRangeModel(start_time=time(9, 0), end_time=time(10, 0))
    assert model.start_time < model.end_time

    # Invalid case
    with pytest.raises(ValidationError) as exc:
        TimeRangeModel(start_time=time(10, 0), end_time=time(9, 0))

    errors = exc.value.errors()
    assert len(errors) == 1
    assert "End time must be after start time" in errors[0]["msg"]


if __name__ == "__main__":
    test_pydantic_v2_validator()
    print("✅ Pydantic v2 validator syntax works correctly!")
