# backend/app/repositories/event_outbox_repository.py
"""
Repository for notification event outbox operations.

Implements transactional enqueue, pending fetch with locking, and status updates
required for the outbox dispatcher.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
from typing import Any, Iterable, Optional, cast

from sqlalchemy import Select, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session
import ulid

from app.database.session_utils import get_dialect_name
from app.models.event_outbox import EventOutbox, EventOutboxStatus

logger = logging.getLogger(__name__)


def _now_utc() -> datetime:
    """Return timezone-aware utcnow suitable for DB comparisons."""
    return datetime.now(timezone.utc)


class EventOutboxRepository:
    """Data access helpers for event outbox rows."""

    def __init__(self, db: Session):
        self.db = db
        self._dialect = get_dialect_name(db, default="postgresql").lower()

    # ------------------------------------------------------------------ enqueue
    def enqueue(
        self,
        event_type: str,
        aggregate_id: str,
        payload: Optional[dict[str, Any]] = None,
        idempotency_key: Optional[str] = None,
        next_attempt_at: Optional[datetime] = None,
    ) -> EventOutbox:
        """
        Insert a new outbox row if one does not already exist for the idempotency key.

        Returns the persisted row (existing or newly created).
        """
        payload = payload or {}
        next_attempt = next_attempt_at or _now_utc()
        key = idempotency_key or f"{event_type}:{aggregate_id}:{int(next_attempt.timestamp())}"

        event_id = str(ulid.ULID())
        stmt = insert(EventOutbox).values(
            event_type=event_type,
            aggregate_id=aggregate_id,
            payload=payload,
            idempotency_key=key,
            status=EventOutboxStatus.PENDING.value,
            attempt_count=0,
            next_attempt_at=next_attempt,
            id=event_id,
        )

        inserted_id: Optional[str] = None

        if self._dialect == "postgresql":
            stmt = pg_insert(EventOutbox).values(
                event_type=event_type,
                aggregate_id=aggregate_id,
                payload=payload,
                idempotency_key=key,
                status=EventOutboxStatus.PENDING.value,
                attempt_count=0,
                next_attempt_at=next_attempt,
                id=event_id,
            )
            stmt = stmt.on_conflict_do_nothing(index_elements=["idempotency_key"]).returning(
                EventOutbox.id
            )
            result = self.db.execute(stmt)
            inserted_value = result.scalar_one_or_none()
            if inserted_value is not None:
                inserted_id = cast(str, inserted_value)
        else:
            if self._dialect == "sqlite":
                stmt = stmt.prefix_with("OR IGNORE")
            result = self.db.execute(stmt)
            if getattr(result, "rowcount", 0):
                inserted_id = event_id

        if inserted_id:
            self.db.flush()
            row = cast(Optional[EventOutbox], self.db.get(EventOutbox, inserted_id))
            if row is None:
                raise RuntimeError("Inserted outbox row could not be reloaded")
            return row

        # Existing row - fetch and return without mutating attempt counters
        existing_result = self.db.execute(
            select(EventOutbox).where(EventOutbox.idempotency_key == key)
        )
        existing = cast(Optional[EventOutbox], existing_result.scalar_one_or_none())
        if existing is None:
            raise RuntimeError("Outbox row not found after enqueue conflict")
        return existing

    # ---------------------------------------------------------------- fetchers
    def fetch_pending(self, limit: int = 200) -> list[EventOutbox]:
        """Return pending events eligible for delivery ordered by attempt time."""
        now = _now_utc()
        stmt: Select[Any] = (
            select(EventOutbox)
            .where(EventOutbox.status == EventOutboxStatus.PENDING.value)
            .where(EventOutbox.next_attempt_at <= now)
            .order_by(EventOutbox.next_attempt_at.asc(), EventOutbox.id.asc())
            .limit(limit)
        )
        if self._dialect == "postgresql":
            stmt = stmt.with_for_update(skip_locked=True)

        result = self.db.execute(stmt)
        rows = cast(list[EventOutbox], result.scalars().all())
        return rows

    def get_by_id(self, event_id: str, for_update: bool = False) -> Optional[EventOutbox]:
        """Fetch a single outbox row."""
        if for_update and self._dialect == "postgresql":
            stmt = (
                select(EventOutbox)
                .where(EventOutbox.id == event_id)
                .with_for_update(skip_locked=True)
            )
            result = self.db.execute(stmt)
            return cast(Optional[EventOutbox], result.scalar_one_or_none())
        return cast(Optional[EventOutbox], self.db.get(EventOutbox, event_id))

    # ------------------------------------------------------------- state updates
    def mark_sent(self, event_id: str, attempt_count: int) -> None:
        """Update row to SENT state."""
        now = _now_utc()
        self.db.execute(
            update(EventOutbox)
            .where(EventOutbox.id == event_id)
            .values(
                status=EventOutboxStatus.SENT.value,
                attempt_count=attempt_count,
                last_error=None,
                next_attempt_at=now,
                updated_at=now,
            )
        )
        self.db.flush()

    def mark_sent_by_key(self, idempotency_key: str, attempt_count: int) -> None:
        """Mark an outbox row as sent using its idempotency key."""
        now = _now_utc()
        self.db.execute(
            update(EventOutbox)
            .where(EventOutbox.idempotency_key == idempotency_key)
            .values(
                status=EventOutboxStatus.SENT.value,
                attempt_count=attempt_count,
                last_error=None,
                next_attempt_at=now,
                updated_at=now,
            )
        )
        self.db.flush()

    def mark_failed(
        self,
        event_id: str,
        *,
        attempt_count: int,
        backoff_seconds: int,
        error: str | None = None,
        terminal: bool = False,
    ) -> None:
        """Update row after delivery failure."""
        now = _now_utc()
        values = {
            "attempt_count": attempt_count,
            "updated_at": now,
            "last_error": (error[:1000] if error else None),
        }
        if terminal:
            values["status"] = EventOutboxStatus.FAILED.value
            values["next_attempt_at"] = now
        else:
            values["status"] = EventOutboxStatus.PENDING.value
            values["next_attempt_at"] = now + timedelta(seconds=max(backoff_seconds, 1))

        self.db.execute(update(EventOutbox).where(EventOutbox.id == event_id).values(**values))
        self.db.flush()

    def reset_failed(self, event_ids: Iterable[str]) -> None:
        """Reset failed rows back to pending (maintenance helper)."""
        ids = list(event_ids)
        if not ids:
            return
        now = _now_utc()
        self.db.execute(
            update(EventOutbox)
            .where(EventOutbox.id.in_(ids))
            .values(
                status=EventOutboxStatus.PENDING.value,
                next_attempt_at=now,
                updated_at=now,
            )
        )
        self.db.flush()
