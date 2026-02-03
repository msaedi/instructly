"""Schemas for MCP webhook ledger responses."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from ._strict_base import StrictModel
from .mcp import MCPTimeWindow


class MCPWebhookEventItem(StrictModel):
    id: str
    source: str
    event_type: str
    event_id: str | None = None
    status: str
    received_at: datetime | None = None
    processed_at: datetime | None = None
    processing_duration_ms: int | None = None
    related_entity: str | None = None
    replay_of: str | None = None
    replay_count: int = 0


class MCPWebhookListMeta(StrictModel):
    request_id: str
    generated_at: datetime
    since_hours: int
    total_count: int
    returned_count: int
    time_window: MCPTimeWindow


class MCPWebhookListSummary(StrictModel):
    by_status: dict[str, int] = Field(default_factory=dict)
    by_source: dict[str, int] = Field(default_factory=dict)


class MCPWebhookListResponse(StrictModel):
    meta: MCPWebhookListMeta
    summary: MCPWebhookListSummary
    events: list[MCPWebhookEventItem]


class MCPWebhookFailedMeta(StrictModel):
    request_id: str
    generated_at: datetime
    since_hours: int
    returned_count: int
    time_window: MCPTimeWindow


class MCPWebhookFailedItem(MCPWebhookEventItem):
    processing_error: str | None = None


class MCPWebhookFailedResponse(StrictModel):
    meta: MCPWebhookFailedMeta
    events: list[MCPWebhookFailedItem]


class MCPWebhookDetailMeta(StrictModel):
    request_id: str
    generated_at: datetime


class MCPWebhookDetail(MCPWebhookEventItem):
    payload: dict[str, Any]
    headers: dict[str, Any] | None = None
    processing_error: str | None = None
    idempotency_key: str | None = None


class MCPWebhookDetailResponse(StrictModel):
    meta: MCPWebhookDetailMeta
    event: MCPWebhookDetail


class MCPWebhookReplayMeta(StrictModel):
    request_id: str
    generated_at: datetime
    dry_run: bool


class MCPWebhookReplayResult(StrictModel):
    status: str
    replay_event_id: str | None = None
    error: str | None = None


class MCPWebhookReplayResponse(StrictModel):
    meta: MCPWebhookReplayMeta
    result: MCPWebhookReplayResult | None = None
    event: MCPWebhookEventItem | None = None
    note: str | None = None
