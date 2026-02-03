"""Schemas for governance audit log responses."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from ._strict_base import StrictModel


class AuditActor(StrictModel):
    type: str
    id: Optional[str] = None
    email: Optional[str] = None


class AuditResource(StrictModel):
    type: str
    id: Optional[str] = None


class AuditEntry(StrictModel):
    id: str
    timestamp: datetime
    actor: AuditActor
    action: str
    resource: AuditResource
    description: Optional[str] = None
    changes: Optional[dict[str, Any]] = None
    status: str
    request_id: Optional[str] = None


class AuditSearchMeta(StrictModel):
    since_hours: int
    total_count: int
    returned_count: int


class AuditSearchSummary(StrictModel):
    by_action: dict[str, int]
    by_actor_type: dict[str, int]
    by_status: dict[str, int]


class AuditSearchResponse(StrictModel):
    meta: AuditSearchMeta
    summary: AuditSearchSummary
    entries: list[AuditEntry]


__all__ = [
    "AuditActor",
    "AuditResource",
    "AuditEntry",
    "AuditSearchMeta",
    "AuditSearchSummary",
    "AuditSearchResponse",
]
