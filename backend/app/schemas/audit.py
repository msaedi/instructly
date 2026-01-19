# backend/app/schemas/audit.py
"""Pydantic schemas for admin audit log responses."""

from __future__ import annotations

from datetime import datetime
import logging
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict

logger = logging.getLogger(__name__)


class AuditLogView(BaseModel):
    """Single audit log entry."""

    id: str
    entity_type: str
    entity_id: str
    action: str
    actor_id: Optional[str] = None
    actor_role: Optional[str] = None
    occurred_at: datetime
    before: Optional[Dict[str, Any]] = None
    after: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(from_attributes=True)


class AuditLogListResponse(BaseModel):
    """Paginated audit log response."""

    items: list[AuditLogView]
    total: int
    limit: int
    offset: int


__all__ = ["AuditLogView", "AuditLogListResponse"]

try:
    AuditLogView.model_rebuild()
    AuditLogListResponse.model_rebuild()
except Exception:
    logger.debug("Non-fatal error ignored", exc_info=True)
