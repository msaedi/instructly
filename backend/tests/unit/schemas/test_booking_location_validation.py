from __future__ import annotations

from datetime import date, time

from pydantic import ValidationError
import pytest

from app.schemas.booking import BookingCreate


def _base_payload() -> dict:
    return {
        "instructor_id": "01HZZZZZZZZZZZZZZZZZZZZZZZ",
        "instructor_service_id": "01HYYYYYYYYYYYYYYYYYYYYYY",
        "booking_date": date(2025, 1, 1),
        "start_time": time(9, 0),
        "selected_duration": 60,
    }


def test_online_booking_no_address_required() -> None:
    data = BookingCreate(**{**_base_payload(), "location_type": "online"})

    assert data.location_address is None


@pytest.mark.parametrize(
    "location_type",
    ["student_location", "instructor_location", "neutral_location"],
)
def test_non_online_requires_address(location_type: str) -> None:
    payload = {**_base_payload(), "location_type": location_type}

    with pytest.raises(ValidationError, match="Address is required"):
        BookingCreate(**payload)


def test_student_location_with_address_passes() -> None:
    payload = {
        **_base_payload(),
        "location_type": "student_location",
        "location_address": "123 Main St, Brooklyn, NY",
        "location_lat": 40.6892,
        "location_lng": -73.9857,
    }

    data = BookingCreate(**payload)

    assert data.location_address == "123 Main St, Brooklyn, NY"


def test_meeting_location_backfills_address() -> None:
    payload = {
        **_base_payload(),
        "location_type": "neutral_location",
        "meeting_location": "456 Elm St, Queens, NY",
    }

    data = BookingCreate(**payload)

    assert data.location_address == "456 Elm St, Queens, NY"
