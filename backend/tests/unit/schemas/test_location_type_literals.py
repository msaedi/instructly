from datetime import date, datetime, time, timezone

from pydantic import ValidationError
import pytest

from app.models.booking import BookingStatus
from app.schemas.booking import BookingResponse


def _base_booking_payload() -> dict:
    now = datetime(2030, 1, 1, 12, 0, tzinfo=timezone.utc)
    return {
        "id": "booking-1",
        "student_id": "student-1",
        "instructor_id": "instructor-1",
        "instructor_service_id": "service-1",
        "booking_date": date(2030, 1, 2),
        "start_time": time(9, 0),
        "end_time": time(10, 0),
        "service_name": "Piano",
        "hourly_rate": 75.0,
        "total_price": 75.0,
        "duration_minutes": 60,
        "status": BookingStatus.CONFIRMED,
        "service_area": None,
        "meeting_location": None,
        "location_type": "online",
        "location_address": None,
        "location_lat": None,
        "location_lng": None,
        "location_place_id": None,
        "student_note": None,
        "instructor_note": None,
        "created_at": now,
        "confirmed_at": None,
        "completed_at": None,
        "cancelled_at": None,
        "cancelled_by_id": None,
        "cancellation_reason": None,
        "student": {
            "id": "student-1",
            "first_name": "Student",
            "last_name": "Test",
            "email": "student@example.com",
        },
        "instructor": {
            "id": "instructor-1",
            "first_name": "Instructor",
            "last_initial": "T",
        },
        "instructor_service": {
            "id": "service-1",
            "name": "Piano",
            "description": None,
        },
    }


class TestLocationTypeLiteral:
    def test_valid_location_types_accepted(self) -> None:
        """All 4 canonical location types should be valid."""
        payload = _base_booking_payload()
        for loc_type in [
            "student_location",
            "instructor_location",
            "online",
            "neutral_location",
        ]:
            response = BookingResponse(**{**payload, "location_type": loc_type})
            assert response.location_type == loc_type

    def test_invalid_location_type_rejected(self) -> None:
        """Invalid location types should raise ValidationError."""
        payload = _base_booking_payload()
        with pytest.raises(ValidationError):
            BookingResponse(**{**payload, "location_type": "invalid_type"})

    def test_legacy_types_rejected(self) -> None:
        """Legacy types should be rejected at schema level."""
        payload = _base_booking_payload()
        for legacy in ["student_home", "neutral", "remote", "in_person"]:
            with pytest.raises(ValidationError):
                BookingResponse(**{**payload, "location_type": legacy})
