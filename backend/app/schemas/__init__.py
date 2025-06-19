"""
Pydantic schemas for InstaInstru platform.

This module exports all request/response schemas used in the API.
Schemas are organized by functionality for better maintainability.
"""

# Availability schemas
from .availability import DateTimeSlot  # Legacy, kept for API compatibility
from .availability import (
    ApplyToDateRangeRequest,
    AvailabilityQuery,
    AvailabilitySlot,
    AvailabilitySlotBase,
    AvailabilitySlotCreate,
    CopyWeekRequest,
    InstructorAvailability,
    InstructorAvailabilityBase,
    InstructorAvailabilityCreate,
    InstructorAvailabilityUpdate,
    WeekScheduleCreate,
)

# Availability window schemas
from .availability_window import (
    AvailabilityWindowBase,
    AvailabilityWindowResponse,
    AvailabilityWindowUpdate,
    BlackoutDateCreate,
    BlackoutDateResponse,
    DayOfWeekEnum,
    SpecificDateAvailabilityCreate,
    WeekSpecificScheduleCreate,
)
from .booking import (
    AvailabilityCheckRequest,
    AvailabilityCheckResponse,
    BookingCancel,
    BookingCreate,
    BookingListResponse,
    BookingResponse,
    BookingStatsResponse,
    BookingStatus,
    BookingUpdate,
    UpcomingBookingResponse,
)

# Instructor profile schemas
from .instructor import (
    InstructorProfileBase,
    InstructorProfileCreate,
    InstructorProfileResponse,
    InstructorProfileUpdate,
    ServiceBase,
    ServiceCreate,
    ServiceResponse,
)

# Password reset schemas
from .password_reset import PasswordResetConfirm, PasswordResetRequest, PasswordResetResponse

# User and authentication schemas
from .user import Token, UserCreate, UserLogin, UserResponse, UserRole

__all__ = [
    # User schemas
    "UserCreate",
    "UserLogin",
    "UserResponse",
    "Token",
    "UserRole",
    # Instructor schemas
    "InstructorProfileBase",
    "InstructorProfileCreate",
    "InstructorProfileUpdate",
    "InstructorProfileResponse",
    "ServiceBase",
    "ServiceCreate",
    "ServiceResponse",
    # Availability schemas
    "AvailabilitySlotBase",
    "AvailabilitySlotCreate",
    "AvailabilitySlot",
    "InstructorAvailabilityBase",
    "InstructorAvailabilityCreate",
    "InstructorAvailabilityUpdate",
    "InstructorAvailability",
    "DateTimeSlot",
    "WeekScheduleCreate",
    "CopyWeekRequest",
    "ApplyToDateRangeRequest",
    "AvailabilityQuery",
    # Availability window schemas
    "AvailabilityWindowBase",
    "AvailabilityWindowUpdate",
    "AvailabilityWindowResponse",
    "SpecificDateAvailabilityCreate",
    "WeekSpecificScheduleCreate",
    "BlackoutDateCreate",
    "BlackoutDateResponse",
    "DayOfWeekEnum",
    # Password reset schemas
    "PasswordResetRequest",
    "PasswordResetConfirm",
    "PasswordResetResponse",
    # Booking schemas
    "BookingCreate",
    "BookingUpdate",
    "BookingCancel",
    "BookingResponse",
    "BookingListResponse",
    "AvailabilityCheckRequest",
    "AvailabilityCheckResponse",
    "BookingStatsResponse",
    "UpcomingBookingResponse",
    "BookingStatus",
]
