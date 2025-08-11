"""Response models for booking endpoints."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class SendRemindersResponse(BaseModel):
    """Response for sending booking reminders."""

    message: str
    reminders_sent: int
    failed_reminders: int


class BookingPreviewResponse(BaseModel):
    """Response for booking preview."""

    booking_id: int
    student_first_name: str
    student_last_name: str
    # Add other fields as needed based on the service response
