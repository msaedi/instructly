"""Repository helpers for webhook event ledger."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
from typing import cast

from sqlalchemy import func, update as sa_update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.exceptions import RepositoryException
from app.models.webhook_event import WebhookEvent
from app.repositories.base_repository import BaseRepository

logger = logging.getLogger(__name__)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


class WebhookEventRepository(BaseRepository[WebhookEvent]):
    """Repository for webhook ledger queries."""

    def __init__(self, db: Session) -> None:
        super().__init__(db, WebhookEvent)

    @staticmethod
    def _cutoff(since_hours: int) -> datetime:
        return _now_utc() - timedelta(hours=since_hours)

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
        if start_time or end_time:
            query = self._build_query()
            if start_time is not None:
                query = query.filter(WebhookEvent.received_at >= start_time)
            if end_time is not None:
                query = query.filter(WebhookEvent.received_at <= end_time)
        else:
            cutoff = self._cutoff(since_hours)
            query = self._build_query().filter(WebhookEvent.received_at >= cutoff)
        if source:
            query = query.filter(WebhookEvent.source == source)
        if status:
            query = query.filter(WebhookEvent.status == status)
        if event_type:
            query = query.filter(WebhookEvent.event_type == event_type)
        query = query.order_by(WebhookEvent.received_at.desc()).limit(limit)
        return self._execute_query(query)

    def count_events(
        self,
        *,
        since_hours: int = 24,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> int:
        query = self.db.query(func.count(WebhookEvent.id))
        if start_time is not None:
            query = query.filter(WebhookEvent.received_at >= start_time)
        elif end_time is None:
            cutoff = self._cutoff(since_hours)
            query = query.filter(WebhookEvent.received_at >= cutoff)
        if end_time is not None:
            query = query.filter(WebhookEvent.received_at <= end_time)
        count_value = self._execute_scalar(query)
        return int(count_value or 0)

    def summarize_by_status(
        self,
        *,
        since_hours: int = 24,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> dict[str, int]:
        try:
            query = self.db.query(WebhookEvent.status, func.count(WebhookEvent.id))
            if start_time is not None:
                query = query.filter(WebhookEvent.received_at >= start_time)
            elif end_time is None:
                cutoff = self._cutoff(since_hours)
                query = query.filter(WebhookEvent.received_at >= cutoff)
            if end_time is not None:
                query = query.filter(WebhookEvent.received_at <= end_time)
            rows = query.group_by(WebhookEvent.status).all()
        except SQLAlchemyError as exc:
            self.logger.error("Failed to summarize webhook status counts: %s", str(exc))
            raise RepositoryException("Failed to summarize webhook status counts") from exc
        typed_rows = cast(list[tuple[str | None, int]], rows)
        return {row[0] or "unknown": int(row[1] or 0) for row in typed_rows}

    def summarize_by_source(
        self,
        *,
        since_hours: int = 24,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> dict[str, int]:
        try:
            query = self.db.query(WebhookEvent.source, func.count(WebhookEvent.id))
            if start_time is not None:
                query = query.filter(WebhookEvent.received_at >= start_time)
            elif end_time is None:
                cutoff = self._cutoff(since_hours)
                query = query.filter(WebhookEvent.received_at >= cutoff)
            if end_time is not None:
                query = query.filter(WebhookEvent.received_at <= end_time)
            rows = query.group_by(WebhookEvent.source).all()
        except SQLAlchemyError as exc:
            self.logger.error("Failed to summarize webhook source counts: %s", str(exc))
            raise RepositoryException("Failed to summarize webhook source counts") from exc
        typed_rows = cast(list[tuple[str | None, int]], rows)
        return {row[0] or "unknown": int(row[1] or 0) for row in typed_rows}

    def get_event(self, event_id: str) -> WebhookEvent | None:
        try:
            return cast(WebhookEvent | None, self.db.get(WebhookEvent, event_id))
        except SQLAlchemyError as exc:
            self.logger.error("Failed to load webhook event %s: %s", event_id, str(exc))
            raise RepositoryException("Failed to load webhook event") from exc

    def find_by_source_and_event_id(self, source: str, event_id: str) -> WebhookEvent | None:
        """Find webhook event by source and external event ID."""
        result = (
            self.db.query(WebhookEvent)
            .filter(WebhookEvent.source == source, WebhookEvent.event_id == event_id)
            .first()
        )
        return cast(WebhookEvent | None, result)

    def find_by_source_and_idempotency_key(
        self,
        source: str,
        idempotency_key: str,
    ) -> WebhookEvent | None:
        """Find webhook event by source and idempotency key."""
        result = (
            self.db.query(WebhookEvent)
            .filter(
                WebhookEvent.source == source,
                WebhookEvent.idempotency_key == idempotency_key,
            )
            .first()
        )
        return cast(WebhookEvent | None, result)

    MAX_PROCESSING_ATTEMPTS = 3

    def claim_for_processing(self, event_id: str) -> bool:
        """Atomically claim an event for processing.

        M1: events that have already failed ``MAX_PROCESSING_ATTEMPTS`` times are
        transitioned to ``dead_letter`` and not re-claimed, preventing an
        infinite retry loop on a poison-message handler. Events already in
        ``dead_letter`` are never claimed.
        """
        try:
            # Advisory pre-check: the authoritative guard is the atomic UPDATE below,
            # which uses WHERE status IN ('received', 'failed') to prevent claiming
            # dead_letter or already-processing events. This pre-check exists only to
            # provide a clear log message and avoid the UPDATE round-trip when the
            # outcome is already known.
            current = self.db.query(WebhookEvent).filter(WebhookEvent.id == event_id).one_or_none()
            if current is None:
                return False
            if current.status == "dead_letter":
                return False
            if (
                current.status == "failed"
                and (current.attempt_count or 0) >= self.MAX_PROCESSING_ATTEMPTS
            ):
                # Single-writer guard: if two workers both read status='failed' with
                # attempt_count >= MAX, both will try to transition to dead_letter.
                # The WHERE status='failed' clause ensures exactly one UPDATE writes;
                # the second worker's UPDATE finds status='dead_letter' and is a
                # no-op (rowcount=0).
                self.db.execute(
                    sa_update(WebhookEvent)
                    .where(WebhookEvent.id == event_id)
                    .where(WebhookEvent.status == "failed")
                    .values(status="dead_letter")
                )
                self.db.flush()
                # Expire the ORM attribute so any later ``get_event`` (e.g. the
                # route's re-fetch after ``mark_processing`` returns False) sees
                # ``status="dead_letter"`` without an explicit ``db.refresh``.
                # SQLAlchemy's session doesn't auto-expire identity-map objects
                # after a core-level UPDATE on the same row.
                if current is not None:
                    self.db.expire(current, ["status"])
                return False

            stmt = (
                sa_update(WebhookEvent)
                .where(
                    WebhookEvent.id == event_id,
                    WebhookEvent.status.in_(("received", "failed")),
                )
                .values(
                    status="processing",
                    processing_error=None,
                    processed_at=None,
                    attempt_count=(WebhookEvent.attempt_count + 1),
                )
                .returning(WebhookEvent.id)
            )
            row = self.db.execute(stmt).first()
            return row is not None
        except SQLAlchemyError as exc:
            self.logger.error(
                "Failed to claim webhook event %s for processing: %s", event_id, str(exc)
            )
            raise RepositoryException("Failed to claim webhook event for processing") from exc

    def get_failed_events(
        self,
        *,
        source: str | None = None,
        since_hours: int = 24,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 50,
    ) -> list[WebhookEvent]:
        query = self._build_query().filter(WebhookEvent.status == "failed")
        if start_time is not None:
            query = query.filter(WebhookEvent.received_at >= start_time)
        elif end_time is None:
            cutoff = self._cutoff(since_hours)
            query = query.filter(WebhookEvent.received_at >= cutoff)
        if end_time is not None:
            query = query.filter(WebhookEvent.received_at <= end_time)
        if source:
            query = query.filter(WebhookEvent.source == source)
        query = query.order_by(WebhookEvent.received_at.desc()).limit(limit)
        return self._execute_query(query)

    def list_events_for_related_entity(
        self,
        *,
        related_entity_id: str,
        related_entity_type: str | None = None,
        limit: int | None = None,
    ) -> list[WebhookEvent]:
        """Return webhook events for a related entity, ordered oldest to newest."""
        query = self._build_query().filter(WebhookEvent.related_entity_id == related_entity_id)
        if related_entity_type:
            query = query.filter(WebhookEvent.related_entity_type == related_entity_type)
        query = query.order_by(WebhookEvent.received_at.asc())
        if limit is not None:
            query = query.limit(limit)
        return self._execute_query(query)
