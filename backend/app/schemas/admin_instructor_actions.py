"""Schemas for MCP admin instructor actions."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field


class SuspendReasonCode(str, Enum):
    FRAUD = "FRAUD"
    POLICY_VIOLATION = "POLICY_VIOLATION"
    SAFETY_CONCERN = "SAFETY_CONCERN"
    QUALITY_ISSUES = "QUALITY_ISSUES"
    BGC_FAILURE = "BGC_FAILURE"
    PAYMENT_FRAUD = "PAYMENT_FRAUD"
    IDENTITY_MISMATCH = "IDENTITY_MISMATCH"
    TEMPORARY_REVIEW = "TEMPORARY_REVIEW"


class InstructorState(BaseModel):
    account_status: str
    is_verified: bool
    is_founding: bool


class SuspendPreviewRequest(BaseModel):
    reason_code: SuspendReasonCode
    note: str = Field(..., min_length=1, max_length=2000)
    notify_instructor: bool = True
    cancel_pending_bookings: bool = True


class SuspendPreviewResponse(BaseModel):
    eligible: bool
    ineligible_reason: str | None = None
    current_state: InstructorState
    pending_bookings_count: int
    pending_bookings_value: Decimal
    pending_payout_amount: Decimal
    active_conversations: int
    will_suspend: bool
    will_cancel_bookings: bool
    will_refund_students: bool
    will_hold_payouts: bool
    will_notify_instructor: bool
    will_notify_affected_students: bool
    warnings: list[str] = []
    confirm_token: str | None = None
    idempotency_key: str | None = None


class SuspendExecuteRequest(BaseModel):
    confirm_token: str
    idempotency_key: str


class SuspendExecuteResponse(BaseModel):
    success: bool
    error: str | None = None
    instructor_id: str
    previous_status: str
    new_status: str
    bookings_cancelled: int
    refunds_issued: int
    total_refunded: Decimal
    notifications_sent: list[str]
    audit_id: str


class UnsuspendRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=2000)
    restore_visibility: bool = True


class UnsuspendResponse(BaseModel):
    success: bool
    error: str | None = None
    instructor_id: str
    previous_status: str
    new_status: str
    visibility_restored: bool
    payout_hold_released: bool
    audit_id: str


class VerificationType(str, Enum):
    IDENTITY = "IDENTITY"
    BACKGROUND_CHECK = "BACKGROUND_CHECK"
    PAYMENT_SETUP = "PAYMENT_SETUP"
    FULL = "FULL"


class VerifyOverrideRequest(BaseModel):
    instructor_id: str | None = None
    verification_type: VerificationType
    reason: str = Field(..., min_length=1, max_length=2000)
    evidence: str | None = Field(default=None, max_length=2000)


class VerifyOverrideResponse(BaseModel):
    success: bool
    error: str | None = None
    instructor_id: str
    verification_type: str
    previous_status: dict[str, bool]
    new_status: dict[str, bool]
    now_fully_verified: bool
    search_eligible: bool
    audit_id: str


class CommissionAction(str, Enum):
    SET_TIER = "SET_TIER"
    GRANT_FOUNDING = "GRANT_FOUNDING"
    REVOKE_FOUNDING = "REVOKE_FOUNDING"
    TEMPORARY_DISCOUNT = "TEMPORARY_DISCOUNT"


class CommissionTier(str, Enum):
    ENTRY = "entry"
    GROWTH = "growth"
    PRO = "pro"
    FOUNDING = "founding"


class UpdateCommissionPreviewRequest(BaseModel):
    action: CommissionAction
    tier: CommissionTier | None = None
    temporary_rate: Decimal | None = None
    temporary_until: datetime | None = None
    reason: str = Field(..., min_length=1, max_length=2000)


class UpdateCommissionPreviewResponse(BaseModel):
    eligible: bool
    ineligible_reason: str | None = None
    current_tier: str
    current_rate: Decimal
    is_founding: bool
    new_tier: str
    new_rate: Decimal
    will_be_founding: bool
    rate_change: Decimal
    estimated_monthly_impact: Decimal
    warnings: list[str] = []
    confirm_token: str | None = None
    idempotency_key: str | None = None


class UpdateCommissionExecuteRequest(BaseModel):
    confirm_token: str
    idempotency_key: str


class UpdateCommissionExecuteResponse(BaseModel):
    success: bool
    error: str | None = None
    instructor_id: str
    previous_tier: str
    new_tier: str
    previous_rate: Decimal
    new_rate: Decimal
    founding_status_changed: bool
    audit_id: str


class PayoutHoldAction(str, Enum):
    HOLD = "HOLD"
    RELEASE = "RELEASE"


class PayoutHoldRequest(BaseModel):
    action: PayoutHoldAction
    reason: str = Field(..., min_length=1, max_length=2000)


class PayoutHoldResponse(BaseModel):
    success: bool
    error: str | None = None
    instructor_id: str
    action: str
    held_amount: Decimal
    pending_payouts: int
    audit_id: str
