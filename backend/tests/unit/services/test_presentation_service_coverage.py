from __future__ import annotations

from datetime import date, time
from types import SimpleNamespace

from app.services.presentation_service import PresentationService


def _make_booking() -> SimpleNamespace:
    student = SimpleNamespace(first_name="John", last_name="Smith")
    return SimpleNamespace(
        id="booking-1",
        student=student,
        service_area="Upper West Side",
        service_name="Piano",
        duration_minutes=60,
        location_type=None,
    )


def test_format_student_name_for_privacy(db) -> None:
    service = PresentationService(db)

    assert service.format_student_name_for_privacy(None, "Smith") == {
        "first_name": "Unknown",
        "last_initial": "",
    }
    assert service.format_student_name_for_privacy("John", "Smith") == {
        "first_name": "John",
        "last_initial": "S.",
    }
    assert service.format_student_name_for_privacy("Jane", "") == {
        "first_name": "Jane",
        "last_initial": "",
    }


def test_abbreviate_service_area(db) -> None:
    service = PresentationService(db)

    assert service.abbreviate_service_area(None) == "NYC"
    assert service.abbreviate_service_area("Upper West Side, Midtown") == "UWS"
    assert service.abbreviate_service_area("SomewhereReallyLongName") == "SomewhereR"


def test_format_booked_slot_for_display(db) -> None:
    service = PresentationService(db)
    booking = _make_booking()

    result = service.format_booked_slot_for_display(
        booking=booking,
        slot_start_time=time(9, 0),
        slot_end_time=time(10, 0),
        slot_date=date(2025, 1, 1),
    )

    assert result.booking_id == "booking-1"
    assert result.student_first_name == "John"
    assert result.student_last_initial == "S."
    assert result.service_area_short == "UWS"
    assert result.location_type == "neutral"


def test_format_booked_slots_from_service_data(db, monkeypatch) -> None:
    service = PresentationService(db)
    booking = _make_booking()

    def _get_by_id(booking_id: str):
        return booking if booking_id == "booking-1" else None

    monkeypatch.setattr(service, "booking_repository", SimpleNamespace(get_by_id=_get_by_id))

    slots = {
        "2025-01-02": [
            {"booking_id": "booking-1", "start_time": "09:00", "end_time": "10:00"},
            {"booking_id": "missing", "start_time": "11:00", "end_time": "12:00"},
        ]
    }
    results = service.format_booked_slots_from_service_data(slots)

    assert len(results) == 1
    assert results[0].booking_id == "booking-1"


def test_format_duration_for_display(db) -> None:
    service = PresentationService(db)

    assert service.format_duration_for_display(30) == "30 minutes"
    assert service.format_duration_for_display(60) == "1 hour"
    assert service.format_duration_for_display(90) == "1 hour 30 minutes"
    assert service.format_duration_for_display(121) == "2 hours 1 minute"


def test_format_time_for_display(db) -> None:
    service = PresentationService(db)

    assert service.format_time_for_display(time(0, 0)) == "12 AM"
    assert service.format_time_for_display(time(12, 0)) == "12 PM"
    assert service.format_time_for_display(time(13, 5)) == "1:05 PM"
    assert service.format_time_for_display(time(9, 30), use_12_hour=False) == "09:30"


def test_format_price_for_display(db) -> None:
    service = PresentationService(db)

    assert service.format_price_for_display(10) == "$10.00"
    assert service.format_price_for_display(1234.5) == "$1,234.50"
    assert service.format_price_for_display(99.95, include_currency=False) == "99.95"
