from ._strict_base import StrictModel

"""Response models for booking endpoints."""

from typing import Optional


class SendRemindersResponse(StrictModel):
    """Response for sending booking reminders."""

    message: str
    reminders_sent: int
    failed_reminders: int


class BookingPreviewResponse(StrictModel):
    """Response for booking preview with privacy protection."""

    booking_id: str
    student_first_name: str
    student_last_name: str
    instructor_first_name: str
    instructor_last_name: str  # Shows last initial for students, full for instructors
    service_name: str
    booking_date: str
    start_time: str
    end_time: str
    duration_minutes: int
    location_type: str
    location_type_display: str
    meeting_location: Optional[str]
    service_area: Optional[str]
    status: str
    student_note: Optional[str]
    total_price: float
