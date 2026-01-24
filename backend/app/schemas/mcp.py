"""Schemas for MCP admin responses."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from ._strict_base import StrictModel


class MCPActor(StrictModel):
    id: str
    email: str


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
