from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.models.event_outbox import EventOutbox, EventOutboxStatus, NotificationDelivery
from app.monitoring.prometheus_metrics import (
    notifications_outbox_attempt_total,
    notifications_outbox_total,
)
from app.schemas.availability_window import WeekSpecificScheduleCreate
from app.services.availability_service import AvailabilityService
from app.services.week_operation_service import WeekOperationService
from app.tasks.notification_tasks import deliver_event


@pytest.fixture(autouse=True)
def _notif_sync(monkeypatch):
    """Ensure availability events are not suppressed and are processed synchronously."""
    from app.core.config import settings

    # ensure availability events are not suppressed and are processed synchronously
    monkeypatch.setenv("SUPPRESS_PAST_AVAILABILITY_EVENTS", "0", prepend=False)
    monkeypatch.setenv("NOTIFICATIONS_SYNC_DELIVERY", "1", prepend=False)

    # Also patch settings directly to ensure it takes effect immediately
    monkeypatch.setattr(settings, "suppress_past_availability_events", False, raising=False)


def _future_monday(weeks_ahead: int = 1) -> date:
    today = date.today()
    days_until_monday = (7 - today.weekday()) % 7
    base = today + timedelta(days=days_until_monday)
    if base <= today:
        base += timedelta(days=7)
    return base + timedelta(weeks=weeks_ahead - 1)


def _latest_outbox(db, event_type: str) -> EventOutbox:
    return (
        db.query(EventOutbox)
        .filter(EventOutbox.event_type == event_type)
        .order_by(EventOutbox.id.desc())
        .first()
    )


@pytest.mark.asyncio
async def test_save_week_availability_emits_outbox(
    db,
    test_instructor_with_availability,
):
    availability_service = AvailabilityService(db)
    week_start = _future_monday()
    schedule = [
        {
            "date": week_start.isoformat(),
            "start_time": "09:00",
            "end_time": "10:00",
        },
        {
            "date": (week_start + timedelta(days=2)).isoformat(),
            "start_time": "14:00",
            "end_time": "15:00",
        },
    ]
    week_data = WeekSpecificScheduleCreate(
        schedule=schedule,
        clear_existing=True,
        week_start=week_start,
    )

    await availability_service.save_week_availability(test_instructor_with_availability.id, week_data)

    # Commit the transaction so the outbox event is visible to deliver_event.run()
    db.commit()

    outbox_row = _latest_outbox(db, "availability.week_saved")
    assert outbox_row is not None

    attempt_counter = notifications_outbox_attempt_total.labels(event_type="availability.week_saved")
    sent_counter = notifications_outbox_total.labels(status="sent", event_type="availability.week_saved")
    before_attempts = attempt_counter._value.get()
    before_sent = sent_counter._value.get()

    deliver_event.run(outbox_row.id)
    db.refresh(outbox_row)
    assert outbox_row.status == EventOutboxStatus.SENT.value
    assert attempt_counter._value.get() == before_attempts + 1
    assert sent_counter._value.get() == before_sent + 1

    deliveries = (
        db.query(NotificationDelivery)
        .filter(NotificationDelivery.idempotency_key == outbox_row.idempotency_key)
        .all()
    )
    assert len(deliveries) == 1


@pytest.mark.asyncio
async def test_copy_week_availability_emits_outbox(
    db,
    test_instructor_with_availability,
):
    availability_service = AvailabilityService(db)
    week_service = WeekOperationService(db)
    source_monday = _future_monday()

    # Ensure source week has data
    week_data = WeekSpecificScheduleCreate(
        schedule=[
            {
                "date": source_monday.isoformat(),
                "start_time": "09:00",
                "end_time": "10:00",
            }
        ],
        clear_existing=True,
        week_start=source_monday,
    )
    await availability_service.save_week_availability(test_instructor_with_availability.id, week_data)

    target_monday = source_monday + timedelta(weeks=1)
    await week_service.copy_week_availability(
        test_instructor_with_availability.id,
        from_week_start=source_monday,
        to_week_start=target_monday,
    )

    outbox_row = _latest_outbox(db, "availability.week_copied")
    assert outbox_row is not None

    attempt_counter = notifications_outbox_attempt_total.labels(event_type="availability.week_copied")
    sent_counter = notifications_outbox_total.labels(status="sent", event_type="availability.week_copied")
    before_attempts = attempt_counter._value.get()
    before_sent = sent_counter._value.get()

    deliver_event.run(outbox_row.id)
    db.refresh(outbox_row)
    assert outbox_row.status == EventOutboxStatus.SENT.value
    assert attempt_counter._value.get() == before_attempts + 1
    assert sent_counter._value.get() == before_sent + 1

    deliveries = (
        db.query(NotificationDelivery)
        .filter(NotificationDelivery.idempotency_key == outbox_row.idempotency_key)
        .all()
    )
    assert len(deliveries) == 1
