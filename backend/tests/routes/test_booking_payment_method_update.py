"""
Tests for PATCH /bookings/{id}/payment-method endpoint.
"""

from datetime import date, timedelta
from unittest.mock import patch

from fastapi import status
import pytest

from app.auth import create_access_token
from app.models.booking import BookingStatus


@pytest.mark.asyncio
async def test_update_payment_method_retriggers_auth(client, db, test_student, test_instructor_with_availability):
    # Tokens
    student_token = create_access_token(data={"sub": test_student.email})
    headers = {"Authorization": f"Bearer {student_token}"}

    # Prepare a service for the instructor
    from app.models.service_catalog import InstructorService as Service

    svc = (
        db.query(Service)
        .filter_by(instructor_profile_id=test_instructor_with_availability.instructor_profile.id, is_active=True)
        .first()
    )

    # Create booking tomorrow (pending flow through API)
    tomorrow = date.today() + timedelta(days=1)
    payload = {
        "instructor_id": test_instructor_with_availability.id,
        "instructor_service_id": svc.id,
        "booking_date": tomorrow.isoformat(),
        "start_time": "10:00",
        "selected_duration": 60,
        "meeting_location": "Test",
    }

    resp = client.post("/bookings/", json=payload, headers=headers)
    assert resp.status_code == status.HTTP_201_CREATED
    booking_id = resp.json()["id"]

    # Update payment method and ensure it confirms + schedules or authorizes
    with patch("app.repositories.payment_repository.PaymentRepository.create_payment_event") as mock_event:
        upd = client.patch(
            f"/bookings/{booking_id}/payment-method",
            json={"payment_method_id": "pm_test", "set_as_default": False},
            headers=headers,
        )

    assert upd.status_code == status.HTTP_200_OK
    body = upd.json()
    assert body["status"] == BookingStatus.CONFIRMED.value
    assert body["id"] == booking_id
    mock_event.assert_called()
