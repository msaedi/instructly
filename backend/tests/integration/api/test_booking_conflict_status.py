# backend/tests/integration/api/test_booking_conflict_status.py
"""API smoke test to ensure booking conflicts surface as HTTP 409 responses."""

from __future__ import annotations

from datetime import date, time, timedelta

from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm import Session

from app.api import dependencies as api_dependencies
from app.core.config import settings
from app.models.instructor import InstructorProfile
from app.models.service_catalog import InstructorService as Service
from app.models.user import User
from app.repositories.availability_day_repository import AvailabilityDayRepository
from app.schemas.availability_window import WeekSpecificScheduleCreate
from app.services.availability_service import AvailabilityService
from app.services.booking_service import BookingService
from app.utils.bitset import bits_from_windows


def _get_service_with_duration(db: Session, instructor: User, duration_minutes: int) -> Service:
    """Locate an active instructor service that supports the requested duration."""
    profile = db.query(InstructorProfile).filter_by(user_id=instructor.id).first()
    assert profile is not None, "Instructor profile not found"
    services = (
        db.query(Service)
        .filter(Service.instructor_profile_id == profile.id, Service.is_active.is_(True))
        .all()
    )
    assert services, "Instructor has no active services"
    for svc in services:
        options = getattr(svc, "duration_options", []) or []
        if duration_minutes in options:
            return svc
    return services[0]


async def _seed_single_day_availability(
    availability_service: AvailabilityService,
    instructor_id: str,
    target_date: date,
    start: time,
    end: time,
) -> None:
    """Seed a single availability window for the requested day."""
    week_start = target_date - timedelta(days=target_date.weekday())
    payload = WeekSpecificScheduleCreate(
        week_start=week_start,
        clear_existing=True,
        schedule=[
            {
                "date": target_date.isoformat(),
                "start_time": start.strftime("%H:%M"),
                "end_time": end.strftime("%H:%M"),
            }
        ],
    )
    await availability_service.save_week_availability(instructor_id, payload)
    AvailabilityDayRepository(availability_service.db).upsert_week(
        instructor_id,
        [
            (
                target_date,
                bits_from_windows([(start.strftime("%H:%M"), end.strftime("%H:%M"))]),
            )
        ],
    )
    availability_service.db.commit()


@pytest.mark.asyncio
async def test_booking_create_conflict_returns_409(
    client: TestClient,
    db: Session,
    test_student: User,
    test_instructor: User,
    auth_headers_student: dict,
    mock_notification_service,
    monkeypatch: pytest.MonkeyPatch,
):
    # Bypass beta gating to simplify test setup.
    monkeypatch.setenv("SITE_MODE", "preview")

    # Override the booking service to inject mocked notifications.
    client.app.dependency_overrides[
        api_dependencies.get_booking_service
    ] = lambda: BookingService(db, mock_notification_service)

    availability_service = AvailabilityService(db)
    service = _get_service_with_duration(db, test_instructor, duration_minutes=60)
    service.hourly_rate = 120.0
    service.offers_at_location = True
    db.flush()
    target_date = date.today() + timedelta(days=9)
    start_slot = time(13, 0)

    await _seed_single_day_availability(
        availability_service,
        test_instructor.id,
        target_date,
        start=start_slot,
        end=time(17, 0),
    )

    frontend_origin = f"https://{settings.preview_frontend_domain}"

    request_headers = {
        **auth_headers_student,
        "Origin": frontend_origin,
        "Referer": f"{frontend_origin}/bookings",
    }

    payload = {
        "instructor_id": test_instructor.id,
        "instructor_service_id": service.id,
        "booking_date": target_date.isoformat(),
        "start_time": start_slot.strftime("%H:%M"),
        "selected_duration": 60,
        "location_type": "instructor_location",
        "meeting_location": "Test Location",
    }

    first_response = client.post("/api/v1/bookings/", json=payload, headers=request_headers)
    assert first_response.status_code == 201, first_response.text

    second_response = client.post("/api/v1/bookings/", json=payload, headers=request_headers)
    assert second_response.status_code == 409, second_response.text
    response_payload = second_response.json()
    assert response_payload.get("code") == "BOOKING_CONFLICT"
    conflict_details = response_payload.get("errors", {})
    assert conflict_details.get("instructor_id") == test_instructor.id
    assert conflict_details.get("booking_date") == target_date.isoformat()
