from __future__ import annotations

from datetime import date, time
from unittest.mock import MagicMock

import pytest

from app.core.exceptions import ValidationException
from app.schemas.booking import BookingCreate
from app.services.booking_service import BookingService


def _base_payload() -> dict:
    return {
        "instructor_id": "01HZTESTINSTRUCTOR00000000000",
        "instructor_service_id": "01HZTESTSERVICE000000000000",
        "booking_date": date(2025, 1, 1),
        "start_time": time(9, 0),
        "selected_duration": 60,
    }


def _make_travel_booking(location_type: str) -> BookingCreate:
    payload = {
        **_base_payload(),
        "location_type": location_type,
        "location_address": "123 Main St, New York, NY",
        "location_lat": 40.751,
        "location_lng": -73.989,
    }
    return BookingCreate(**payload)


def _make_service(db, is_covered: bool) -> BookingService:
    service = BookingService(db)
    service.filter_repository.is_location_in_service_area = MagicMock(return_value=is_covered)
    return service


def test_student_location_in_service_area_succeeds(db) -> None:
    service = _make_service(db, True)
    booking_data = _make_travel_booking("student_location")

    service._validate_service_area(booking_data, booking_data.instructor_id)

    service.filter_repository.is_location_in_service_area.assert_called_once()


def test_student_location_outside_service_area_fails(db) -> None:
    service = _make_service(db, False)
    booking_data = _make_travel_booking("student_location")

    with pytest.raises(ValidationException, match="outside the instructor's service area") as exc:
        service._validate_service_area(booking_data, booking_data.instructor_id)

    assert exc.value.code == "OUTSIDE_SERVICE_AREA"


def test_neutral_location_in_service_area_succeeds(db) -> None:
    service = _make_service(db, True)
    booking_data = _make_travel_booking("neutral_location")

    service._validate_service_area(booking_data, booking_data.instructor_id)

    service.filter_repository.is_location_in_service_area.assert_called_once()


def test_neutral_location_outside_service_area_fails(db) -> None:
    service = _make_service(db, False)
    booking_data = _make_travel_booking("neutral_location")

    with pytest.raises(ValidationException, match="outside the instructor's service area"):
        service._validate_service_area(booking_data, booking_data.instructor_id)


def test_online_skips_service_area_check(db) -> None:
    service = _make_service(db, True)
    booking_data = BookingCreate(**{**_base_payload(), "location_type": "online"})

    service._validate_service_area(booking_data, booking_data.instructor_id)

    service.filter_repository.is_location_in_service_area.assert_not_called()


def test_instructor_location_skips_service_area_check(db) -> None:
    service = _make_service(db, True)
    booking_data = BookingCreate(
        **{**_base_payload(), "location_type": "instructor_location", "meeting_location": "Studio"}
    )

    service._validate_service_area(booking_data, booking_data.instructor_id)

    service.filter_repository.is_location_in_service_area.assert_not_called()


def test_missing_coordinates_for_travel_booking_fails(db) -> None:
    service = _make_service(db, True)
    booking_data = BookingCreate.model_construct(
        **{
            **_base_payload(),
            "location_type": "student_location",
            "location_address": "123 Main St, New York, NY",
            "location_lat": None,
            "location_lng": None,
        }
    )

    with pytest.raises(ValidationException, match="Coordinates are required"):
        service._validate_service_area(booking_data, booking_data.instructor_id)


def test_instructor_with_no_service_areas_rejects_travel(db) -> None:
    service = _make_service(db, False)
    booking_data = _make_travel_booking("student_location")

    with pytest.raises(ValidationException, match="outside the instructor's service area"):
        service._validate_service_area(booking_data, booking_data.instructor_id)
