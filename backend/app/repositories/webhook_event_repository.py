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
        limit: int = 50,
    ) -> list[WebhookEvent]:
        """Return recent webhook events filtered by criteria."""
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

    def count_events(self, *, since_hours: int = 24) -> int:
        cutoff = self._cutoff(since_hours)
        query = self.db.query(func.count(WebhookEvent.id)).filter(
            WebhookEvent.received_at >= cutoff
        )
        count_value = self._execute_scalar(query)
        return int(count_value or 0)

    def summarize_by_status(self, *, since_hours: int = 24) -> dict[str, int]:
        cutoff = self._cutoff(since_hours)
        try:
            rows = (
                self.db.query(WebhookEvent.status, func.count(WebhookEvent.id))
                .filter(WebhookEvent.received_at >= cutoff)
                .group_by(WebhookEvent.status)
                .all()
            )
        except SQLAlchemyError as exc:
            self.logger.error("Failed to summarize webhook status counts: %s", str(exc))
            raise RepositoryException("Failed to summarize webhook status counts") from exc
        typed_rows = cast(list[tuple[str | None, int]], rows)
        return {row[0] or "unknown": int(row[1] or 0) for row in typed_rows}

    def summarize_by_source(self, *, since_hours: int = 24) -> dict[str, int]:
        cutoff = self._cutoff(since_hours)
        try:
            rows = (
                self.db.query(WebhookEvent.source, func.count(WebhookEvent.id))
                .filter(WebhookEvent.received_at >= cutoff)
                .group_by(WebhookEvent.source)
                .all()
            )
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

    def get_failed_events(
        self,
        *,
        source: str | None = None,
        since_hours: int = 24,
        limit: int = 50,
    ) -> list[WebhookEvent]:
        cutoff = self._cutoff(since_hours)
        query = self._build_query().filter(
            WebhookEvent.status == "failed",
            WebhookEvent.received_at >= cutoff,
        )
        if source:
            query = query.filter(WebhookEvent.source == source)
        query = query.order_by(WebhookEvent.received_at.desc()).limit(limit)
        return self._execute_query(query)
