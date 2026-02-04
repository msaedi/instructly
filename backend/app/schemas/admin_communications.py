"""Schemas for MCP admin communication tooling."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field


class CommunicationChannel(str, Enum):
    EMAIL = "email"
    PUSH = "push"
    IN_APP = "in_app"


class AnnouncementAudience(str, Enum):
    ALL_USERS = "all_users"
    ALL_STUDENTS = "all_students"
    ALL_INSTRUCTORS = "all_instructors"
    ACTIVE_STUDENTS = "active_students"
    ACTIVE_INSTRUCTORS = "active_instructors"
    FOUNDING_INSTRUCTORS = "founding_instructors"


class BulkUserType(str, Enum):
    ALL = "all"
    STUDENT = "student"
    INSTRUCTOR = "instructor"


class CommunicationStatus(str, Enum):
    SENT = "sent"
    SCHEDULED = "scheduled"
    FAILED = "failed"


class RenderedContent(BaseModel):
    subject: str | None = None
    title: str
    body: str
    html_body: str | None = None
    text_body: str | None = None


class RecipientSample(BaseModel):
    user_id: str
    email: str | None = None
    first_name: str | None = None
    last_name: str | None = None


class AnnouncementPreviewRequest(BaseModel):
    audience: AnnouncementAudience
    channels: list[CommunicationChannel] = Field(..., min_length=1)
    title: str = Field(..., min_length=1, max_length=200)
    body: str = Field(..., min_length=1, max_length=5000)
    subject: str | None = Field(default=None, max_length=200)
    schedule_at: datetime | None = None
    high_priority: bool = False


class AnnouncementPreviewResponse(BaseModel):
    audience_size: int
    channel_breakdown: dict[str, int]
    rendered_content: RenderedContent
    warnings: list[str] = Field(default_factory=list)
    confirm_token: str | None = None
    idempotency_key: str | None = None


class AnnouncementExecuteRequest(BaseModel):
    confirm_token: str
    idempotency_key: str


class AnnouncementExecuteResponse(BaseModel):
    success: bool
    error: str | None = None
    status: str
    batch_id: str
    audience_size: int
    scheduled_for: datetime | None = None
    channel_results: dict[str, dict[str, int]]


class BulkTarget(BaseModel):
    user_type: BulkUserType | None = None
    user_ids: list[str] | None = None
    categories: list[str] | None = None
    locations: list[str] | None = None
    active_within_days: int | None = Field(default=None, ge=1, le=365)


class BulkNotificationPreviewRequest(BaseModel):
    target: BulkTarget
    channels: list[CommunicationChannel] = Field(..., min_length=1)
    title: str = Field(..., min_length=1, max_length=200)
    body: str = Field(..., min_length=1, max_length=5000)
    subject: str | None = Field(default=None, max_length=200)
    variables: dict[str, str] = Field(default_factory=dict)
    schedule_at: datetime | None = None


class BulkNotificationPreviewResponse(BaseModel):
    audience_size: int
    channel_breakdown: dict[str, int]
    sample_recipients: list[RecipientSample] = Field(default_factory=list)
    rendered_content: RenderedContent
    warnings: list[str] = Field(default_factory=list)
    confirm_token: str | None = None
    idempotency_key: str | None = None


class BulkNotificationExecuteRequest(BaseModel):
    confirm_token: str
    idempotency_key: str


class BulkNotificationExecuteResponse(BaseModel):
    success: bool
    error: str | None = None
    status: str
    batch_id: str
    audience_size: int
    scheduled_for: datetime | None = None
    channel_results: dict[str, dict[str, int]]


class NotificationHistoryEntry(BaseModel):
    batch_id: str
    kind: str
    status: str
    channels: list[str]
    created_at: datetime
    scheduled_for: datetime | None = None
    created_by: str | None = None
    audience_size: int
    subject: str | None = None
    title: str | None = None
    sent: dict[str, int]
    delivered: dict[str, int]
    failed: dict[str, int]
    open_rate: Decimal
    click_rate: Decimal


class NotificationHistorySummary(BaseModel):
    total: int
    sent: int
    delivered: int
    failed: int
    open_rate: Decimal
    click_rate: Decimal


class NotificationHistoryResponse(BaseModel):
    items: list[NotificationHistoryEntry]
    summary: NotificationHistorySummary


class TemplateInfo(BaseModel):
    template_id: str
    category: str
    channels: list[str]
    required_variables: list[str]
    optional_variables: list[str]
    usage_count: int


class NotificationTemplatesResponse(BaseModel):
    templates: list[TemplateInfo]


class EmailPreviewRequest(BaseModel):
    template: str
    variables: dict[str, str] = Field(default_factory=dict)
    subject: str | None = None
    test_send_to: str | None = None


class EmailPreviewResponse(BaseModel):
    template: str
    subject: str
    html_content: str
    text_content: str
    missing_variables: list[str]
    valid: bool
    test_send_success: bool | None = None
