from datetime import date, time, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

try:  # pragma: no cover - allow running from backend/ root
    from backend.tests._utils import ensure_allowed_durations_for_instructor
except ModuleNotFoundError:  # pragma: no cover
    from tests._utils import ensure_allowed_durations_for_instructor

from app.models.service_catalog import InstructorService as Service
from app.repositories.availability_day_repository import AvailabilityDayRepository
from app.schemas.booking import BookingCreate, BookingUpdate
from app.services.booking_service import BookingService
from app.utils.bitset import bits_from_windows


@pytest.mark.asyncio
async def test_booking_audit_flow(
    db,
    client,
    test_student,
    test_instructor_with_availability,
    auth_headers_admin,
    auth_headers_student,
):
    notification_service = MagicMock()
    notification_service.send_cancellation_notification = AsyncMock()

    booking_service = BookingService(db, notification_service=notification_service)

    profile = test_instructor_with_availability.instructor_profile
    service = db.query(Service).filter(Service.instructor_profile_id == profile.id).first()
    assert service is not None

    ensure_allowed_durations_for_instructor(
        db,
        instructor_user_id=test_instructor_with_availability.id,
        durations=(30, 60),
    )

    booking_day = date.today() + timedelta(days=3)

    booking_payload = BookingCreate(
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=service.id,
        booking_date=booking_day,
        start_time=time(10, 0),
        selected_duration=30,
        student_note="Ring the doorbell",
        location_type="remote",
    )

    AvailabilityDayRepository(db).upsert_week(
        test_instructor_with_availability.id,
        [(booking_day, bits_from_windows([("10:00", "10:30")]))],
    )
    db.commit()

    with patch("app.services.booking_service.PricingService.compute_booking_pricing", return_value=None):
        booking = await booking_service.create_booking(
            student=test_student,
            booking_data=booking_payload,
            selected_duration=30,
        )

    booking_service.update_booking(
        booking.id,
        test_instructor_with_availability,
        BookingUpdate(instructor_note="Bring materials"),
    )

    await booking_service.cancel_booking(booking.id, test_student, reason="Scheduling conflict")

    params = {"entity_type": "booking", "entity_id": booking.id}
    response = client.get("/api/admin/audit", params=params, headers=auth_headers_admin)
    assert response.status_code == 200

    payload = response.json()
    assert payload["total"] == 3
    actions = [entry["action"] for entry in payload["items"]]
    assert set(actions) == {"create", "update", "cancel"}
    assert actions[0] == "cancel"

    actor_roles = {entry["action"]: entry["actor_role"] for entry in payload["items"]}
    assert actor_roles["create"] == "student"
    assert actor_roles["update"] == "instructor"
    assert actor_roles["cancel"] == "student"

    for entry in payload["items"]:
        after = entry.get("after") or {}
        before = entry.get("before") or {}
        assert after.get("student_note") in (None, "[REDACTED]")
        assert before.get("student_note") in (None, "[REDACTED]")

    forbidden = client.get("/api/admin/audit", params=params, headers=auth_headers_student)
    assert forbidden.status_code == 403
