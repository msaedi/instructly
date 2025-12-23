# backend/app/tasks/notification_tasks.py
"""
Celery tasks for dispatching notification outbox events.

Implements a two-step workflow:
1. `outbox.dispatch_pending` periodically enqueues delivery tasks.
2. `outbox.deliver_event` performs delivery with retries and backoff.
"""

from __future__ import annotations

from contextlib import contextmanager
from time import monotonic
from typing import Any, Iterator, Optional, cast

from celery.app.task import Task  # noqa: F401 - used for type hints
from celery.utils.log import get_task_logger
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.monitoring.prometheus_metrics import PrometheusMetrics
from app.repositories.event_outbox_repository import EventOutboxRepository
from app.services.notification_provider import (
    NotificationProvider,
    NotificationProviderTemporaryError,
)
from app.tasks.celery_app import celery_app

logger = get_task_logger(__name__)

MAX_DELIVERY_ATTEMPTS = 5
BACKOFF_SECONDS = [30, 120, 600, 1800, 7200]


def _next_backoff(attempt_number: int) -> int:
    """Return backoff delay for the given attempt (1-indexed)."""
    index = max(0, min(attempt_number - 1, len(BACKOFF_SECONDS) - 1))
    return BACKOFF_SECONDS[index]


@contextmanager
def _session_scope() -> Iterator[Session]:
    """Provide transactional scope for use in tasks."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@celery_app.task(name="outbox.dispatch_pending", max_retries=0, queue="notifications")
def dispatch_pending() -> int:
    """
    Fetch pending outbox events and enqueue delivery tasks.

    Returns the number of events scheduled.
    """
    with _session_scope() as session:
        repo = EventOutboxRepository(session)
        pending = repo.fetch_pending(limit=200)
        for event in pending:
            deliver_event.apply_async((event.id,), queue="notifications")
        scheduled: int = len(pending)
        if scheduled:
            logger.info("Scheduled %s outbox events for delivery", scheduled)
        return scheduled


@celery_app.task(
    name="outbox.deliver_event",
    bind=True,
    max_retries=5,
    default_retry_delay=30,
    queue="notifications",
)
def deliver_event(self: "Task[Any, Any]", event_id: str) -> Optional[str]:
    """Deliver a single outbox event."""
    provider = NotificationProvider()
    session = SessionLocal()
    attempt_number = 0
    start: Optional[float] = None

    try:
        repo = EventOutboxRepository(session)
        event = repo.get_by_id(event_id, for_update=False)
        if event is None:
            logger.warning("Outbox event %s missing; skipping", event_id)
            session.commit()
            return None

        attempt_number = event.attempt_count + 1
        PrometheusMetrics.record_notification_attempt(event.event_type)

        try:
            start = monotonic()
            provider.send(
                event_type=event.event_type,
                payload=event.payload,
                idempotency_key=event.idempotency_key,
            )
            duration = (monotonic() - start) if start is not None else 0.0
            repo.mark_sent(event.id, attempt_number)
            session.commit()
            PrometheusMetrics.observe_notification_dispatch(event.event_type, duration)
            PrometheusMetrics.record_notification_outcome(event.event_type, "sent")
            logger.info(
                "Delivered outbox event %s type=%s attempts=%s",
                event.id,
                event.event_type,
                attempt_number,
            )
            return cast(str, event.id)
        except NotificationProviderTemporaryError as exc:
            duration = (monotonic() - start) if start is not None else 0.0
            PrometheusMetrics.observe_notification_dispatch(event.event_type, duration)
            backoff = _next_backoff(attempt_number)
            terminal = attempt_number >= MAX_DELIVERY_ATTEMPTS
            repo.mark_failed(
                event.id,
                attempt_count=attempt_number,
                backoff_seconds=backoff,
                error=str(exc),
                terminal=terminal,
            )
            session.commit()
            if terminal:
                PrometheusMetrics.record_notification_outcome(event.event_type, "failed")
                logger.error(
                    "Outbox event %s failed after %s attempts",
                    event.id,
                    attempt_number,
                )
                raise
            logger.warning(
                "Retrying outbox event %s attempt=%s backoff=%ss",
                event.id,
                attempt_number,
                backoff,
            )
            raise self.retry(countdown=backoff, exc=exc)
        except Exception as exc:
            duration = (monotonic() - start) if start is not None else 0.0
            PrometheusMetrics.observe_notification_dispatch(event.event_type, duration)
            backoff = _next_backoff(attempt_number)
            terminal = attempt_number >= MAX_DELIVERY_ATTEMPTS
            repo.mark_failed(
                event.id,
                attempt_count=attempt_number,
                backoff_seconds=backoff,
                error=str(exc),
                terminal=terminal,
            )
            session.commit()
            if terminal:
                PrometheusMetrics.record_notification_outcome(event.event_type, "failed")
                logger.exception(
                    "Outbox event %s failed permanently after %s attempts",
                    event.id,
                    attempt_number,
                )
                raise
            logger.exception(
                "Error delivering outbox event %s; retrying in %ss",
                event.id,
                backoff,
            )
            raise self.retry(countdown=backoff, exc=exc)
    finally:
        session.close()
