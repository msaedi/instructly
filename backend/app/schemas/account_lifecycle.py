# backend/app/schemas/account_lifecycle.py
"""
Schemas for account lifecycle management.

Handles request/response models for instructor account status changes.
"""

from typing import List, Optional

from pydantic import BaseModel


class AccountStatusChangeResponse(BaseModel):
    """Response for account status change operations."""

    success: bool
    message: str
    previous_status: str
    new_status: str


class AccountStatusResponse(BaseModel):
    """Response for account status check endpoint."""

    user_id: str
    role: str
    account_status: str
    can_login: bool
    can_receive_bookings: bool
    is_active: bool
    is_suspended: bool
    is_deactivated: bool
    has_future_bookings: Optional[bool] = None
    future_bookings_count: Optional[int] = None
    can_suspend: Optional[bool] = None
    can_deactivate: Optional[bool] = None
    can_reactivate: Optional[bool] = None


class FutureBookingInfo(BaseModel):
    """Information about a future booking that blocks status change."""

    booking_id: str
    booking_date: str
    start_time: str
    end_time: str
    student_first_name: str
    student_last_name: str
    service_name: str


class AccountStatusError(BaseModel):
    """Error response for account status operations."""

    detail: str
    future_bookings: Optional[List[FutureBookingInfo]] = None
