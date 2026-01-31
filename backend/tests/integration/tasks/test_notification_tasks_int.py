from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from tests.factories.booking_builders import create_booking_pg_safe

from app.models.booking import BookingStatus
from app.models.event_outbox import EventOutbox, EventOutboxStatus
from app.repositories.event_outbox_repository import EventOutboxRepository
from app.services.notification_provider import NotificationProviderTemporaryError
from app.tasks.notification_tasks import (
    MAX_DELIVERY_ATTEMPTS,
    deliver_event,
    dispatch_pending,
    send_booking_reminders,
)


def _enqueue_outbox(db, *, event_type: str, aggregate_id: str, key: str) -> EventOutbox:
    repo = EventOutboxRepository(db)
    event = repo.enqueue(
        event_type=event_type,
        aggregate_id=aggregate_id,
        payload={"aggregate_id": aggregate_id},
        idempotency_key=key,
    )
    db.commit()
    return event


def test_dispatch_pending_enqueues_events(db):
    event1 = _enqueue_outbox(
        db,
        event_type="booking.created",
        aggregate_id="booking-1",
        key="booking:booking-1:booking.created",
    )
    event2 = _enqueue_outbox(
        db,
        event_type="booking.created",
        aggregate_id="booking-2",
        key="booking:booking-2:booking.created",
    )

    with patch("app.tasks.notification_tasks.enqueue_task") as mocked_enqueue:
        scheduled = dispatch_pending()

    assert scheduled == 2
    called_ids = {call.kwargs["args"][0] for call in mocked_enqueue.call_args_list}
    assert {event1.id, event2.id} == called_ids


def test_deliver_event_missing_returns_none():
    assert deliver_event.run("missing-event-id") is None


def test_deliver_event_success_marks_sent(db):
    event = _enqueue_outbox(
        db,
        event_type="booking.created",
        aggregate_id="booking-3",
        key="booking:booking-3:booking.created",
    )

    deliver_event.run(event.id)
    db.expire_all()
    refreshed = db.get(EventOutbox, event.id)
    assert refreshed is not None
    assert refreshed.status == EventOutboxStatus.SENT.value


def test_deliver_event_temporary_error_retries(db, monkeypatch):
    event = _enqueue_outbox(
        db,
        event_type="booking.created",
        aggregate_id="booking-4",
        key="booking:booking-4:booking.created",
    )
    monkeypatch.setenv("NOTIFICATION_PROVIDER_RAISE_ON", "*")

    with pytest.raises(NotificationProviderTemporaryError):
        deliver_event.run(event.id)

    db.expire_all()
    refreshed = db.get(EventOutbox, event.id)
    assert refreshed is not None
    assert refreshed.status == EventOutboxStatus.PENDING.value
    assert refreshed.attempt_count == 1


def test_deliver_event_temporary_error_terminal(db, monkeypatch):
    event = _enqueue_outbox(
        db,
        event_type="booking.created",
        aggregate_id="booking-5",
        key="booking:booking-5:booking.created",
    )
    event.attempt_count = MAX_DELIVERY_ATTEMPTS - 1
    db.commit()
    monkeypatch.setenv("NOTIFICATION_PROVIDER_RAISE_ON", "*")

    with pytest.raises(NotificationProviderTemporaryError):
        deliver_event.run(event.id)

    db.expire_all()
    refreshed = db.get(EventOutbox, event.id)
    assert refreshed is not None
    assert refreshed.status == EventOutboxStatus.FAILED.value


def test_deliver_event_generic_error_retries(db, monkeypatch):
    event = _enqueue_outbox(
        db,
        event_type="booking.created",
        aggregate_id="booking-6",
        key="booking:booking-6:booking.created",
    )

    with patch(
        "app.tasks.notification_tasks.NotificationProvider.send",
        side_effect=RuntimeError("boom"),
    ):
        with pytest.raises(RuntimeError):
            deliver_event.run(event.id)

    db.expire_all()
    refreshed = db.get(EventOutbox, event.id)
    assert refreshed is not None
    assert refreshed.status == EventOutboxStatus.PENDING.value
    assert refreshed.attempt_count == 1


def test_send_booking_reminders_marks_flags(db, test_booking):
    now = datetime.now(timezone.utc)
    test_booking.status = BookingStatus.CONFIRMED
    test_booking.booking_date = (now + timedelta(hours=24)).date()
    test_booking.booking_start_utc = now + timedelta(hours=24) - timedelta(minutes=10)
    test_booking.reminder_24h_sent = False
    test_booking.reminder_1h_sent = False
    db.flush()

    booking_1h = create_booking_pg_safe(
        db,
        student_id=test_booking.student_id,
        instructor_id=test_booking.instructor_id,
        instructor_service_id=test_booking.instructor_service_id,
        booking_date=test_booking.booking_date + timedelta(days=1),
        start_time=test_booking.start_time,
        end_time=test_booking.end_time,
        service_name=test_booking.service_name,
        hourly_rate=test_booking.hourly_rate,
        total_price=test_booking.total_price,
        duration_minutes=test_booking.duration_minutes,
        status=BookingStatus.CONFIRMED,
        offset_index=10,
    )
    booking_1h.booking_start_utc = now + timedelta(hours=1) - timedelta(minutes=10)
    booking_1h.reminder_24h_sent = False
    booking_1h.reminder_1h_sent = False
    db.commit()

    with patch(
        "app.tasks.notification_tasks.NotificationService.notify_user",
        new=AsyncMock(),
    ):
        result = send_booking_reminders()

    db.refresh(test_booking)
    db.refresh(booking_1h)
    assert result["reminders_24h_sent"] == 2
    assert result["reminders_1h_sent"] == 2
    assert test_booking.reminder_24h_sent is True
    assert booking_1h.reminder_1h_sent is True


def test_send_booking_reminders_failure_does_not_mark_flags(db, test_booking):
    now = datetime.now(timezone.utc)
    test_booking.status = BookingStatus.CONFIRMED
    test_booking.booking_date = (now + timedelta(hours=24)).date()
    test_booking.booking_start_utc = now + timedelta(hours=24) - timedelta(minutes=10)
    test_booking.reminder_24h_sent = False
    db.commit()

    with patch(
        "app.tasks.notification_tasks.NotificationService.notify_user",
        new=AsyncMock(side_effect=RuntimeError("sms failed")),
    ):
        result = send_booking_reminders()

    db.refresh(test_booking)
    assert result["reminders_24h_sent"] == 0
    assert test_booking.reminder_24h_sent is False
