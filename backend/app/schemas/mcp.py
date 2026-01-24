"""Schemas for MCP admin responses."""

from __future__ import annotations

from datetime import datetime
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
