"""Schemas for admin booking and payments endpoints."""

from __future__ import annotations

from datetime import date, datetime, time
from enum import Enum
from typing import Any, Optional

from pydantic import Field

from ._strict_base import StrictModel, StrictRequestModel


class AdminBookingPerson(StrictModel):
    id: str
    name: str
    email: str
    phone: Optional[str] = None


class AdminBookingListItem(StrictModel):
    id: str
    student: AdminBookingPerson
    instructor: AdminBookingPerson
    service_name: str
    booking_date: date
    start_time: time
    end_time: time
    total_price: float
    status: str
    payment_status: Optional[str] = None
    payment_intent_id: Optional[str] = None
    created_at: Optional[datetime] = None


class AdminBookingListResponse(StrictModel):
    bookings: list[AdminBookingListItem]
    total: int
    page: int
    per_page: int
    total_pages: int


class AdminBookingServiceInfo(StrictModel):
    id: Optional[str] = None
    name: str
    duration_minutes: int
    hourly_rate: float


class AdminBookingPaymentInfo(StrictModel):
    total_price: float
    lesson_price: float
    platform_fee: float
    credits_applied: float
    payment_status: Optional[str] = None
    payment_intent_id: Optional[str] = None
    instructor_payout: float
    platform_revenue: float
    stripe_url: Optional[str] = None


class AdminBookingTimelineEvent(StrictModel):
    timestamp: datetime
    event: str
    amount: Optional[float] = None


class AdminBookingDetailResponse(StrictModel):
    id: str
    student: AdminBookingPerson
    instructor: AdminBookingPerson
    service: AdminBookingServiceInfo
    booking_date: date
    start_time: time
    end_time: time
    location_type: Optional[str] = None
    meeting_location: Optional[str] = None
    student_note: Optional[str] = None
    instructor_note: Optional[str] = None
    status: str
    payment: AdminBookingPaymentInfo
    timeline: list[AdminBookingTimelineEvent]
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class AdminBookingStatsToday(StrictModel):
    booking_count: int
    revenue: float


class AdminBookingStatsWeek(StrictModel):
    gmv: float
    platform_revenue: float


class AdminBookingStatsNeedsAction(StrictModel):
    pending_completion: int
    disputed: int


class AdminBookingStatsResponse(StrictModel):
    today: AdminBookingStatsToday
    this_week: AdminBookingStatsWeek
    needs_action: AdminBookingStatsNeedsAction


class AdminAuditActor(StrictModel):
    id: str
    email: str


class AdminAuditEntry(StrictModel):
    id: str
    timestamp: datetime
    admin: AdminAuditActor
    action: str
    resource_type: str
    resource_id: str
    details: Optional[dict[str, Any]] = None


class AdminAuditLogSummary(StrictModel):
    refunds_count: int
    refunds_total: float
    captures_count: int
    captures_total: float


class AdminAuditLogResponse(StrictModel):
    entries: list[AdminAuditEntry]
    summary: AdminAuditLogSummary
    total: int
    page: int
    per_page: int
    total_pages: int


class AdminCancelBookingRequest(StrictRequestModel):
    reason: str = Field(..., max_length=100)
    note: Optional[str] = Field(None, max_length=1000)
    refund: bool = False


class AdminCancelBookingResponse(StrictModel):
    success: bool
    booking_id: str
    booking_status: str
    refund_issued: bool
    refund_id: Optional[str] = None


class AdminBookingStatusUpdate(str, Enum):
    COMPLETED = "COMPLETED"
    NO_SHOW = "NO_SHOW"


class AdminBookingStatusUpdateRequest(StrictRequestModel):
    status: AdminBookingStatusUpdate
    note: Optional[str] = Field(None, max_length=1000)


class AdminBookingStatusUpdateResponse(StrictModel):
    success: bool
    booking_id: str
    booking_status: str


__all__ = [
    "AdminAuditEntry",
    "AdminAuditLogResponse",
    "AdminAuditLogSummary",
    "AdminAuditActor",
    "AdminBookingDetailResponse",
    "AdminBookingListItem",
    "AdminBookingListResponse",
    "AdminBookingPaymentInfo",
    "AdminBookingPerson",
    "AdminBookingServiceInfo",
    "AdminBookingStatsNeedsAction",
    "AdminBookingStatsResponse",
    "AdminBookingStatsToday",
    "AdminBookingStatsWeek",
    "AdminBookingTimelineEvent",
    "AdminBookingStatusUpdate",
    "AdminBookingStatusUpdateRequest",
    "AdminBookingStatusUpdateResponse",
    "AdminCancelBookingRequest",
    "AdminCancelBookingResponse",
]
