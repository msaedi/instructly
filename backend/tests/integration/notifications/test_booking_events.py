from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
import os
from unittest.mock import patch

import pytest

from app.models.availability import AvailabilitySlot
from app.models.event_outbox import EventOutbox, EventOutboxStatus, NotificationDelivery
from app.models.instructor import InstructorProfile
from app.models.service_catalog import InstructorService as Service
from app.monitoring.prometheus_metrics import (
    notifications_outbox_attempt_total,
    notifications_outbox_total,
)
from app.schemas.booking import BookingCreate
from app.services.booking_service import BookingService
from app.services.notification_provider import NotificationProviderTemporaryError
from app.services.pricing_service import PricingService
from app.tasks.notification_tasks import deliver_event


def _next_available_slot(db, instructor_id: str) -> tuple[Service, AvailabilitySlot]:
    profile = (
        db.query(InstructorProfile)
        .filter(InstructorProfile.user_id == instructor_id)
        .first()
    )
    if profile is None:
        raise RuntimeError("Instructor profile not found")
    active_services = [s for s in profile.instructor_services if s.is_active]
    if not active_services:
        raise RuntimeError("Instructor has no active services")
    service = active_services[0]

    tomorrow = date.today() + timedelta(days=1)
    slot = (
        db.query(AvailabilitySlot)
        .filter(
            AvailabilitySlot.instructor_id == instructor_id,
            AvailabilitySlot.specific_date == tomorrow,
        )
        .first()
    )
    if slot is None:
        raise RuntimeError("Instructor has no availability slot for tomorrow")
    return service, slot


def _select_duration(service: Service) -> int:
    options = sorted(getattr(service, "duration_options", [60]), reverse=True)
    for duration in options:
        try:
            price = service.session_price(duration)
        except Exception:
            continue
        if price >= Decimal("80"):
            return duration
    return options[0]


async def _create_booking(
    db,
    booking_service: BookingService,
    student,
    instructor,
):
    service, slot = _next_available_slot(db, instructor.id)
    duration_minutes = _select_duration(service)
    end_dt = (datetime.combine(slot.specific_date, slot.start_time) + timedelta(minutes=duration_minutes)).time()

    booking_data = BookingCreate(
        instructor_id=instructor.id,
        instructor_service_id=service.id,
        booking_date=slot.specific_date,
        start_time=slot.start_time,
        selected_duration=duration_minutes,
        end_time=end_dt,
        location_type="remote",
        meeting_location="Test location",
        student_note="Integration test",
    )

    booking = await booking_service.create_booking(
        student, booking_data, selected_duration=duration_minutes
    )
    return booking


def _latest_outbox(db, event_type: str) -> EventOutbox:
    return (
        db.query(EventOutbox)
        .filter(EventOutbox.event_type == event_type)
        .order_by(EventOutbox.id.desc())
        .first()
    )


@pytest.mark.asyncio
async def test_booking_create_outbox_to_delivery(
    db,
    test_student,
    test_instructor_with_availability,
    mock_notification_service,
):
    booking_service = BookingService(db, notification_service=mock_notification_service)
    with patch.object(PricingService, "compute_booking_pricing", return_value=None):
        await _create_booking(db, booking_service, test_student, test_instructor_with_availability)

    outbox_row = _latest_outbox(db, "booking.created")
    assert outbox_row is not None
    assert outbox_row.status == EventOutboxStatus.PENDING.value

    attempt_counter = notifications_outbox_attempt_total.labels(event_type="booking.created")
    outcome_counter = notifications_outbox_total.labels(status="sent", event_type="booking.created")
    before_attempts = attempt_counter._value.get()
    before_outcomes = outcome_counter._value.get()

    deliver_event.run(outbox_row.id)
    db.refresh(outbox_row)
    assert outbox_row.status == EventOutboxStatus.SENT.value
    assert outbox_row.attempt_count == 1
    assert attempt_counter._value.get() == before_attempts + 1
    assert outcome_counter._value.get() == before_outcomes + 1

    deliveries = (
        db.query(NotificationDelivery)
        .filter(NotificationDelivery.idempotency_key == outbox_row.idempotency_key)
        .all()
    )
    assert len(deliveries) == 1


@pytest.mark.asyncio
async def test_booking_cancel_event_retries_then_succeeds(
    db,
    test_student,
    test_instructor_with_availability,
    mock_notification_service,
):
    booking_service = BookingService(db, notification_service=mock_notification_service)
    with patch.object(PricingService, "compute_booking_pricing", return_value=None):
        booking = await _create_booking(db, booking_service, test_student, test_instructor_with_availability)

    await booking_service.cancel_booking(booking.id, test_student, reason="schedule conflict")

    outbox_row = _latest_outbox(db, "booking.cancelled")
    assert outbox_row is not None

    attempt_counter = notifications_outbox_attempt_total.labels(event_type="booking.cancelled")
    sent_counter = notifications_outbox_total.labels(status="sent", event_type="booking.cancelled")
    before_attempts = attempt_counter._value.get()
    before_sent = sent_counter._value.get()

    try:
        os.environ["NOTIFICATION_PROVIDER_RAISE_ON"] = "booking.cancelled"
        with pytest.raises(NotificationProviderTemporaryError):
            deliver_event.run(outbox_row.id)
    finally:
        os.environ.pop("NOTIFICATION_PROVIDER_RAISE_ON", None)

    db.refresh(outbox_row)
    assert outbox_row.status == EventOutboxStatus.PENDING.value
    assert outbox_row.attempt_count == 1

    # Retry succeeds
    deliver_event.run(outbox_row.id)
    db.refresh(outbox_row)
    assert outbox_row.status == EventOutboxStatus.SENT.value
    assert outbox_row.attempt_count == 2
    assert attempt_counter._value.get() >= before_attempts + 2
    assert sent_counter._value.get() == before_sent + 1

    deliveries = (
        db.query(NotificationDelivery)
        .filter(NotificationDelivery.idempotency_key == outbox_row.idempotency_key)
        .all()
    )
    assert len(deliveries) == 1
