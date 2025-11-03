# backend/app/services/notification_provider.py
"""
Notification provider shim used by the outbox dispatcher.

This component simulates delivery to an external provider while enforcing
idempotency via the notification_delivery table. A test-only environment flag
(`NOTIFICATION_PROVIDER_RAISE_ON`) can be used to trigger transient failures.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timezone
import json
import logging
import os
from typing import Any, Callable, Dict, Generator, Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.database import SessionLocal
from app.monitoring.prometheus_metrics import PrometheusMetrics
from app.repositories.notification_delivery_repository import NotificationDeliveryRepository

logger = logging.getLogger(__name__)


class NotificationProviderTemporaryError(RuntimeError):
    """Exception raised to simulate transient provider failures."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _should_raise(event_type: str, idempotency_key: str) -> bool:
    """Determine whether to simulate a provider failure."""
    raw = os.getenv("NOTIFICATION_PROVIDER_RAISE_ON")
    if not raw:
        return False

    tokens = {token.strip() for token in raw.split(",") if token.strip()}
    if not tokens:
        return False

    return (
        "*" in tokens
        or event_type in tokens
        or idempotency_key in tokens
        or any(token and token in idempotency_key for token in tokens if len(token) > 4)
    )


@contextmanager
def _managed_session(session_factory: Callable[[], Session]) -> Generator[Session, None, None]:
    """Context manager that yields a session and guarantees cleanup."""
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@dataclass(slots=True)
class NotificationDispatchResult:
    """Metadata describing a simulated provider send."""

    idempotency_key: str
    event_type: str
    attempt_count: int
    stored_payload: Dict[str, Any]


class NotificationProvider:
    """
    Lightweight provider shim that writes to notification_delivery.

    Usage:
        provider = NotificationProvider()
        provider.send(event_type="booking.created", payload={...}, idempotency_key="...")
    """

    def __init__(self, session_factory: Callable[[], Session] | None = None) -> None:
        self._session_factory = session_factory or SessionLocal

    def send(
        self,
        event_type: str,
        payload: Optional[Dict[str, Any]] = None,
        idempotency_key: Optional[str] = None,
    ) -> NotificationDispatchResult:
        """Simulate sending a notification message."""
        if not idempotency_key:
            raise ValueError("idempotency_key is required for notification dispatch")

        if _should_raise(event_type, idempotency_key):
            logger.warning(
                "Simulating provider failure for %s (%s)",
                event_type,
                idempotency_key,
            )
            raise NotificationProviderTemporaryError(
                f"Simulated transient failure for {event_type}"
            )

        payload = payload or {}
        logger.info(
            "Dispatching notification %s key=%s payload=%s",
            event_type,
            idempotency_key,
            json.dumps(payload, sort_keys=True)[:500],
        )

        if (
            settings.suppress_past_availability_events
            and event_type.startswith("availability.")
            and self._payload_contains_past_date(payload)
        ):
            PrometheusMetrics.record_availability_event_suppressed("past_date")
            logger.info(
                "Suppressing availability notification for past-only dates",
                extra={"event_type": event_type, "idempotency_key": idempotency_key},
            )
            return NotificationDispatchResult(
                idempotency_key=idempotency_key,
                event_type=event_type,
                attempt_count=0,
                stored_payload=dict(payload),
            )

        with _managed_session(self._session_factory) as session:
            repo = NotificationDeliveryRepository(session)
            record = repo.record_delivery(event_type, idempotency_key, payload)
            logger.debug(
                "Notification delivery recorded id=%s attempts=%s",
                record.id,
                record.attempt_count,
            )
            return NotificationDispatchResult(
                idempotency_key=idempotency_key,
                event_type=event_type,
                attempt_count=record.attempt_count,
                stored_payload=dict(record.payload or {}),
            )

    @staticmethod
    def _payload_contains_past_date(payload: Dict[str, Any]) -> bool:
        """Detect if a notification payload references only past dates."""
        today = datetime.now(timezone.utc).date()
        candidate_keys = (
            "affected_dates",
            "dates",
            "edited_dates",
            "written_dates",
            "skipped_dates",
        )
        dates: list[date] = []
        for key in candidate_keys:
            value = payload.get(key)
            if not isinstance(value, list):
                continue
            for item in value:
                try:
                    parsed = date.fromisoformat(str(item))
                except (TypeError, ValueError):
                    continue
                dates.append(parsed)
        if not dates:
            return False
        return all(candidate < today for candidate in dates)
