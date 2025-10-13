"""Schemas for pricing preview API responses."""

from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field


class LineItem(BaseModel):
    label: str
    amount_cents: int = Field(ge=-(10**9), le=10**9)


class PricingPreviewOut(BaseModel):
    base_price_cents: int = Field(ge=0)
    student_fee_cents: int = Field(ge=0)
    instructor_commission_cents: int = Field(ge=0)
    target_instructor_payout_cents: int = Field(ge=0)
    credit_applied_cents: int = Field(ge=0)
    student_pay_cents: int = Field(ge=0)
    application_fee_cents: int = Field(ge=0)
    top_up_transfer_cents: int = Field(ge=0)
    instructor_tier_pct: float = Field(ge=0, le=1)
    line_items: List[LineItem]


__all__ = ["LineItem", "PricingPreviewOut"]
