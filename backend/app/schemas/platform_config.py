"""Schemas for public platform configuration."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class PlatformFees(BaseModel):
    founding_instructor: float = Field(
        ..., gt=0, lt=1, description="Platform fee for founding instructors"
    )
    tier_1: float = Field(..., gt=0, lt=1, description="Entry tier platform fee")
    tier_2: float = Field(..., gt=0, lt=1, description="Second tier platform fee")
    tier_3: float = Field(..., gt=0, lt=1, description="Third tier platform fee")
    student_booking_fee: float = Field(
        ..., gt=0, lt=1, description="Student booking protection fee"
    )


class PublicConfigResponse(BaseModel):
    fees: PlatformFees
    updated_at: Optional[datetime] = None
