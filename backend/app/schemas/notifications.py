# backend/app/schemas/notifications.py
"""Schemas for notification inbox endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import ConfigDict, Field

from ._strict_base import StrictModel


class NotificationResponse(StrictModel):
    """Notification inbox entry."""

    id: str
    category: str
    type: str
    title: str
    body: str | None
    data: dict[str, Any] | None
    read_at: datetime | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, **StrictModel.model_config)


class NotificationListResponse(StrictModel):
    """Paginated notification response."""

    notifications: list[NotificationResponse]
    total: int
    unread_count: int


class NotificationUnreadCountResponse(StrictModel):
    """Unread notification count response."""

    unread_count: int = Field(..., ge=0)


class NotificationStatusResponse(StrictModel):
    """Simple status response for notification actions."""

    success: bool
    message: str | None = None
