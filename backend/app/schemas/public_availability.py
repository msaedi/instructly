# backend/app/schemas/public_availability.py
"""
Public availability schemas for student-facing API.

These schemas are designed for unauthenticated access and provide
only the necessary information for students to view and book instructors.
No internal IDs or implementation details are exposed.
"""

from datetime import date
from typing import Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field


class PublicTimeSlot(BaseModel):
    """
    A bookable time slot for public viewing.

    Note: No slot IDs exposed - frontend should use instructor_id + date + times
    for booking requests.
    """

    start_time: str = Field(description="Start time in HH:MM format")
    end_time: str = Field(description="End time in HH:MM format")

    model_config = ConfigDict(json_schema_extra={"example": {"start_time": "09:00", "end_time": "10:00"}})


class PublicDayAvailability(BaseModel):
    """Availability for a single day."""

    date: str = Field(description="Date in YYYY-MM-DD format")
    available_slots: List[PublicTimeSlot] = Field(
        default_factory=list, description="List of available time slots for booking"
    )
    is_blackout: bool = Field(default=False, description="Whether this date is completely unavailable")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "date": "2025-07-15",
                "available_slots": [
                    {"start_time": "09:00", "end_time": "10:00"},
                    {"start_time": "10:30", "end_time": "11:30"},
                ],
                "is_blackout": False,
            }
        }
    )


class PublicInstructorAvailability(BaseModel):
    """
    Public availability response for an instructor.

    This is the main response schema for the public endpoint.
    Provides all necessary information for students to view
    availability and make booking decisions.
    """

    instructor_id: int
    instructor_name: str
    availability_by_date: Dict[str, PublicDayAvailability] = Field(
        description="Availability indexed by date string (YYYY-MM-DD)"
    )
    timezone: str = Field(default="America/New_York", description="Instructor's timezone")

    # Summary statistics to help frontend
    total_available_slots: int = Field(description="Total number of bookable slots in the date range")
    earliest_available_date: Optional[str] = Field(None, description="Earliest date with availability")

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "instructor_id": 123,
                "instructor_name": "Sarah Chen",
                "availability_by_date": {
                    "2025-07-15": {
                        "date": "2025-07-15",
                        "available_slots": [
                            {"start_time": "09:00", "end_time": "10:00"},
                            {"start_time": "14:00", "end_time": "15:00"},
                        ],
                        "is_blackout": False,
                    }
                },
                "timezone": "America/New_York",
                "total_available_slots": 2,
                "earliest_available_date": "2025-07-15",
            }
        },
    )


class PublicAvailabilityQuery(BaseModel):
    """Query parameters for public availability endpoint."""

    start_date: date = Field(description="Start date for availability query")
    end_date: Optional[date] = Field(
        None, description="End date for availability query (defaults to 30 days from start)"
    )

    @property
    def date_range_days(self) -> int:
        """Calculate the number of days in the query range."""
        if not self.end_date:
            return 30
        return (self.end_date - self.start_date).days + 1


class PublicAvailabilityMinimal(BaseModel):
    """Minimal availability info - just yes/no."""

    instructor_id: int
    instructor_name: str
    has_availability: bool
    earliest_available_date: Optional[str] = None
    timezone: str = Field(default="America/New_York")


class PublicAvailabilitySummary(BaseModel):
    """Summary availability - time ranges without specific slots."""

    instructor_id: int
    instructor_name: str
    availability_summary: Dict[str, Dict[str, Union[str, bool, float]]]
    timezone: str = Field(default="America/New_York")
    total_available_days: int
    detail_level: Literal["summary"] = "summary"

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "instructor_id": 123,
                "instructor_name": "Sarah Chen",
                "availability_summary": {
                    "2025-07-15": {
                        "date": "2025-07-15",
                        "morning_available": True,
                        "afternoon_available": False,
                        "evening_available": True,
                        "total_hours": 4.5,
                    }
                },
                "timezone": "America/New_York",
                "total_available_days": 5,
                "detail_level": "summary",
            }
        }
    )
