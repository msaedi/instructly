from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from sqlalchemy.orm import sessionmaker

from app.models.event_outbox import EventOutbox, EventOutboxStatus, NotificationDelivery
from app.repositories.event_outbox_repository import EventOutboxRepository
from app.tasks.notification_tasks import deliver_event


def test_concurrent_enqueue_is_deduplicated(db) -> None:
    session_factory = sessionmaker(bind=db.bind, autoflush=False, autocommit=False)
    key = "booking:dedupe-test:booking.created:2025-01-01T00:00:00Z"

    def worker() -> None:
        session = session_factory()
        try:
            repo = EventOutboxRepository(session)
            repo.enqueue(
                event_type="booking.created",
                aggregate_id="dedupe-test",
                payload={"booking_id": "dedupe-test"},
                idempotency_key=key,
            )
            session.commit()
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(worker) for _ in range(4)]
        for future in futures:
            future.result()

    rows = db.query(EventOutbox).filter(EventOutbox.idempotency_key == key).all()
    assert len(rows) == 1

    deliver_event.run(rows[0].id)
    db.refresh(rows[0])
    assert rows[0].status == EventOutboxStatus.SENT.value

    deliveries = (
        db.query(NotificationDelivery)
        .filter(NotificationDelivery.idempotency_key == key)
        .all()
    )
    assert len(deliveries) == 1
