"""Repository helpers for background check webhook logs."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any, List, Optional, Sequence, Tuple, cast

from sqlalchemy import and_, desc, func, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..core.exceptions import RepositoryException
from ..models.instructor import BGCWebhookLog

logger = logging.getLogger(__name__)

MAX_LOG_ENTRIES = 200
TRIM_BATCH = 100


class BGCWebhookLogRepository:
    """Persist and query recent Checkr webhook deliveries."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.logger = logger

    def record(
        self,
        *,
        event_type: str,
        resource_id: str | None,
        delivery_id: str | None,
        http_status: int | None,
        payload: dict[str, Any],
        signature: str | None,
    ) -> BGCWebhookLog:
        """Persist a webhook payload and enforce a fixed history size."""

        try:
            entry = BGCWebhookLog(
                event_type=(event_type or "")[:64],
                resource_id=resource_id,
                delivery_id=delivery_id,
                http_status=http_status,
                payload_json=payload,
                signature=signature,
            )
            self.db.add(entry)
            self.db.flush()
            self._trim_excess()
            return entry
        except SQLAlchemyError as exc:
            self.logger.error("Failed to record webhook event %s: %s", event_type, str(exc))
            self.db.rollback()
            raise RepositoryException("Failed to persist webhook delivery") from exc

    def list_filtered(
        self,
        *,
        limit: int = 50,
        cursor: str | None = None,
        events: Sequence[str] | None = None,
        event_prefixes: Sequence[str] | None = None,
        status_codes: Sequence[int] | None = None,
        search: str | None = None,
    ) -> Tuple[List[BGCWebhookLog], str | None]:
        """Return filtered webhook deliveries ordered by recency."""

        capped = max(1, min(limit, MAX_LOG_ENTRIES))
        query = self.db.query(BGCWebhookLog).order_by(
            desc(BGCWebhookLog.created_at),
            desc(BGCWebhookLog.id),
        )

        clauses: list[Any] = []
        if events:
            clauses.append(BGCWebhookLog.event_type.in_(list(events)))
        prefix_filters = [
            BGCWebhookLog.event_type.like(f"{prefix}%")
            for prefix in (event_prefixes or [])
            if prefix
        ]
        if prefix_filters:
            clauses.extend(prefix_filters)
        if clauses:
            query = query.filter(or_(*clauses))
        if status_codes:
            query = query.filter(BGCWebhookLog.http_status.in_(list(status_codes)))
        if search:
            like_value = f"%{search.lower()}%"
            query = query.filter(
                or_(
                    func.lower(func.coalesce(BGCWebhookLog.delivery_id, "")).like(like_value),
                    func.lower(func.coalesce(BGCWebhookLog.signature, "")).like(like_value),
                )
            )
        if cursor:
            cursor_entry = self._get_by_id(cursor)
            if cursor_entry is not None:
                query = query.filter(
                    or_(
                        BGCWebhookLog.created_at < cursor_entry.created_at,
                        and_(
                            BGCWebhookLog.created_at == cursor_entry.created_at,
                            BGCWebhookLog.id < cursor_entry.id,
                        ),
                    )
                )

        try:
            rows: List[BGCWebhookLog] = query.limit(capped + 1).all()
        except SQLAlchemyError as exc:
            self.logger.error("Failed to list webhook deliveries: %s", str(exc))
            raise RepositoryException("Failed to load webhook deliveries") from exc

        next_cursor = rows[capped].id if len(rows) > capped else None
        return rows[:capped], next_cursor

    def count_errors_since(self, *, since: datetime) -> int:
        """Return the number of webhook deliveries with 4xx/5xx responses since timestamp."""

        cutoff = since if since.tzinfo else since.replace(tzinfo=timezone.utc)
        try:
            total = (
                self.db.query(func.count(BGCWebhookLog.id))
                .filter(
                    BGCWebhookLog.created_at >= cutoff,
                    BGCWebhookLog.http_status >= 400,
                )
                .scalar()
            )
            return int(total or 0)
        except SQLAlchemyError as exc:
            self.logger.error("Failed to count webhook errors: %s", str(exc))
            raise RepositoryException("Failed to count webhook errors") from exc

    def _get_by_id(self, entry_id: str) -> Optional[BGCWebhookLog]:
        try:
            return cast(Optional[BGCWebhookLog], self.db.get(BGCWebhookLog, entry_id))
        except SQLAlchemyError as exc:
            self.logger.error("Failed to load webhook entry %s: %s", entry_id, str(exc))
            raise RepositoryException("Failed to load webhook entry") from exc

    def _trim_excess(self) -> None:
        """Delete older rows beyond the configured MAX_LOG_ENTRIES."""

        try:
            outdated_ids = (
                self.db.query(BGCWebhookLog.id)
                .order_by(desc(BGCWebhookLog.created_at), desc(BGCWebhookLog.id))
                .offset(MAX_LOG_ENTRIES)
                .limit(TRIM_BATCH)
                .all()
            )
            if not outdated_ids:
                return

            ids = [row[0] for row in outdated_ids]
            (
                self.db.query(BGCWebhookLog)
                .filter(BGCWebhookLog.id.in_(ids))
                .delete(synchronize_session=False)
            )
            self.db.flush()
        except SQLAlchemyError as exc:
            self.logger.warning("Failed to trim webhook log entries: %s", str(exc))
            self.db.rollback()
