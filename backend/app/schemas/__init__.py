"""
Pydantic schemas for InstaInstru platform.

This module exports all request/response schemas used in the API.
Schemas are organized by functionality for better maintainability.
"""

# User and authentication schemas
from .user import UserCreate, UserLogin, UserResponse, Token, UserRole

# Instructor profile schemas
from .instructor import (
    InstructorProfileBase, 
    InstructorProfileCreate, 
    InstructorProfileUpdate, 
    InstructorProfileResponse,
    ServiceBase,
    ServiceCreate,
    ServiceResponse
)

# Availability schemas
from .availability import (
    AvailabilitySlotBase,
    AvailabilitySlotCreate,
    AvailabilitySlot,
    InstructorAvailabilityBase,
    InstructorAvailabilityCreate,
    InstructorAvailabilityUpdate,
    InstructorAvailability,
    DateTimeSlot,  # Legacy, kept for API compatibility
    WeekScheduleCreate,
    CopyWeekRequest,
    ApplyToDateRangeRequest,
    AvailabilityQuery
)

# Availability window schemas
from .availability_window import (
    AvailabilityWindowBase,
    AvailabilityWindowUpdate,
    AvailabilityWindowResponse,
    SpecificDateAvailabilityCreate,
    WeekSpecificScheduleCreate,
    BlackoutDateCreate,
    BlackoutDateResponse,
    DayOfWeekEnum
)

# Password reset schemas
from .password_reset import (
    PasswordResetRequest,
    PasswordResetConfirm,
    PasswordResetResponse
)

from .booking import (
    BookingCreate, BookingUpdate, BookingCancel,
    BookingResponse, BookingListResponse,
    AvailabilityCheckRequest, AvailabilityCheckResponse,
    BookingStatsResponse, UpcomingBookingResponse,
    BookingStatus
)

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
    "BookingStatus"
]