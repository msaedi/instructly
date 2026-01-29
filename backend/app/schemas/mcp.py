"""Schemas for MCP admin responses."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal, Optional

from pydantic import EmailStr, Field

from ._strict_base import StrictModel, StrictRequestModel


class MCPActor(StrictModel):
    id: str
    email: str
    principal_type: Literal["user", "service"] = "service"


class MCPMeta(StrictModel):
    request_id: str
    generated_at: datetime
    actor: MCPActor


class MCPFunnelStage(StrictModel):
    stage: str
    count: int
    description: str


class MCPConversionRate(StrictModel):
    from_stage: str
    to_stage: str
    rate: float


class MCPFoundingCap(StrictModel):
    cap: int
    used: int
    remaining: int
    is_founding_phase: bool


class MCPTimeWindow(StrictModel):
    start: Optional[datetime] = None
    end: Optional[datetime] = None


class MCPFunnelSummaryResponse(StrictModel):
    meta: MCPMeta
    stages: list[MCPFunnelStage]
    conversion_rates: list[MCPConversionRate]
    founding_cap: MCPFoundingCap
    time_window: MCPTimeWindow


class MCPStuckInstructor(StrictModel):
    user_id: str
    name: str
    email: str
    current_stage: str
    days_in_stage: int
    occurred_at: Optional[datetime] = None


class MCPStuckSummary(StrictModel):
    stage: str
    stuck_count: int


class MCPStuckResponse(StrictModel):
    meta: MCPMeta
    summary: list[MCPStuckSummary]
    instructors: list[MCPStuckInstructor]
    total_stuck: int


class MCPInstructorListItem(StrictModel):
    user_id: str
    name: str
    email: str
    status: str
    is_founding: bool
    founding_granted_at: Optional[datetime] = None
    services: list[str]
    categories: list[str]
    live_at: Optional[datetime] = None
    rating_avg: float
    bookings_completed: int
    admin_url: str


class MCPInstructorListResponse(StrictModel):
    meta: MCPMeta
    items: list[MCPInstructorListItem]
    next_cursor: Optional[str] = None
    limit: int


class MCPServiceCoverageData(StrictModel):
    group_by: str
    labels: list[str]
    values: list[int]
    total_instructors: int
    total_services_offered: int


class MCPServiceCoverageResponse(StrictModel):
    meta: MCPMeta
    data: MCPServiceCoverageData


class MCPInstructorOnboarding(StrictModel):
    profile_created_at: Optional[datetime] = None
    profile_updated_at: Optional[datetime] = None
    identity_verified_at: Optional[datetime] = None
    background_check_uploaded_at: Optional[datetime] = None
    bgc_invited_at: Optional[datetime] = None
    bgc_completed_at: Optional[datetime] = None
    onboarding_completed_at: Optional[datetime] = None


class MCPInstructorBGC(StrictModel):
    status: Optional[str] = None
    completed_at: Optional[datetime] = None
    valid_until: Optional[datetime] = None


class MCPInstructorService(StrictModel):
    name: str
    slug: str
    category: str
    hourly_rate: Decimal
    is_active: bool


class MCPInstructorStats(StrictModel):
    bookings_completed: int
    bookings_cancelled: int
    no_shows: int
    rating_avg: float
    rating_count: int
    response_rate: Optional[float] = None


class MCPInstructorDetailResponse(StrictModel):
    meta: MCPMeta
    user_id: str
    name: str
    email: str
    phone: Optional[str] = None
    status: str
    is_founding: bool
    founding_granted_at: Optional[datetime] = None
    admin_url: str
    live_at: Optional[datetime] = None
    onboarding: MCPInstructorOnboarding
    bgc: MCPInstructorBGC
    services: list[MCPInstructorService]
    stats: MCPInstructorStats


class MCPDateWindow(StrictModel):
    start: date
    end: date


class MCPInvitePreviewRequest(StrictRequestModel):
    recipient_emails: list[EmailStr] = Field(..., min_length=1, max_length=100)
    grant_founding_status: bool = Field(default=True)
    expires_in_days: int = Field(default=14, ge=1, le=180)
    message_note: Optional[str] = None


class MCPInvitePreviewRecipient(StrictModel):
    email: EmailStr
    exists_in_system: bool
    user_id: Optional[str] = None


class MCPInvitePreview(StrictModel):
    subject: str
    expires_at: datetime
    grants_founding: bool
    founding_cap_remaining: int


class MCPInvitePreviewData(StrictModel):
    recipient_count: int
    recipients: list[MCPInvitePreviewRecipient]
    invite_preview: MCPInvitePreview
    confirm_token: str
    confirm_expires_at: datetime
    warnings: list[str]


class MCPInvitePreviewResponse(StrictModel):
    meta: MCPMeta
    data: MCPInvitePreviewData


class MCPInviteSendRequest(StrictRequestModel):
    confirm_token: str
    idempotency_key: str


class MCPInviteSendResult(StrictModel):
    email: EmailStr
    code: str
    status: str


class MCPInviteSendData(StrictModel):
    sent_count: int
    failed_count: int
    invites: list[MCPInviteSendResult]
    audit_id: str


class MCPInviteSendResponse(StrictModel):
    meta: MCPMeta
    data: MCPInviteSendData


class MCPTopQuery(StrictModel):
    query: str
    count: int
    avg_results: float
    conversion_rate: float


class MCPTopQueriesData(StrictModel):
    time_window: MCPDateWindow
    queries: list[MCPTopQuery]
    total_searches: int


class MCPTopQueriesResponse(StrictModel):
    meta: MCPMeta
    data: MCPTopQueriesData


class MCPZeroResultQuery(StrictModel):
    query: str
    count: int


class MCPZeroResultsData(StrictModel):
    time_window: MCPDateWindow
    queries: list[MCPZeroResultQuery]
    total_zero_result_searches: int
    zero_result_rate: float


class MCPZeroResultsResponse(StrictModel):
    meta: MCPMeta
    data: MCPZeroResultsData


class MCPMetricDefinition(StrictModel):
    metric: str
    definition: str
    requirements: list[str]
    source_fields: list[str]
    related_metrics: list[str]


class MCPMetricResponse(StrictModel):
    meta: MCPMeta
    data: MCPMetricDefinition


class MCPServiceCatalogItem(StrictModel):
    id: str
    name: str
    slug: str
    category_slug: Optional[str] = None
    category_name: Optional[str] = None
    is_active: bool


class MCPServiceCatalogData(StrictModel):
    services: list[MCPServiceCatalogItem]
    count: int


class MCPServiceCatalogResponse(StrictModel):
    meta: MCPMeta
    data: MCPServiceCatalogData


class MCPServiceLookupData(StrictModel):
    query: str
    matches: list[MCPServiceCatalogItem]
    count: int
    message: Optional[str] = None


class MCPServiceLookupResponse(StrictModel):
    meta: MCPMeta
    data: MCPServiceLookupData


class MCPInviteListItem(StrictModel):
    id: str
    code: str
    email: Optional[EmailStr] = None
    status: str
    created_at: datetime
    expires_at: datetime
    accepted_at: Optional[datetime] = None


class MCPInviteListData(StrictModel):
    invites: list[MCPInviteListItem]
    count: int
    next_cursor: Optional[str] = None


class MCPInviteListResponse(StrictModel):
    meta: MCPMeta
    data: MCPInviteListData


class MCPInviteStatusEvent(StrictModel):
    status: str
    timestamp: datetime


class MCPInviteDetailData(StrictModel):
    id: str
    code: str
    email: Optional[EmailStr] = None
    status: str
    created_at: datetime
    expires_at: datetime
    accepted_at: Optional[datetime] = None
    used_by_user_id: Optional[str] = None
    role: str
    grant_founding_status: bool
    metadata: Optional[dict[str, Any]] = None
    status_history: list[MCPInviteStatusEvent]


class MCPInviteDetailResponse(StrictModel):
    meta: MCPMeta
    data: MCPInviteDetailData
