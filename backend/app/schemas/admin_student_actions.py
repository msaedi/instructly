"""Schemas for MCP admin student actions."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field


class StudentSuspendReasonCode(str, Enum):
    FRAUD = "FRAUD"
    ABUSE = "ABUSE"
    PAYMENT_FRAUD = "PAYMENT_FRAUD"
    POLICY_VIOLATION = "POLICY_VIOLATION"
    MULTIPLE_NO_SHOWS = "MULTIPLE_NO_SHOWS"
    HARASSMENT = "HARASSMENT"


class StudentState(BaseModel):
    account_status: str
    credit_balance: Decimal
    is_restricted: bool


class StudentSuspendPreviewRequest(BaseModel):
    reason_code: StudentSuspendReasonCode
    note: str = Field(..., min_length=1, max_length=2000)
    notify_student: bool = True
    cancel_pending_bookings: bool = True
    forfeit_credits: bool = False


class StudentSuspendPreviewResponse(BaseModel):
    eligible: bool
    ineligible_reason: str | None = None
    current_state: StudentState
    pending_bookings_count: int
    pending_bookings_value: Decimal
    credit_balance: Decimal
    active_conversations: int
    will_suspend: bool
    will_cancel_bookings: bool
    will_refund_students: bool
    will_forfeit_credits: bool
    will_notify_student: bool
    will_notify_affected_instructors: bool
    warnings: list[str] = []
    confirm_token: str | None = None
    idempotency_key: str | None = None


class StudentSuspendExecuteRequest(BaseModel):
    confirm_token: str
    idempotency_key: str


class StudentSuspendExecuteResponse(BaseModel):
    success: bool
    error: str | None = None
    student_id: str
    previous_status: str
    new_status: str
    bookings_cancelled: int
    refunds_issued: int
    total_refunded: Decimal
    credits_forfeited: Decimal
    notifications_sent: list[str]
    audit_id: str


class StudentUnsuspendRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=2000)
    restore_credits: bool = True


class StudentUnsuspendResponse(BaseModel):
    success: bool
    error: str | None = None
    student_id: str
    previous_status: str
    new_status: str
    credits_restored: Decimal
    audit_id: str


class CreditAdjustAction(str, Enum):
    ADD = "ADD"
    REMOVE = "REMOVE"
    SET = "SET"


class CreditAdjustReasonCode(str, Enum):
    GOODWILL = "GOODWILL"
    COMPENSATION = "COMPENSATION"
    PROMOTIONAL = "PROMOTIONAL"
    CORRECTION = "CORRECTION"
    REFERRAL_BONUS = "REFERRAL_BONUS"
    REFUND_CONVERSION = "REFUND_CONVERSION"
    FRAUD_RECOVERY = "FRAUD_RECOVERY"


class CreditAdjustPreviewRequest(BaseModel):
    action: CreditAdjustAction
    amount: Decimal
    reason_code: CreditAdjustReasonCode
    note: str | None = Field(default=None, max_length=2000)
    expires_at: datetime | None = None


class CreditAdjustPreviewResponse(BaseModel):
    eligible: bool
    ineligible_reason: str | None = None
    current_balance: Decimal
    new_balance: Decimal
    delta: Decimal
    will_create_credit: bool
    will_remove_credit: bool
    warnings: list[str] = []
    confirm_token: str | None = None
    idempotency_key: str | None = None


class CreditAdjustExecuteRequest(BaseModel):
    confirm_token: str
    idempotency_key: str


class CreditAdjustExecuteResponse(BaseModel):
    success: bool
    error: str | None = None
    student_id: str
    previous_balance: Decimal
    new_balance: Decimal
    delta: Decimal
    credits_created: int
    credits_revoked: int
    audit_id: str


class CreditHistoryEntry(BaseModel):
    credit_id: str
    amount: Decimal
    status: str
    reason: str
    source_type: str
    created_at: datetime
    expires_at: datetime | None = None
    used_at: datetime | None = None
    forfeited_at: datetime | None = None
    revoked_at: datetime | None = None
    reserved_amount: Decimal | None = None
    reserved_for_booking_id: str | None = None


class CreditHistorySummary(BaseModel):
    total_earned: Decimal
    total_spent: Decimal
    total_expired: Decimal
    total_forfeited: Decimal
    available_balance: Decimal
    reserved_balance: Decimal


class CreditHistoryResponse(BaseModel):
    include_expired: bool
    credits: list[CreditHistoryEntry]
    summary: CreditHistorySummary


class RefundHistoryEntry(BaseModel):
    booking_id: str
    amount: Decimal
    method: str
    status: str | None = None
    refunded_at: datetime | None = None


class RefundHistorySummary(BaseModel):
    total_card_refunds: Decimal
    total_credit_refunds: Decimal
    total_refunds: Decimal
    refund_count: int


class RefundFraudFlags(BaseModel):
    refund_rate: float
    high_refund_rate: bool
    rapid_refunds: bool
    high_refund_amount: bool
    refunds_last_7_days: int
    refunds_last_30_days: int


class RefundHistoryResponse(BaseModel):
    refunds: list[RefundHistoryEntry]
    summary: RefundHistorySummary
    fraud_flags: RefundFraudFlags
