# backend/app/schemas/public_availability.py
"""
Public availability schemas for student-facing API.

These schemas are designed for unauthenticated access and provide
only the necessary information for students to view and book instructors.
No internal IDs or implementation details are exposed.
"""

from datetime import date
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field


class PublicTimeSlot(BaseModel):
    """
    A bookable time slot for public viewing.

    Note: No slot IDs exposed - frontend should use instructor_id + date + times
    for booking requests.
    """

    start_time: str = Field(description="Start time in HH:MM format")
    end_time: str = Field(description="End time in HH:MM format")

    model_config = ConfigDict(
        json_schema_extra={"example": {"start_time": "09:00", "end_time": "10:00"}}
    )


class PublicDayAvailability(BaseModel):
    """Availability for a single day."""

    date: str = Field(description="Date in YYYY-MM-DD format")
    available_slots: List[PublicTimeSlot] = Field(
        default_factory=list, description="List of available time slots for booking"
    )
    is_blackout: bool = Field(
        default=False, description="Whether this date is completely unavailable"
    )

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

    The detail_level field indicates what data is populated:
    - "minimal": Only has_availability and earliest_available_date
    - "summary": Includes availability_summary but not specific slots
    - "full": Complete availability_by_date with all time slots
    """

    instructor_id: str
    instructor_first_name: Optional[str] = Field(
        None, description="Instructor's first name if privacy settings allow"
    )
    instructor_last_initial: Optional[str] = Field(
        None, description="Instructor's last name initial for privacy"
    )

    # Detail level indicator
    detail_level: str = Field(description="Level of detail: minimal, summary, or full")

    # Full detail fields (populated when detail_level == "full")
    availability_by_date: Optional[Dict[str, PublicDayAvailability]] = Field(
        None, description="Availability indexed by date string (YYYY-MM-DD) - only in full detail"
    )

    # Summary fields (populated when detail_level == "summary")
    availability_summary: Optional[Dict[str, Dict[str, Any]]] = Field(
        None, description="Summary of availability by date - only in summary detail"
    )

    # Minimal fields (always populated)
    has_availability: Optional[bool] = Field(None, description="Whether any availability exists")

    timezone: str = Field(default="America/New_York", description="Instructor's timezone")

    # Summary statistics to help frontend
    total_available_slots: Optional[int] = Field(
        None, description="Total number of bookable slots in the date range"
    )
    total_available_days: Optional[int] = Field(
        None, description="Number of days with availability"
    )
    earliest_available_date: Optional[str] = Field(
        None, description="Earliest date with availability"
    )

    model_config = ConfigDict(
        from_attributes=True,
        # Exclude None values from serialization to keep responses clean
        json_schema_extra={
            "example": {
                "instructor_id": 123,
                "instructor_first_name": "Sarah",
                "instructor_last_initial": "C",
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

    instructor_id: str
    instructor_first_name: Optional[str] = Field(
        None, description="Instructor's first name if privacy settings allow"
    )
    instructor_last_initial: Optional[str] = Field(
        None, description="Instructor's last name initial for privacy"
    )
    has_availability: bool
    earliest_available_date: Optional[str] = None
    timezone: str = Field(default="America/New_York")


class PublicAvailabilitySummary(BaseModel):
    """Summary availability - time ranges without specific slots."""

    instructor_id: str
    instructor_first_name: Optional[str] = Field(
        None, description="Instructor's first name if privacy settings allow"
    )
    instructor_last_initial: Optional[str] = Field(
        None, description="Instructor's last name initial for privacy"
    )
    availability_summary: Dict[str, Dict[str, Union[str, bool, float]]]
    timezone: str = Field(default="America/New_York")
    total_available_days: int
    detail_level: Literal["summary"] = "summary"

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "instructor_id": 123,
                "instructor_first_name": "Sarah",
                "instructor_last_initial": "C",
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


class NextAvailableSlotResponse(BaseModel):
    """Response for next available slot endpoint."""

    found: bool
    date: Optional[str] = Field(None, description="Date of the next available slot (YYYY-MM-DD)")
    start_time: Optional[str] = Field(None, description="Start time (HH:MM:SS)")
    end_time: Optional[str] = Field(None, description="End time (HH:MM:SS)")
    duration_minutes: Optional[int] = Field(None, description="Duration in minutes")
    message: Optional[str] = Field(None, description="Message when no slot is found")

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "found": True,
                    "date": "2025-07-15",
                    "start_time": "09:00:00",
                    "end_time": "10:00:00",
                    "duration_minutes": 60,
                },
                {"found": False, "message": "No available slots found in the next 30 days"},
            ]
        }
    )
