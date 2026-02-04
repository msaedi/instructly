"""Schemas for MCP admin booking actions."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class BookingState(BaseModel):
    status: str
    payment_status: str | None = None


class ForceCancelReasonCode(str, Enum):
    ADMIN_DISCRETION = "ADMIN_DISCRETION"
    INSTRUCTOR_NO_SHOW = "INSTRUCTOR_NO_SHOW"
    STUDENT_NO_SHOW = "STUDENT_NO_SHOW"
    DUPLICATE_BOOKING = "DUPLICATE_BOOKING"
    TECHNICAL_ISSUE = "TECHNICAL_ISSUE"
    DISPUTE_RESOLUTION = "DISPUTE_RESOLUTION"


class RefundPreference(str, Enum):
    FULL_CARD = "FULL_CARD"
    POLICY_BASED = "POLICY_BASED"
    NO_REFUND = "NO_REFUND"


class ForceCancelPreviewRequest(BaseModel):
    reason_code: ForceCancelReasonCode
    note: str = Field(..., min_length=1, max_length=2000)
    refund_preference: RefundPreference = RefundPreference.POLICY_BASED


class ForceCancelPreviewResponse(BaseModel):
    eligible: bool
    ineligible_reason: str | None = None
    current_state: BookingState
    will_cancel_booking: bool
    will_refund: bool
    refund_method: Literal["card", "credit", "none"] | None = None
    refund_amount: Decimal | None = None
    will_notify_student: bool
    will_notify_instructor: bool
    instructor_payout_impact: Decimal
    platform_fee_impact: Decimal
    warnings: list[str] = []
    confirm_token: str | None = None
    idempotency_key: str | None = None


class ForceCancelExecuteRequest(BaseModel):
    confirm_token: str
    idempotency_key: str


class ForceCancelExecuteResponse(BaseModel):
    success: bool
    error: str | None = None
    booking_id: str
    previous_status: str
    new_status: str
    refund_issued: bool
    refund_id: str | None = None
    refund_amount: Decimal | None = None
    refund_method: str | None = None
    notifications_sent: list[str]
    audit_id: str


class ForceCompleteReasonCode(str, Enum):
    LESSON_CONFIRMED_BY_BOTH = "LESSON_CONFIRMED_BY_BOTH"
    INSTRUCTOR_CONFIRMED = "INSTRUCTOR_CONFIRMED"
    STUDENT_CONFIRMED = "STUDENT_CONFIRMED"
    ADMIN_VERIFIED = "ADMIN_VERIFIED"


class ForceCompletePreviewRequest(BaseModel):
    reason_code: ForceCompleteReasonCode
    note: str = Field(..., min_length=1, max_length=2000)


class ForceCompletePreviewResponse(BaseModel):
    eligible: bool
    ineligible_reason: str | None = None
    current_state: BookingState
    will_mark_complete: bool
    will_capture_payment: bool
    capture_amount: Decimal | None = None
    instructor_payout: Decimal
    platform_fee: Decimal
    lesson_time_passed: bool
    hours_since_scheduled: float | None = None
    warnings: list[str] = []
    confirm_token: str | None = None
    idempotency_key: str | None = None


class ForceCompleteExecuteRequest(BaseModel):
    confirm_token: str
    idempotency_key: str


class ForceCompleteExecuteResponse(BaseModel):
    success: bool
    error: str | None = None
    booking_id: str
    previous_status: str
    new_status: str
    payment_captured: bool
    capture_amount: Decimal | None = None
    instructor_payout_scheduled: bool
    payout_amount: Decimal | None = None
    audit_id: str


class NotificationType(str, Enum):
    BOOKING_CONFIRMATION = "booking_confirmation"
    LESSON_REMINDER_24H = "lesson_reminder_24h"
    LESSON_REMINDER_1H = "lesson_reminder_1h"
    LESSON_COMPLETED = "lesson_completed"
    CANCELLATION_NOTICE = "cancellation_notice"


class NotificationRecipient(str, Enum):
    STUDENT = "student"
    INSTRUCTOR = "instructor"
    BOTH = "both"


class ResendNotificationRequest(BaseModel):
    notification_type: NotificationType
    recipient: NotificationRecipient = NotificationRecipient.STUDENT
    note: str = Field(..., min_length=1, max_length=2000)


class NotificationSent(BaseModel):
    recipient: str
    channel: str
    template: str
    sent_at: datetime


class ResendNotificationResponse(BaseModel):
    success: bool
    error: str | None = None
    notifications_sent: list[NotificationSent]
    audit_id: str


class NoteVisibility(str, Enum):
    INTERNAL = "internal"
    SHARED_WITH_INSTRUCTOR = "shared_with_instructor"
    SHARED_WITH_STUDENT = "shared_with_student"


class NoteCategory(str, Enum):
    SUPPORT_INTERACTION = "support_interaction"
    DISPUTE = "dispute"
    FRAUD_FLAG = "fraud_flag"
    QUALITY_ISSUE = "quality_issue"
    GENERAL = "general"


class AddNoteRequest(BaseModel):
    note: str = Field(..., min_length=1, max_length=2000)
    visibility: NoteVisibility = NoteVisibility.INTERNAL
    category: NoteCategory = NoteCategory.GENERAL


class AddNoteResponse(BaseModel):
    success: bool
    note_id: str
    created_at: datetime
    audit_id: str
