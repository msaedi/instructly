"""Schemas for admin booking detail MCP endpoint."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from ._strict_base import StrictModel, StrictRequestModel


class BookingDetailRequest(StrictRequestModel):
    booking_id: str
    include_messages_summary: bool = False
    include_webhooks: bool = True
    include_trace_links: bool = False


class BookingDetailMeta(StrictModel):
    generated_at: datetime
    booking_id: str


class ServiceInfo(StrictModel):
    slug: str
    name: str
    category: str


class ParticipantInfo(StrictModel):
    id: str
    name: str
    email_hash: str


class BookingInfo(StrictModel):
    id: str
    status: str
    scheduled_at: datetime
    duration_minutes: int
    location_type: str
    service: ServiceInfo
    student: ParticipantInfo
    instructor: ParticipantInfo
    created_at: datetime
    updated_at: datetime


class TimelineEvent(StrictModel):
    ts: datetime
    event: str
    details: dict[str, Any] = Field(default_factory=dict)


class PaymentAmount(StrictModel):
    gross: float
    platform_fee: float
    credits_applied: float
    tip: float
    net_to_instructor: float


class PaymentIds(StrictModel):
    payment_intent: str | None = None
    charge: str | None = None


class PaymentFailure(StrictModel):
    ts: datetime
    category: str


class PaymentInfo(StrictModel):
    status: str
    amount: PaymentAmount
    ids: PaymentIds
    scheduled_authorize_at: datetime | None = None
    scheduled_capture_at: datetime | None = None
    failures: list[PaymentFailure] = Field(default_factory=list)


class MessagesSummary(StrictModel):
    included: bool
    conversation_id: str | None
    message_count: int | None
    last_message_at: datetime | None


class WebhookEventBrief(StrictModel):
    event_id: str
    type: str
    status: str
    ts: datetime


class WebhooksSummary(StrictModel):
    included: bool
    events: list[WebhookEventBrief] = Field(default_factory=list)


class TracesSummary(StrictModel):
    included: bool
    trace_ids: list[str] = Field(default_factory=list)
    support_code: str | None = None


class RecommendedAction(StrictModel):
    action: str
    reason: str
    allowed: bool


class BookingDetailResponse(StrictModel):
    meta: BookingDetailMeta
    booking: BookingInfo
    timeline: list[TimelineEvent]
    payment: PaymentInfo | None
    messages: MessagesSummary | None
    webhooks: WebhooksSummary | None
    traces: TracesSummary | None
    recommended_actions: list[RecommendedAction]


__all__ = [
    "BookingDetailMeta",
    "BookingDetailRequest",
    "BookingDetailResponse",
    "BookingInfo",
    "MessagesSummary",
    "ParticipantInfo",
    "PaymentAmount",
    "PaymentFailure",
    "PaymentIds",
    "PaymentInfo",
    "RecommendedAction",
    "ServiceInfo",
    "TimelineEvent",
    "TracesSummary",
    "WebhookEventBrief",
    "WebhooksSummary",
]
