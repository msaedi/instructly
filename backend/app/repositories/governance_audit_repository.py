"""Repository helpers for governance audit_log persistence and querying."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Sequence, cast

from sqlalchemy import Select, and_, func, select
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLogEntry


class GovernanceAuditRepository:
    """Query helpers for governance audit log entries."""

    def __init__(self, db: Session):
        self.db = db

    def write(self, entry: AuditLogEntry) -> None:
        """Persist a new audit log entry."""
        self.db.add(entry)
        self.db.flush()

    def search(
        self,
        *,
        actor_email: Optional[str] = None,
        actor_id: Optional[str] = None,
        actor_types: Optional[Sequence[str]] = None,
        action: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        status: Optional[str] = None,
        since_hours: int = 24,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 100,
    ) -> tuple[Sequence[AuditLogEntry], int, dict[str, dict[str, int]]]:
        limit = max(0, min(limit, 500))
        if start_time or end_time:
            start = start_time
            end = end_time
        else:
            now = datetime.now(timezone.utc)
            start = now - timedelta(hours=max(0, since_hours))
            end = now

        conditions = []
        if start is not None:
            conditions.append(AuditLogEntry.timestamp >= start)
        if end is not None:
            conditions.append(AuditLogEntry.timestamp <= end)
        if actor_email:
            conditions.append(AuditLogEntry.actor_email == actor_email)
        if actor_id:
            conditions.append(AuditLogEntry.actor_id == actor_id)
        if actor_types:
            conditions.append(AuditLogEntry.actor_type.in_(list(actor_types)))
        if action:
            conditions.append(AuditLogEntry.action == action)
        if resource_type:
            conditions.append(AuditLogEntry.resource_type == resource_type)
        if resource_id:
            conditions.append(AuditLogEntry.resource_id == resource_id)
        if status:
            conditions.append(AuditLogEntry.status == status)

        stmt: Select[AuditLogEntry] = select(AuditLogEntry).order_by(AuditLogEntry.timestamp.desc())
        count_stmt = select(func.count()).select_from(AuditLogEntry)

        if conditions:
            stmt = stmt.where(and_(*conditions))
            count_stmt = count_stmt.where(and_(*conditions))

        stmt = stmt.limit(limit)
        entries = self.db.execute(stmt).scalars().all()
        total = int(self.db.execute(count_stmt).scalar_one())

        summary = {
            "by_action": self._group_counts(AuditLogEntry.action, conditions),
            "by_actor_type": self._group_counts(AuditLogEntry.actor_type, conditions),
            "by_status": self._group_counts(AuditLogEntry.status, conditions),
        }

        return entries, total, summary

    def list_by_resource(
        self,
        *,
        resource_type: str,
        resource_id: str,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 50,
    ) -> Sequence[AuditLogEntry]:
        conditions = [
            AuditLogEntry.resource_type == resource_type,
            AuditLogEntry.resource_id == resource_id,
        ]
        if start_time is not None:
            conditions.append(AuditLogEntry.timestamp >= start_time)
        if end_time is not None:
            conditions.append(AuditLogEntry.timestamp <= end_time)
        stmt = (
            select(AuditLogEntry)
            .where(and_(*conditions))
            .order_by(AuditLogEntry.timestamp.desc())
            .limit(max(0, min(limit, 500)))
        )
        entries = self.db.execute(stmt).scalars().all()
        return cast(Sequence[AuditLogEntry], entries)

    def _group_counts(
        self,
        column: Any,
        conditions: list[Any],
    ) -> dict[str, int]:
        stmt = select(column, func.count()).select_from(AuditLogEntry)
        if conditions:
            stmt = stmt.where(and_(*conditions))
        stmt = stmt.group_by(column)
        rows = self.db.execute(stmt).all()
        return {str(row[0]): int(row[1]) for row in rows if row[0] is not None}
