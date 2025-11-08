# backend/app/repositories/notification_delivery_repository.py
"""
Repository for downstream notification delivery tracking.

Provides simple idempotent persistence used by the provider shim.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional, cast

from sqlalchemy import Select, insert, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session
import ulid

from app.database.session_utils import get_dialect_name
from app.models.event_outbox import NotificationDelivery


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


class NotificationDeliveryRepository:
    """Data access helper for notification_delivery rows."""

    def __init__(self, db: Session):
        self.db = db
        self._dialect = get_dialect_name(db, default="postgresql").lower()

    def record_delivery(
        self,
        event_type: str,
        idempotency_key: str,
        payload: Optional[dict[str, Any]] = None,
    ) -> NotificationDelivery:
        """
        Persist the delivery attempt and enforce idempotency.

        Returns the up-to-date row reflecting attempt count.
        """
        payload = payload or {}
        now = _now_utc()

        if self._dialect == "postgresql":
            stmt = (
                pg_insert(NotificationDelivery)
                .values(
                    event_type=event_type,
                    idempotency_key=idempotency_key,
                    payload=payload,
                    attempt_count=1,
                    delivered_at=now,
                    id=str(ulid.ULID()),
                )
                .on_conflict_do_nothing(index_elements=["idempotency_key"])
                .returning(NotificationDelivery)
            )
            result = self.db.execute(stmt)
            row = cast(Optional[NotificationDelivery], result.scalar_one_or_none())
            if row is None:
                row = self.get_by_idempotency_key(idempotency_key)
                if row is None:
                    raise RuntimeError("Failed to load notification delivery after conflict")
                row.touch(payload)
            self.db.flush()
            return row

        if self._dialect == "sqlite":
            stmt = (
                sqlite_insert(NotificationDelivery)
                .values(
                    event_type=event_type,
                    idempotency_key=idempotency_key,
                    payload=payload,
                    attempt_count=1,
                    delivered_at=now,
                    id=str(ulid.ULID()),
                )
                .on_conflict_do_nothing(index_elements=["idempotency_key"])
            )
            self.db.execute(stmt)
            self.db.flush()
            existing = self.get_by_idempotency_key(idempotency_key)
            if existing is None:
                raise RuntimeError("Failed to load notification delivery after SQLite conflict")
            existing.touch(payload)
            self.db.flush()
            return existing

        # Generic fallback: attempt insert, fallback to update
        insert_stmt = insert(NotificationDelivery).values(
            event_type=event_type,
            idempotency_key=idempotency_key,
            payload=payload,
            attempt_count=1,
            delivered_at=now,
            id=str(ulid.ULID()),
        )
        result = self.db.execute(insert_stmt)
        if getattr(result, "rowcount", 0):
            self.db.flush()
            inserted_pk = result.inserted_primary_key
            if inserted_pk:
                row = cast(
                    Optional[NotificationDelivery],
                    self.db.get(NotificationDelivery, inserted_pk[0]),
                )
                if row is not None:
                    return row

        # Duplicate: fetch existing and bump attempts
        existing = self.get_by_idempotency_key(idempotency_key)
        if existing is None:
            raise RuntimeError("Notification delivery record missing after update")
        existing.touch(payload)
        self.db.flush()
        return existing

    def get_by_idempotency_key(self, idempotency_key: str) -> Optional[NotificationDelivery]:
        """Fetch a delivery row by idempotency key."""
        stmt: Select[Any] = select(NotificationDelivery).where(
            NotificationDelivery.idempotency_key == idempotency_key
        )
        result = self.db.execute(stmt)
        return cast(Optional[NotificationDelivery], result.scalar_one_or_none())

    def reset(self) -> None:
        """Utility for tests to clear table without truncating."""
        self.db.query(NotificationDelivery).delete(synchronize_session=False)
        self.db.flush()
