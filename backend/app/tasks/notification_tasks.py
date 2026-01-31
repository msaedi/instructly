# backend/app/tasks/notification_tasks.py
"""
Celery tasks for dispatching notification outbox events.

Implements a two-step workflow:
1. `outbox.dispatch_pending` periodically enqueues delivery tasks.
2. `outbox.deliver_event` performs delivery with retries and backoff.
"""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta, timezone
from time import monotonic
from typing import Any, Iterator, Optional, cast

from celery.app.task import Task  # noqa: F401 - used for type hints
from celery.utils.log import get_task_logger
from sqlalchemy.orm import Session, joinedload

from app.core.request_context import with_request_id_header
from app.database import SessionLocal
from app.models.booking import Booking, BookingStatus
from app.monitoring.prometheus_metrics import PrometheusMetrics
from app.repositories.event_outbox_repository import EventOutboxRepository
from app.services.notification_provider import (
    NotificationProvider,
    NotificationProviderTemporaryError,
)
from app.services.notification_service import NotificationService
from app.services.notification_templates import (
    INSTRUCTOR_REMINDER_1H,
    INSTRUCTOR_REMINDER_24H,
    STUDENT_REMINDER_1H,
    STUDENT_REMINDER_24H,
    NotificationTemplate,
)
from app.services.sms_templates import REMINDER_1H, REMINDER_24H, SMSTemplate
from app.tasks.celery_app import typed_task

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


@typed_task(name="outbox.dispatch_pending", max_retries=0, queue="notifications")
def dispatch_pending() -> int:
    """
    Fetch pending outbox events and enqueue delivery tasks.

    Returns the number of events scheduled.
    """
    with _session_scope() as session:
        repo = EventOutboxRepository(session)
        pending = repo.fetch_pending(limit=200)
        for event in pending:
            deliver_event.apply_async(
                (event.id,),
                queue="notifications",
                headers=with_request_id_header(),
            )
        scheduled: int = len(pending)
        if scheduled:
            logger.info("Scheduled %s outbox events for delivery", scheduled)
        return scheduled


@typed_task(
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


def _format_display_name(user: Any) -> str:
    first = (getattr(user, "first_name", "") or "").strip() if user else ""
    last = (getattr(user, "last_name", "") or "").strip() if user else ""
    if first and last:
        return f"{first} {last[0]}."
    return first or "Someone"


def _format_booking_date(booking: Booking) -> str:
    booking_date = getattr(booking, "booking_date", None)
    if isinstance(booking_date, date):
        return booking_date.strftime("%B %d").replace(" 0", " ")
    return str(booking_date or "")


def _format_booking_time(booking: Booking) -> str:
    start_time = getattr(booking, "start_time", None)
    if isinstance(start_time, time):
        return start_time.strftime("%I:%M %p").lstrip("0")
    if start_time:
        return str(start_time)
    return ""


def _resolve_service_name(booking: Booking) -> str:
    name = getattr(booking, "service_name", None)
    if isinstance(name, str) and name.strip():
        return name.strip()
    service = getattr(booking, "instructor_service", None)
    service_name = getattr(service, "name", None)
    if isinstance(service_name, str) and service_name.strip():
        return service_name.strip()
    return "Lesson"


def _send_reminder_notifications(
    service: NotificationService,
    booking: Booking,
    instructor_template: NotificationTemplate,
    student_template: NotificationTemplate,
    sms_template: SMSTemplate,
) -> bool:
    student_name = _format_display_name(getattr(booking, "student", None))
    instructor_name = _format_display_name(getattr(booking, "instructor", None))
    service_name = _resolve_service_name(booking)
    date_str = _format_booking_date(booking)
    time_str = _format_booking_time(booking)

    async def _notify() -> None:
        await service.notify_user(
            user_id=booking.instructor_id,
            template=instructor_template,
            student_name=student_name,
            service_name=service_name,
            date=date_str,
            time=time_str,
            booking_id=booking.id,
            send_email=False,
            send_sms=True,
            sms_template=sms_template,
            other_party_name=student_name,
        )
        await service.notify_user(
            user_id=booking.student_id,
            template=student_template,
            instructor_name=instructor_name,
            service_name=service_name,
            date=date_str,
            time=time_str,
            booking_id=booking.id,
            send_email=False,
            send_sms=True,
            sms_template=sms_template,
            other_party_name=instructor_name,
        )

    try:
        asyncio.run(_notify())
    except Exception as exc:
        logger.warning(
            "Failed reminder notifications for booking %s: %s",
            booking.id,
            exc,
        )
        return False
    return True


@typed_task(name="app.tasks.notification_tasks.send_booking_reminders", queue="notifications")
def send_booking_reminders() -> dict[str, int]:
    """
    Send reminder notifications for upcoming bookings.
    Runs every 15 minutes via Celery Beat.
    """
    now = datetime.now(timezone.utc)

    reminder_24h_start = now + timedelta(hours=24) - timedelta(minutes=15)
    reminder_24h_end = now + timedelta(hours=24)
    reminder_1h_start = now + timedelta(hours=1) - timedelta(minutes=15)
    reminder_1h_end = now + timedelta(hours=1)

    reminders_24h = 0
    reminders_1h = 0

    with _session_scope() as session:
        service = NotificationService(session)
        bookings_24h = (
            session.query(Booking)
            .options(
                joinedload(Booking.student),
                joinedload(Booking.instructor),
                joinedload(Booking.instructor_service),
            )
            .filter(
                Booking.status == BookingStatus.CONFIRMED,
                Booking.booking_start_utc >= reminder_24h_start,
                Booking.booking_start_utc < reminder_24h_end,
                Booking.reminder_24h_sent.is_(False),
            )
            .all()
        )

        for booking in bookings_24h:
            success = _send_reminder_notifications(
                service,
                booking,
                INSTRUCTOR_REMINDER_24H,
                STUDENT_REMINDER_24H,
                REMINDER_24H,
            )
            if success:
                reminders_24h += 2
                booking.reminder_24h_sent = True

        bookings_1h = (
            session.query(Booking)
            .options(
                joinedload(Booking.student),
                joinedload(Booking.instructor),
                joinedload(Booking.instructor_service),
            )
            .filter(
                Booking.status == BookingStatus.CONFIRMED,
                Booking.booking_start_utc >= reminder_1h_start,
                Booking.booking_start_utc < reminder_1h_end,
                Booking.reminder_1h_sent.is_(False),
            )
            .all()
        )

        for booking in bookings_1h:
            success = _send_reminder_notifications(
                service,
                booking,
                INSTRUCTOR_REMINDER_1H,
                STUDENT_REMINDER_1H,
                REMINDER_1H,
            )
            if success:
                reminders_1h += 2
                booking.reminder_1h_sent = True

    return {
        "reminders_24h_sent": reminders_24h,
        "reminders_1h_sent": reminders_1h,
    }
