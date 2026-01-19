# backend/app/repositories/audit_repository.py
"""
Repository helpers for audit_log persistence and querying.
"""

from __future__ import annotations

from datetime import datetime
import logging
from typing import Any, Optional, Sequence

from sqlalchemy import Select, and_, func, select
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.monitoring.prometheus_metrics import prometheus_metrics

logger = logging.getLogger(__name__)


class AuditRepository:
    """Persist and query audit trail entries."""

    def __init__(self, db: Session):
        self.db = db

    def write(self, audit: AuditLog) -> None:
        """Persist a new audit row inside the active transaction."""
        self.db.add(audit)
        try:
            prometheus_metrics.record_audit_write(audit.entity_type, audit.action)
        except Exception:
            logger.debug("Non-fatal error ignored", exc_info=True)
        self.db.flush()

    def list(
        self,
        *,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        action: Optional[str] = None,
        actor_id: Optional[str] = None,
        actor_role: Optional[str] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[Sequence[AuditLog], int]:
        """Return audit rows matching supplied filters ordered descending by timestamp."""
        limit = max(0, limit)
        offset = max(0, offset)

        conditions = list(_build_filters(entity_type, entity_id, action, actor_id, actor_role))
        if start is not None:
            conditions.append(AuditLog.occurred_at >= start)
        if end is not None:
            conditions.append(AuditLog.occurred_at <= end)

        stmt: Select[AuditLog] = select(AuditLog).order_by(AuditLog.occurred_at.desc())
        count_stmt = select(func.count()).select_from(AuditLog)

        if conditions:
            stmt = stmt.where(and_(*conditions))
            count_stmt = count_stmt.where(and_(*conditions))

        stmt = stmt.offset(offset).limit(limit)

        rows = self.db.execute(stmt).scalars().all()
        total = self.db.execute(count_stmt).scalar_one()

        return rows, int(total)

    def list_for_booking_actions(
        self,
        *,
        actions: Sequence[str],
        actor_id: Optional[str] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        limit: Optional[int] = 50,
        offset: int = 0,
    ) -> tuple[Sequence[AuditLog], int]:
        """Return audit rows for booking actions with optional filtering."""
        offset = max(0, offset)
        if limit is not None:
            limit = max(0, limit)

        conditions = [AuditLog.entity_type == "booking"]
        if actions:
            conditions.append(AuditLog.action.in_(list(actions)))
        if actor_id:
            conditions.append(AuditLog.actor_id == actor_id)
        if start is not None:
            conditions.append(AuditLog.occurred_at >= start)
        if end is not None:
            conditions.append(AuditLog.occurred_at <= end)

        stmt: Select[AuditLog] = select(AuditLog).order_by(AuditLog.occurred_at.desc())
        count_stmt = select(func.count()).select_from(AuditLog)

        if conditions:
            stmt = stmt.where(and_(*conditions))
            count_stmt = count_stmt.where(and_(*conditions))

        if offset:
            stmt = stmt.offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)

        rows = self.db.execute(stmt).scalars().all()
        total = self.db.execute(count_stmt).scalar_one()

        return rows, int(total)


def _build_filters(
    entity_type: Optional[str],
    entity_id: Optional[str],
    action: Optional[str],
    actor_id: Optional[str],
    actor_role: Optional[str],
) -> list[Any]:
    clauses: list[Any] = []
    if entity_type:
        clauses.append(AuditLog.entity_type == entity_type)
    if entity_id:
        clauses.append(AuditLog.entity_id == entity_id)
    if action:
        clauses.append(AuditLog.action == action)
    if actor_id:
        clauses.append(AuditLog.actor_id == actor_id)
    if actor_role:
        clauses.append(AuditLog.actor_role == actor_role)
    return clauses
