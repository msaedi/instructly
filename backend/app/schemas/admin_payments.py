"""Schemas for MCP admin payment timeline endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import Field

from ._strict_base import StrictModel
from .mcp import MCPTimeWindow


class AdminPaymentAmount(StrictModel):
    gross: float
    platform_fee: float
    credits_applied: float
    tip: float
    net_to_instructor: float


class AdminPaymentStatusEvent(StrictModel):
    ts: datetime
    state: str


class AdminPaymentFailure(StrictModel):
    category: str
    last_failed_at: Optional[datetime] = None


class AdminPaymentRefund(StrictModel):
    refund_id: Optional[str] = None
    amount: Optional[float] = None
    status: Optional[str] = None
    created_at: Optional[datetime] = None


class AdminPaymentTimelineItem(StrictModel):
    booking_id: str
    created_at: datetime
    amount: AdminPaymentAmount
    status: str
    status_timeline: list[AdminPaymentStatusEvent]
    provider_refs: dict[str, str] = Field(default_factory=dict)
    failure: Optional[AdminPaymentFailure] = None
    refunds: list[AdminPaymentRefund] = Field(default_factory=list)


class AdminPaymentTimelineFlags(StrictModel):
    has_failed_payment: bool
    has_pending_refund: bool
    possible_double_charge: bool


class AdminPaymentTimelineMeta(StrictModel):
    time_window: MCPTimeWindow
    total_count: int


class AdminPaymentTimelineResponse(StrictModel):
    payments: list[AdminPaymentTimelineItem]
    flags: AdminPaymentTimelineFlags
    meta: AdminPaymentTimelineMeta


__all__ = [
    "AdminPaymentAmount",
    "AdminPaymentStatusEvent",
    "AdminPaymentFailure",
    "AdminPaymentRefund",
    "AdminPaymentTimelineItem",
    "AdminPaymentTimelineFlags",
    "AdminPaymentTimelineMeta",
    "AdminPaymentTimelineResponse",
]
