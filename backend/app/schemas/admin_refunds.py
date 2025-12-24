"""Schemas for admin refund endpoints."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class AdminRefundReason(str, Enum):
    INSTRUCTOR_NO_SHOW = "instructor_no_show"
    DISPUTE = "dispute"
    PLATFORM_ERROR = "platform_error"
    OTHER = "other"


class AdminRefundRequest(BaseModel):
    amount_cents: Optional[int] = Field(
        None,
        description="Refund amount in cents. Full refund if not provided.",
        gt=0,
    )
    reason: AdminRefundReason = Field(..., description="Reason for refund")
    note: Optional[str] = Field(
        None,
        max_length=1000,
        description="Admin note explaining the refund",
    )


class AdminRefundResponse(BaseModel):
    success: bool
    refund_id: str
    amount_refunded_cents: int
    booking_id: str
    booking_status: str
    message: str
