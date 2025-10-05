"""Schemas for referral-related endpoints and primitives."""

from datetime import datetime
from typing import Dict, List, Optional
from uuid import UUID

from pydantic import AnyUrl, BaseModel, ConfigDict, EmailStr, Field

from app.models.referrals import (
    ReferralCodeStatus,
    RewardSide,
    RewardStatus,
    WalletTransactionType,
)

from ._strict_base import StrictModel, StrictRequestModel


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


class ReferralSendResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
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


class ReferralClaimRequest(StrictRequestModel):
    code: str


class ReferralClaimResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    attributed: bool
    reason: Optional[str] = None


class ReferralLedgerResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    code: str
    share_url: str
    pending: List[RewardOut]
    unlocked: List[RewardOut]
    redeemed: List[RewardOut]
    expiry_notice_days: List[int]


class CheckoutApplyRequest(StrictRequestModel):
    order_id: str


class CheckoutApplyResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    applied_cents: int


class ReferralErrorResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    """Standard error envelope for referral endpoints."""

    reason: str


class ReferralResolveResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    """Response payload when resolving referral slugs as JSON."""

    ok: bool
    code: str
    redirect: str


class TopReferrerOut(BaseModel):
    """Top referrer metadata for admin dashboards."""

    user_id: UUID
    count: int
    code: Optional[str] = None


class AdminReferralsConfigOut(BaseModel):
    """Configuration snapshot for the referral program."""

    student_amount_cents: int
    instructor_amount_cents: int
    min_basket_cents: int
    hold_days: int
    expiry_months: int
    global_cap: int
    flags: Dict[str, bool]


class AdminReferralsSummaryOut(BaseModel):
    """Aggregate referral summary metrics for admins."""

    counts_by_status: Dict[str, int]
    cap_utilization_percent: float
    top_referrers: List[TopReferrerOut]
    clicks_24h: int
    attributions_24h: int


class AdminReferralsHealthOut(BaseModel):
    """Unlocker worker and data health for admin dashboards."""

    workers_alive: int
    workers: List[str]
    backlog_pending_due: int
    pending_total: int
    unlocked_total: int
    void_total: int
