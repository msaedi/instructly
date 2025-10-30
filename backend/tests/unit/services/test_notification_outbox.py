from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import sessionmaker

from app.models.event_outbox import EventOutbox, EventOutboxStatus, NotificationDelivery
from app.repositories.event_outbox_repository import EventOutboxRepository
from app.services.notification_provider import NotificationProvider


def _basic_payload() -> dict[str, str]:
    return {
        "booking_id": "booking-123",
        "status": "CONFIRMED",
    }


def test_enqueue_is_idempotent(db) -> None:
    repo = EventOutboxRepository(db)
    key = "booking:booking-123:booking.created:2025-01-01T00:00:00Z"

    repo.enqueue(
        event_type="booking.created",
        aggregate_id="booking-123",
        payload=_basic_payload(),
        idempotency_key=key,
    )
    repo.enqueue(
        event_type="booking.created",
        aggregate_id="booking-123",
        payload=_basic_payload(),
        idempotency_key=key,
    )
    db.commit()

    rows = db.query(EventOutbox).all()
    assert len(rows) == 1
    assert rows[0].idempotency_key == key


def test_mark_failed_updates_next_attempt(db) -> None:
    repo = EventOutboxRepository(db)
    event = repo.enqueue(
        event_type="booking.cancelled",
        aggregate_id="booking-321",
        payload=_basic_payload(),
        idempotency_key="booking:booking-321:booking.cancelled:2025-01-01T00:00:00Z",
    )
    db.commit()

    before = event.next_attempt_at

    repo.mark_failed(
        event.id,
        attempt_count=1,
        backoff_seconds=120,
        error="transient failure",
        terminal=False,
    )
    db.commit()
    refreshed = repo.get_by_id(event.id)
    assert refreshed is not None
    assert refreshed.attempt_count == 1
    assert refreshed.status == EventOutboxStatus.PENDING.value
    assert refreshed.next_attempt_at > before
    delta = refreshed.next_attempt_at - datetime.now(timezone.utc)
    assert delta.total_seconds() >= 100  # allow some processing delay


def test_notification_provider_enforces_idempotency(db) -> None:
    session_factory = sessionmaker(bind=db.bind, autoflush=False, autocommit=False)
    provider = NotificationProvider(session_factory=session_factory)

    key = "booking:booking-456:booking.created:2025-01-01T00:00:00Z"
    provider.send("booking.created", {"booking_id": "booking-456"}, key)
    provider.send("booking.created", {"booking_id": "booking-456"}, key)

    db.commit()
    deliveries = db.query(NotificationDelivery).all()
    assert len(deliveries) == 1
    assert deliveries[0].idempotency_key == key
