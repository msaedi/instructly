"""Schemas for MCP admin refund preview/execute workflow."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel


class RefundReasonCode(str, Enum):
    CANCEL_POLICY = "CANCEL_POLICY"
    GOODWILL = "GOODWILL"
    DUPLICATE = "DUPLICATE"
    DISPUTE_PREVENTION = "DISPUTE_PREVENTION"
    INSTRUCTOR_NO_SHOW = "INSTRUCTOR_NO_SHOW"
    SERVICE_ISSUE = "SERVICE_ISSUE"


class RefundAmountType(str, Enum):
    FULL = "full"
    PARTIAL = "partial"


class RefundAmount(BaseModel):
    type: RefundAmountType
    value: float | None = None


class RefundPreviewRequest(BaseModel):
    booking_id: str
    reason_code: RefundReasonCode
    amount: RefundAmount
    note: str | None = None


class RefundExecuteRequest(BaseModel):
    confirm_token: str
    idempotency_key: str


class RefundMeta(BaseModel):
    generated_at: datetime
    booking_id: str
    reason_code: str


class OriginalPayment(BaseModel):
    gross: float
    platform_fee: float
    instructor_payout: float
    status: str
    captured_at: datetime | None


class RefundImpact(BaseModel):
    refund_method: str
    student_card_refund: float
    student_credit_issued: float
    instructor_payout_delta: float
    platform_fee_refunded: float
    original_payment: OriginalPayment


class RefundPreviewResponse(BaseModel):
    meta: RefundMeta
    eligible: bool
    ineligible_reason: str | None = None
    policy_basis: str
    impact: RefundImpact
    warnings: list[str] = []
    confirm_token: str | None = None
    idempotency_key: str | None = None
    token_expires_at: datetime | None = None


class RefundExecuteMeta(BaseModel):
    executed_at: datetime
    booking_id: str
    idempotency_key: str


class RefundResult(BaseModel):
    status: str
    amount: float
    method: str
    stripe_refund_id: str | None


class UpdatedBooking(BaseModel):
    id: str
    status: str
    updated_at: datetime


class UpdatedPayment(BaseModel):
    status: str
    refunded_at: datetime


class RefundExecuteResponse(BaseModel):
    meta: RefundExecuteMeta
    result: str
    error: str | None = None
    refund: RefundResult | None = None
    updated_booking: UpdatedBooking | None = None
    updated_payment: UpdatedPayment | None = None
    audit_id: str
