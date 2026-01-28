"""Schemas for MCP Admin Operations responses."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from ._strict_base import StrictModel

# ==================== Booking Summary ====================


class TopCategory(StrictModel):
    """A category with booking count."""

    category: str
    count: int


class BookingSummary(StrictModel):
    """Summary statistics for bookings in a time period."""

    period: str
    total_bookings: int
    by_status: dict[str, int]
    total_revenue_cents: int
    avg_booking_value_cents: int
    new_students: int
    repeat_students: int
    top_categories: list[TopCategory]


class BookingSummaryResponse(StrictModel):
    """Response for booking summary endpoint."""

    summary: BookingSummary
    checked_at: datetime


# ==================== Recent Bookings ====================


class BookingListItem(StrictModel):
    """A booking in a list view with privacy-safe names."""

    booking_id: str
    status: str
    booking_date: str
    start_time: str
    end_time: str
    student_name: str  # "John S." format
    instructor_name: str  # "Sarah C." format
    service_name: str
    category: str
    total_cents: int
    location_type: str
    created_at: str


class RecentBookingsResponse(StrictModel):
    """Response for recent bookings endpoint."""

    bookings: list[BookingListItem]
    count: int
    filters_applied: dict[str, Any]
    checked_at: datetime


# ==================== Payment Pipeline ====================


class PaymentPipelineResponse(StrictModel):
    """Response for payment pipeline status endpoint."""

    # Current state counts
    pending_authorization: int
    authorized: int
    pending_capture: int
    captured: int
    failed: int
    refunded: int

    # Alerts
    overdue_authorizations: int
    overdue_captures: int

    # Revenue (last 7 days)
    total_captured_cents: int
    total_refunded_cents: int
    net_revenue_cents: int

    # Platform fees
    platform_fees_cents: int
    instructor_payouts_cents: int

    checked_at: datetime


# ==================== Pending Payouts ====================


class PendingPayoutItem(StrictModel):
    """An instructor with pending payout."""

    instructor_id: str
    instructor_name: str  # "Sarah C." format
    pending_amount_cents: int
    completed_lessons: int
    oldest_pending_date: str
    stripe_connected: bool


class PendingPayoutsResponse(StrictModel):
    """Response for pending payouts endpoint."""

    payouts: list[PendingPayoutItem]
    total_pending_cents: int
    instructor_count: int
    checked_at: datetime


# ==================== User Lookup ====================


class UserInfo(StrictModel):
    """User information for admin lookup."""

    user_id: str
    email: str
    name: str  # Full name OK for admin
    role: str
    created_at: str
    last_login: Optional[str] = None
    is_verified: bool
    is_founding: bool
    total_bookings: int
    total_spent_cents: int
    stripe_customer_id: Optional[str] = None
    phone: Optional[str] = None

    # Instructor-specific fields
    instructor_status: Optional[str] = None
    total_lessons: Optional[int] = None
    total_earned_cents: Optional[int] = None
    rating: Optional[float] = None
    review_count: Optional[int] = None
    stripe_account_id: Optional[str] = None


class UserLookupResponse(StrictModel):
    """Response for user lookup endpoint."""

    found: bool
    user: Optional[UserInfo] = None
    checked_at: datetime


# ==================== User Booking History ====================


class UserBookingHistoryResponse(StrictModel):
    """Response for user booking history endpoint."""

    user_id: str
    user_name: str
    user_role: str
    bookings: list[BookingListItem]
    total_count: int
    checked_at: datetime
