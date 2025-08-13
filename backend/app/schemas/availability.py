# backend/app/schemas/availability.py
"""
Availability schemas for InstaInstru platform.

Clean Architecture: Single-table design where slots represent availability.
No InstructorAvailability references, no is_available fields.
A slot exists = instructor is available. Simple.
"""

from datetime import date, time
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator


class AvailabilitySlotBase(BaseModel):
    """Base schema for availability time slots."""

    start_time: time
    end_time: time

    @field_validator("end_time")
    @classmethod
    def validate_time_order(cls, v, info):
        """Ensure end time is after start time."""
        if info.data.get("start_time") and v <= info.data["start_time"]:
            raise ValueError("End time must be after start time")
        return v


class AvailabilitySlotCreate(AvailabilitySlotBase):
    """Schema for creating a new availability slot."""

    instructor_id: str
    specific_date: date


class AvailabilitySlotUpdate(BaseModel):
    """Schema for updating an availability slot."""

    start_time: Optional[time] = None
    end_time: Optional[time] = None

    @field_validator("end_time")
    @classmethod
    def validate_time_order(cls, v, info):
        """Ensure end time is after start time if both provided."""
        if v and info.data.get("start_time") and v <= info.data["start_time"]:
            raise ValueError("End time must be after start time")
        return v


class AvailabilitySlot(AvailabilitySlotBase):
    """Schema for returning availability slot data."""

    id: str
    instructor_id: str
    specific_date: date
    model_config = ConfigDict(from_attributes=True)


class AvailabilitySlotResponse(AvailabilitySlot):
    """Response schema with formatted times for API responses."""

    @property
    def start_time_str(self) -> str:
        """Return start time as HH:MM string."""
        return self.start_time.strftime("%H:%M")

    @property
    def end_time_str(self) -> str:
        """Return end time as HH:MM string."""
        return self.end_time.strftime("%H:%M")
