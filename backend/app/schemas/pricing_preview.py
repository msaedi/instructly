"""Schemas for pricing preview API responses."""

from __future__ import annotations

from typing import List, Literal, Optional, TypedDict

from pydantic import BaseModel, Field, model_validator


class LineItem(BaseModel):
    label: str
    amount_cents: int = Field(ge=-(10**9), le=10**9)


class LineItemData(TypedDict):
    label: str
    amount_cents: int


class PricingPreviewOut(BaseModel):
    base_price_cents: int = Field(ge=0)
    student_fee_cents: int = Field(ge=0)
    instructor_platform_fee_cents: int = Field(ge=0)
    target_instructor_payout_cents: int = Field(ge=0)
    credit_applied_cents: int = Field(ge=0)
    student_pay_cents: int = Field(ge=0)
    application_fee_cents: int = Field(ge=0)
    top_up_transfer_cents: int = Field(ge=0)
    instructor_tier_pct: float = Field(ge=0, le=1)
    line_items: List[LineItem]


class PricingPreviewData(TypedDict):
    base_price_cents: int
    student_fee_cents: int
    instructor_platform_fee_cents: int
    target_instructor_payout_cents: int
    credit_applied_cents: int
    student_pay_cents: int
    application_fee_cents: int
    top_up_transfer_cents: int
    instructor_tier_pct: float
    line_items: List[LineItemData]


class PricingPreviewIn(BaseModel):
    instructor_id: str = Field(min_length=1)
    instructor_service_id: str = Field(min_length=1)
    booking_date: str = Field(min_length=1, pattern=r"^\d{4}-\d{2}-\d{2}$")
    start_time: str = Field(min_length=1, pattern=r"^\d{2}:\d{2}$")
    selected_duration: int = Field(gt=0)
    location_type: Literal[
        "student_location",
        "instructor_location",
        "online",
        "neutral_location",
    ]
    meeting_location: Optional[str] = None
    applied_credit_cents: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_location_requirements(self) -> "PricingPreviewIn":
        if self.location_type != "online":
            if not (self.meeting_location or "").strip():
                raise ValueError("meeting_location is required for non-online pricing previews")
        return self


__all__ = [
    "LineItem",
    "LineItemData",
    "PricingPreviewOut",
    "PricingPreviewData",
    "PricingPreviewIn",
]
