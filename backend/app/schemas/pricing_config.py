"""Pydantic schemas for pricing configuration."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, PositiveInt, model_validator


class TierConfig(BaseModel):
    min: int = Field(..., ge=0, description="Minimum completed sessions for this tier")
    max: Optional[int] = Field(
        None,
        ge=0,
        description="Maximum sessions for this tier (inclusive); null for open-ended",
    )
    pct: float = Field(..., gt=0, lt=1, description="Commission percentage expressed as decimal")

    @model_validator(mode="after")
    def validate_bounds(self) -> "TierConfig":
        if self.max is not None and self.max < self.min:
            raise ValueError("Tier max must be greater than or equal to min")
        return self


class PriceFloorConfig(BaseModel):
    private_in_person: int = Field(
        ..., ge=0, description="Minimum cents for in-person private lessons"
    )
    private_remote: int = Field(..., ge=0, description="Minimum cents for remote private lessons")


class StudentCreditCycle(BaseModel):
    cycle_len: PositiveInt = Field(..., description="Length of credit cycle in sessions")
    mod10: int = Field(..., ge=0, description="Modulo offset for $10 credit milestone")
    cents10: int = Field(..., ge=0, description="Credit cents issued for $10 milestone")
    mod20: int = Field(..., ge=0, description="Modulo offset for $20 credit milestone")
    cents20: int = Field(..., ge=0, description="Credit cents issued for $20 milestone")


class PricingConfig(BaseModel):
    student_fee_pct: float = Field(
        ..., gt=0, lt=1, description="Student booking protection fee as decimal"
    )
    founding_instructor_rate_pct: float = Field(
        0.08,
        gt=0,
        lt=1,
        description="Platform fee percentage for founding instructors",
    )
    founding_instructor_cap: PositiveInt = Field(
        100, description="Maximum number of founding instructors"
    )
    founding_search_boost: float = Field(
        1.5,
        gt=0,
        description="Search ranking multiplier for founding instructors",
    )
    instructor_tiers: List[TierConfig]
    tier_activity_window_days: PositiveInt = Field(
        ..., description="Rolling window for tier activity"
    )
    tier_stepdown_max: int = Field(..., ge=0, description="Maximum tiers to drop per evaluation")
    tier_inactivity_reset_days: PositiveInt = Field(
        ..., description="Inactivity period before full reset"
    )
    price_floor_cents: PriceFloorConfig
    student_credit_cycle: StudentCreditCycle

    @model_validator(mode="after")
    def validate_tiers(self) -> "PricingConfig":
        if not self.instructor_tiers:
            raise ValueError("At least one instructor tier must be defined")
        sorted_tiers = sorted(self.instructor_tiers, key=lambda tier: tier.min)
        for idx, tier in enumerate(sorted_tiers):
            if idx > 0:
                prev = sorted_tiers[idx - 1]
                if tier.min <= prev.min:
                    raise ValueError("Instructor tiers must have strictly increasing minimums")
                if prev.max is not None and tier.min <= prev.max:
                    raise ValueError("Instructor tiers may not overlap")
        return self


class PricingConfigResponse(BaseModel):
    config: PricingConfig
    updated_at: Optional[datetime] = None


class PricingConfigPayload(PricingConfig):
    """Alias for request payload compatibility."""

    pass
