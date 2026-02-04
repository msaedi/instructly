"""Repository helpers for webhook event ledger."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
from typing import cast

from sqlalchemy import func
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
