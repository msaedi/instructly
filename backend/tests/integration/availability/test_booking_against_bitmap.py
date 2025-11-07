from __future__ import annotations

from datetime import date, timedelta
from importlib import reload
from types import SimpleNamespace

try:  # pragma: no cover - support direct invocation
    from backend.tests._utils import ensure_allowed_durations_for_instructor
except ModuleNotFoundError:  # pragma: no cover
    from tests._utils import ensure_allowed_durations_for_instructor
from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm import Session

import app.api.dependencies.services as dependency_services
import app.main
from app.models.instructor import InstructorProfile
from app.models.service_catalog import InstructorService
from app.models.user import User
from app.repositories.availability_day_repository import AvailabilityDayRepository
import app.routes.availability_windows as availability_routes
import app.routes.bookings as booking_routes
import app.services.availability_service as availability_service_module
import app.services.booking_service as booking_service_module
import app.services.week_operation_service as week_operation_service_module
from app.utils.bitset import bits_from_windows, new_empty_bits


@pytest.fixture
def bitmap_booking_app(monkeypatch: pytest.MonkeyPatch):
    """Reload the FastAPI app with bitmap availability enabled for bookings."""

    reload(availability_service_module)
    reload(week_operation_service_module)
    reload(booking_service_module)
    reload(availability_routes)
    reload(booking_routes)
    reload(dependency_services)
    reload(app.main)

    yield app.main

    reload(availability_service_module)
    reload(week_operation_service_module)
    reload(booking_service_module)
    reload(availability_routes)
    reload(booking_routes)
    reload(dependency_services)
    reload(app.main)


@pytest.fixture
def bitmap_booking_client(bitmap_booking_app) -> TestClient:
    """Return a TestClient for the bitmap-enabled app instance."""
    client = TestClient(bitmap_booking_app.fastapi_app, raise_server_exceptions=False)
    try:
        yield client
    finally:
        client.close()


@pytest.fixture(autouse=True)
def mock_stripe(monkeypatch: pytest.MonkeyPatch):
    """Avoid real Stripe calls during booking creation."""

    def _raise_stripe_error(*_args, **_kwargs):
        raise Exception("Stripe disabled for tests")

    monkeypatch.setattr("stripe.SetupIntent.create", _raise_stripe_error)

    def _fake_get_or_create_customer(self, user_id: str) -> SimpleNamespace:  # pragma: no cover - simple stub
        return SimpleNamespace(stripe_customer_id=f"mock_{user_id}")

    monkeypatch.setattr(
        "app.services.stripe_service.StripeService.get_or_create_customer",
        _fake_get_or_create_customer,
    )


def _next_monday(reference: date) -> date:
    """Return the next Monday strictly after the reference date."""
    days_ahead = (7 - reference.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    return reference + timedelta(days=days_ahead)


def test_bookings_respect_bitmap_availability_windows(
    bitmap_booking_client: TestClient,
    db: Session,
    test_instructor: User,
    auth_headers_instructor: dict,
    auth_headers_student: dict,
    disable_price_floors,
) -> None:
    """Bookings succeed inside availability bits and fail outside."""
    profile = db.query(InstructorProfile).filter_by(user_id=test_instructor.id).first()
    assert profile is not None, "Expected instructor profile to exist"

    service = (
        db.query(InstructorService)
        .filter_by(instructor_profile_id=profile.id, is_active=True)
        .first()
    )
    assert service is not None, "Expected active instructor service"

    ensure_allowed_durations_for_instructor(
        db,
        instructor_user_id=test_instructor.id,
        durations=(30, 60),
    )

    week_start = _next_monday(date.today())
    target_day = week_start + timedelta(days=2)

    availability_body = {
        "week_start": week_start.isoformat(),
        "clear_existing": True,
        "schedule": [
            {
                "date": target_day.isoformat(),
                "start_time": "09:00:00",
                "end_time": "11:00:00",
            },
        ],
    }

    resp = bitmap_booking_client.post(
        "/instructors/availability/week",
        json=availability_body,
        headers=auth_headers_instructor,
    )
    assert resp.status_code == 200, resp.text

    repo = AvailabilityDayRepository(db)
    existing_bits = repo.get_day_bits(test_instructor.id, target_day) or new_empty_bits()
    midnight_bits = bits_from_windows([("23:30:00", "24:00:00")])
    merged_bits = bytes(a | b for a, b in zip(existing_bits, midnight_bits))
    repo.upsert_week(test_instructor.id, [(target_day, merged_bits)])
    db.commit()

    def _error_message(resp) -> str | None:
        """Extract BusinessRuleException message from API responses."""
        try:
            body = resp.json()
        except Exception:
            return None
        if isinstance(body, dict):
            detail = body.get("detail")
            if isinstance(detail, dict):
                return detail.get("message")
            if isinstance(detail, str):
                return detail
        if isinstance(body, str):
            return body
        return None

    def booking_payload(start: str, duration: int, booking_date: date) -> dict[str, str | int]:
        return {
            "instructor_id": test_instructor.id,
            "instructor_service_id": service.id,
            "booking_date": booking_date.isoformat(),
            "start_time": start,
            "selected_duration": duration,
            "location_type": "remote",
        }

    inside_resp = bitmap_booking_client.post(
        "/bookings/",
        json=booking_payload("09:30", 30, target_day),
        headers=auth_headers_student,
    )
    assert inside_resp.status_code == 201, inside_resp.text

    outside_resp = bitmap_booking_client.post(
        "/bookings/",
        json=booking_payload("12:00", 30, target_day),
        headers=auth_headers_student,
    )
    assert outside_resp.status_code == 422, outside_resp.text
    assert _error_message(outside_resp) == "Requested time is not available"

    midnight_inside = bitmap_booking_client.post(
        "/bookings/",
        json=booking_payload("23:30", 30, target_day),
        headers=auth_headers_student,
    )
    assert midnight_inside.status_code == 201, midnight_inside.text

    midnight_outside = bitmap_booking_client.post(
        "/bookings/",
        # This request targets the first half-hour immediately after midnight (24:00–24:30).
        json=booking_payload("00:00", 30, target_day),
        headers=auth_headers_student,
    )
    assert midnight_outside.status_code == 422, midnight_outside.text
    assert _error_message(midnight_outside) == "Requested time is not available"
