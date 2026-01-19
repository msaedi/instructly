from __future__ import annotations

from datetime import datetime, timezone

from app.models.event_outbox import EventOutbox, EventOutboxStatus, NotificationDelivery


def test_event_outbox_markers() -> None:
    event = EventOutbox(
        event_type="test",
        aggregate_id="agg",
        idempotency_key="key",
        payload={},
    )

    next_attempt = datetime.now(timezone.utc)
    event.mark_pending(next_attempt, attempt_count=2)
    assert event.status == EventOutboxStatus.PENDING.value
    assert event.attempt_count == 2
    assert event.next_attempt_at == next_attempt

    event.mark_sent(attempt_count=3)
    assert event.status == EventOutboxStatus.SENT.value
    assert event.attempt_count == 3

    event.mark_failed(attempt_count=4, error="x" * 2000)
    assert event.status == EventOutboxStatus.FAILED.value
    assert event.attempt_count == 4
    assert event.last_error is not None
    assert len(event.last_error) == 1000


def test_notification_delivery_touch_updates_payload() -> None:
    delivery = NotificationDelivery(
        event_type="evt",
        idempotency_key="key",
        payload={"a": 1},
        attempt_count=1,
    )

    delivery.touch(payload={"b": 2})

    assert delivery.attempt_count == 2
    assert delivery.payload == {"b": 2}
