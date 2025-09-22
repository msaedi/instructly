"""Schemas for referral-related endpoints and primitives."""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import AnyUrl, BaseModel, EmailStr, Field

from app.models.referrals import (
    ReferralCodeStatus,
    RewardSide,
    RewardStatus,
    WalletTransactionType,
)

from ._strict_base import StrictRequestModel


class ReferralSendRequest(StrictRequestModel):
    """Request payload for sending referral invites."""

    emails: List[EmailStr] = Field(..., description="List of recipient email addresses")
    referral_link: AnyUrl = Field(..., description="Referral link to include in the invite")
    from_name: Optional[str] = Field(
        default=None,
        description="Display name of the inviter (falls back to a generic label if omitted)",
    )


class ReferralSendError(BaseModel):
    """Details for a failed referral send attempt."""

    email: EmailStr
    error: str


class ReferralSendResponse(BaseModel):
    """Response after attempting to send referral invites."""

    status: str = Field(description="Operation status ('ok' if the operation ran)")
    sent: int = Field(description="Number of emails successfully sent")
    failed: int = Field(description="Number of emails that failed to send")
    errors: List[ReferralSendError] = Field(
        default_factory=list, description="List of errors for individual recipients"
    )


class ReferralCodeOut(BaseModel):
    """Serialized view of a referral code for API responses."""

    code: str
    vanity_slug: Optional[str] = None
    status: ReferralCodeStatus
    created_at: datetime


class RewardOut(BaseModel):
    """Serialized reward payload."""

    id: UUID
    side: RewardSide
    status: RewardStatus
    amount_cents: int
    unlock_ts: Optional[datetime] = None
    expire_ts: Optional[datetime] = None
    created_at: datetime


class WalletTxnOut(BaseModel):
    """Serialized wallet transaction payload."""

    id: UUID
    type: WalletTransactionType
    amount_cents: int
    created_at: datetime
    related_reward_id: Optional[UUID] = None
