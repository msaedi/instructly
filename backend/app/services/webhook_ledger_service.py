"""Service for logging and replaying webhooks."""

from __future__ import annotations

from datetime import datetime, timezone
import time
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import RepositoryException
from app.models.webhook_event import WebhookEvent
from app.repositories.webhook_event_repository import WebhookEventRepository
from app.services.base import BaseService

_SENSITIVE_HEADERS = {
    "authorization",
    "stripe-signature",
    "x-api-key",
    "x-hundredms-secret",
}


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


class WebhookLedgerService(BaseService):
    """Business logic for webhook ledger entries."""

    def __init__(self, db: Session) -> None:
        super().__init__(db)
        self.repository = WebhookEventRepository(db)

    def _find_existing_event(
        self,
        *,
        source: str,
        event_id: str | None,
        idempotency_key: str | None,
    ) -> WebhookEvent | None:
        if event_id:
            existing = self.repository.find_by_source_and_event_id(source, event_id)
            if existing is not None:
                return existing
        if idempotency_key:
            return self.repository.find_by_source_and_idempotency_key(source, idempotency_key)
        return None

    @BaseService.measure_operation("webhook_ledger.log_received")
    def log_received(
        self,
        *,
        source: str,
        event_type: str,
        payload: dict[str, Any],
        headers: dict[str, Any] | None = None,
        event_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> WebhookEvent:
        """
        Log a received webhook before processing.

        Handles retries gracefully by updating retry tracking when a duplicate event_id is received.
        """
        safe_headers = self._sanitize_headers(headers) if headers else None
        now = _now_utc()
        existing = self._find_existing_event(
            source=source,
            event_id=event_id,
            idempotency_key=idempotency_key,
        )

        if existing:
            existing.retry_count = (existing.retry_count or 0) + 1
            existing.last_retry_at = now
            if safe_headers is not None:
                existing.headers = safe_headers
            self.repository.flush()
            return existing

        try:
            return self.repository.create(
                source=source,
                event_type=event_type or "unknown",
                event_id=event_id,
                payload=payload,
                headers=safe_headers,
                status="received",
                idempotency_key=idempotency_key,
                received_at=now,
                retry_count=0,
            )
        except RepositoryException as exc:
            # Race-safe fallback: DB uniqueness won in another worker.
            if isinstance(exc.__cause__, IntegrityError):
                existing = self._find_existing_event(
                    source=source,
                    event_id=event_id,
                    idempotency_key=idempotency_key,
                )
                if existing is not None:
                    existing.retry_count = (existing.retry_count or 0) + 1
                    existing.last_retry_at = now
                    if safe_headers is not None:
                        existing.headers = safe_headers
                    self.repository.flush()
                    return existing
            raise

    @BaseService.measure_operation("webhook_ledger.mark_processing")
    def mark_processing(self, event: WebhookEvent) -> bool:
        """Attempt to claim an event for processing."""
        claimed = self.repository.claim_for_processing(event.id)
        if claimed:
            event.status = "processing"
            event.processing_error = None
            event.processed_at = None
        return claimed

    @BaseService.measure_operation("webhook_ledger.mark_processed")
    def mark_processed(
        self,
        event: WebhookEvent,
        *,
        related_entity_type: str | None = None,
        related_entity_id: str | None = None,
        duration_ms: int | None = None,
        status: str = "processed",
    ) -> WebhookEvent:
        """Mark webhook as successfully processed."""
        event.status = status
        event.processed_at = _now_utc()
        event.related_entity_type = related_entity_type
        event.related_entity_id = related_entity_id
        event.processing_duration_ms = duration_ms
        self.repository.flush()
        return event

    @BaseService.measure_operation("webhook_ledger.mark_failed")
    def mark_failed(
        self,
        event: WebhookEvent,
        *,
        error: str,
        duration_ms: int | None = None,
        status: str = "failed",
    ) -> WebhookEvent:
        """Mark webhook as failed."""
        event.status = status
        event.processing_error = error
        event.processed_at = _now_utc()
        event.processing_duration_ms = duration_ms
        self.repository.flush()
        return event

    @BaseService.measure_operation("webhook_ledger.list_events")
    def list_events(
        self,
        *,
        source: str | None = None,
        status: str | None = None,
        event_type: str | None = None,
        since_hours: int = 24,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 50,
    ) -> list[WebhookEvent]:
        """Return recent webhook events filtered by criteria."""
        return self.repository.list_events(
            source=source,
            status=status,
            event_type=event_type,
            since_hours=since_hours,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
        )

    @BaseService.measure_operation("webhook_ledger.count_events")
    def count_events(
        self,
        *,
        since_hours: int = 24,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> int:
        return self.repository.count_events(
            since_hours=since_hours,
            start_time=start_time,
            end_time=end_time,
        )

    @BaseService.measure_operation("webhook_ledger.summarize_by_status")
    def summarize_by_status(
        self,
        *,
        since_hours: int = 24,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> dict[str, int]:
        return self.repository.summarize_by_status(
            since_hours=since_hours,
            start_time=start_time,
            end_time=end_time,
        )

    @BaseService.measure_operation("webhook_ledger.summarize_by_source")
    def summarize_by_source(
        self,
        *,
        since_hours: int = 24,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> dict[str, int]:
        return self.repository.summarize_by_source(
            since_hours=since_hours,
            start_time=start_time,
            end_time=end_time,
        )

    @BaseService.measure_operation("webhook_ledger.get_event")
    def get_event(self, event_id: str) -> WebhookEvent | None:
        return self.repository.get_event(event_id)

    @BaseService.measure_operation("webhook_ledger.get_failed_events")
    def get_failed_events(
        self,
        *,
        source: str | None = None,
        since_hours: int = 24,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 50,
    ) -> list[WebhookEvent]:
        return self.repository.get_failed_events(
            source=source,
            since_hours=since_hours,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
        )

    @BaseService.measure_operation("webhook_ledger.create_replay")
    def create_replay(self, event: WebhookEvent) -> WebhookEvent:
        next_count = (event.replay_count or 0) + 1
        event.replay_count = next_count
        return self.repository.create(
            source=event.source,
            event_type=event.event_type,
            event_id=None,
            payload=event.payload,
            headers=event.headers,
            status="received",
            idempotency_key=f"replay_{event.id}_{next_count}",
            received_at=_now_utc(),
            replay_of=event.id,
            replay_count=0,
        )

    def _sanitize_headers(self, headers: dict[str, Any]) -> dict[str, Any]:
        return {
            key: ("***" if key.lower() in _SENSITIVE_HEADERS else value)
            for key, value in headers.items()
        }

    @BaseService.measure_operation("webhook_ledger.elapsed_ms")
    def elapsed_ms(self, start: float) -> int:
        return int((time.monotonic() - start) * 1000)
