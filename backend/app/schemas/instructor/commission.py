from typing import List

from pydantic import Field

from .._strict_base import StrictModel


class TierInfo(StrictModel):
    """Instructor tier metadata for commission ladder display."""

    name: str = Field(..., description='Tier key: "entry", "growth", or "pro"')
    display_name: str = Field(..., description="Human-readable tier label")
    commission_pct: float = Field(..., description="Commission percentage as whole percent")
    min_lessons: int = Field(..., ge=0, description="Minimum completed lessons for this tier")
    max_lessons: int | None = Field(
        default=None,
        ge=0,
        description="Maximum completed lessons for this tier; null for open-ended tiers",
    )
    is_current: bool = Field(
        default=False, description="Whether this is the displayed current tier"
    )
    is_unlocked: bool = Field(
        default=False,
        description="Whether the instructor has unlocked this tier based on recent lesson volume",
    )


class CommissionStatusResponse(StrictModel):
    """Instructor-facing commission tier status."""

    is_founding: bool = Field(default=False)
    tier_name: str = Field(
        ..., description='Current display tier: "founding", "entry", "growth", or "pro"'
    )
    commission_rate_pct: float = Field(..., description="Commission percentage as whole percent")
    activity_window_days: int = Field(
        ..., ge=1, description="Configured activity window length used for tier progress"
    )
    completed_lessons_30d: int = Field(
        ..., ge=0, description="Completed lessons in the configured activity window"
    )
    next_tier_name: str | None = Field(
        default=None,
        description="Next tier key for progress display; null for founding and pro",
    )
    next_tier_threshold: int | None = Field(
        default=None,
        ge=0,
        description="Completed lesson threshold needed to unlock the next tier",
    )
    lessons_to_next_tier: int | None = Field(
        default=None,
        ge=0,
        description="Remaining lessons needed to unlock the next tier",
    )
    tiers: List["TierInfo"] = Field(default_factory=list, description="Entry/Growth/Pro ladder")
