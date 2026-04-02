"""Shared infrastructure for payment tasks."""

from __future__ import annotations

from datetime import datetime
import logging
from typing import (
    Any,
    Callable,
    Dict,
    List,
    ParamSpec,
    Protocol,
    Sequence,
    TypedDict,
    TypeVar,
    Union,
    cast,
)

from celery.result import AsyncResult
from sqlalchemy.orm import Session
import stripe

from app.core.config import settings
from app.models.booking import Booking
from app.models.payment import PaymentEvent
from app.tasks.celery_app import celery_app

P = ParamSpec("P")
R = TypeVar("R", covariant=True)


class TaskWrapper(Protocol[P, R]):
    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R:
        ...

    delay: "Callable[..., AsyncResult[Any]]"
    apply_async: "Callable[..., AsyncResult[Any]]"


def typed_task(
    *task_args: Any,
    **task_kwargs: Any,
) -> Callable[[Callable[P, R]], TaskWrapper[P, R]]:
    """Return a typed Celery task decorator for mypy."""

    return cast(
        Callable[[Callable[P, R]], TaskWrapper[P, R]],
        celery_app.task(*task_args, **task_kwargs),
    )


class AuthorizationJobResults(TypedDict):
    success: int
    failed: int
    failures: List[Dict[str, Any]]
    processed_at: str


class RetryJobResults(TypedDict):
    retried: int
    success: int
    failed: int
    cancelled: int
    warnings_sent: int
    processed_at: str


class CaptureJobResults(TypedDict):
    captured: int
    failed: int
    auto_completed: int
    expired_handled: int
    processed_at: str


class CaptureRetryResults(TypedDict):
    retried: int
    succeeded: int
    escalated: int
    skipped: int
    processed_at: str


class NoShowResolutionResults(TypedDict):
    resolved: int
    skipped: int
    failed: int
    processed_at: str


logger = logging.getLogger("app.tasks.payment_tasks")
stripe.api_key = (
    settings.stripe_secret_key.get_secret_value() if settings.stripe_secret_key else None
)
logger.info(
    "Stripe SDK %s, API version %s",
    getattr(stripe, "VERSION", "unknown"),
    getattr(stripe, "api_version", "unknown"),
)
STRIPE_CURRENCY = settings.stripe_currency if hasattr(settings, "stripe_currency") else "usd"


class PaymentTasksFacadeApi(Protocol):
    BookingRepository: Any
    BookingService: Any
    ConfigService: Any
    NotificationService: Any
    PricingService: Any
    RepositoryFactory: Any
    StripeService: Any
    StudentCreditService: Any
    TimezoneService: Any
    booking_lock_sync: Any
    datetime: Any
    get_db: Any
    logger: Any
    stripe: Any

    def _auto_complete_booking(self, booking_id: str, now: datetime) -> Dict[str, Any]:
        ...

    def _mark_booking_payment_failed(
        self,
        booking_id: str,
        hours_until_lesson: float,
        now: datetime,
    ) -> bool:
        ...

    def _escalate_capture_failure(self, booking_id: str, now: datetime) -> None:
        ...

    def _get_booking_end_utc(self, booking: Booking) -> datetime:
        ...

    def _get_booking_start_utc(self, booking: Booking) -> datetime:
        ...

    def _process_authorization_for_booking(
        self,
        booking_id: str,
        hours_until_lesson: float,
    ) -> Dict[str, Any]:
        ...

    def _process_capture_for_booking(
        self,
        booking_id: str,
        capture_reason: str,
    ) -> Dict[str, Any]:
        ...

    def _process_retry_authorization(
        self,
        booking_id: str,
        hours_until_lesson: float,
    ) -> Dict[str, Any]:
        ...

    def _resolve_locked_booking_from_task(
        self,
        locked_booking_id: str,
        resolution: str,
    ) -> Dict[str, Any]:
        ...

    def _mark_child_booking_settled(self, booking_id: str) -> None:
        ...

    def _should_retry_auth(self, booking: Booking, now: datetime) -> bool:
        ...

    def _should_retry_capture(self, booking: Booking, now: datetime) -> bool:
        ...

    def create_new_authorization_and_capture(
        self,
        booking: Booking,
        payment_repo: Any,
        db: Session,
        *,
        lock_acquired: bool = False,
    ) -> Dict[str, Any]:
        ...

    def has_event_type(
        self,
        payment_repo: Any,
        booking_id: Union[int, str],
        event_type: str,
    ) -> bool:
        ...


def _get_booking_start_utc(booking: Booking) -> datetime:
    """Get booking start time in UTC."""
    if booking.booking_start_utc is None:
        raise ValueError(f"Booking {booking.id} missing booking_start_utc")
    return cast(datetime, booking.booking_start_utc)


def _get_booking_end_utc(booking: Booking) -> datetime:
    """Get booking end time in UTC."""
    if booking.booking_end_utc is None:
        raise ValueError(f"Booking {booking.id} missing booking_end_utc")
    return cast(datetime, booking.booking_end_utc)


def _should_retry_auth(booking: Booking, now: datetime) -> bool:
    """Determine if a failed authorization should be retried."""
    pd = booking.payment_detail
    attempted_at = getattr(pd, "auth_attempted_at", None)
    if not isinstance(attempted_at, datetime):
        return True
    hours_since_attempt = (now - attempted_at).total_seconds() / 3600
    failure_count = int(getattr(pd, "auth_failure_count", 0) or 0)
    if failure_count <= 1:
        required_wait = 1
    elif failure_count == 2:
        required_wait = 4
    else:
        required_wait = 8
    return hours_since_attempt >= required_wait


def _should_retry_capture(booking: Booking, now: datetime) -> bool:
    """Return True if enough time has passed since the last capture failure."""
    pd = booking.payment_detail
    failed_at = getattr(pd, "capture_failed_at", None)
    if not isinstance(failed_at, datetime):
        return False
    return (now - failed_at).total_seconds() / 3600 >= 4


def has_event_type(payment_repo: Any, booking_id: Union[int, str], event_type: str) -> bool:
    """Check if a booking has a specific event type in its history."""
    events = cast(
        Sequence[PaymentEvent],
        payment_repo.get_payment_events_for_booking(booking_id),
    )
    return any(event.event_type == event_type for event in events)


def resolve_locked_booking_from_task_impl(
    api: PaymentTasksFacadeApi,
    locked_booking_id: str,
    resolution: str,
) -> Dict[str, Any]:
    """Resolve a LOCKed booking from a task context."""
    from app.database import SessionLocal

    db: Session = SessionLocal()
    try:
        result = api.BookingService(db).resolve_lock_for_booking(locked_booking_id, resolution)
        db.commit()
        return cast(Dict[str, Any], result)
    finally:
        db.close()


def mark_child_booking_settled_impl(
    api: PaymentTasksFacadeApi,
    booking_id: str,
) -> None:
    """Mark a rescheduled booking as settled after lock resolution."""
    from app.database import SessionLocal
    from app.models.booking import PaymentStatus

    db: Session = SessionLocal()
    try:
        booking_repo = api.BookingRepository(db)
        booking = booking_repo.get_by_id(booking_id)
        if booking:
            booking_repo.ensure_payment(booking.id).payment_status = PaymentStatus.SETTLED.value
            db.commit()
    finally:
        db.close()
