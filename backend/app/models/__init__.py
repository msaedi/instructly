"""
Database models for InstaInstru platform.

This module exports all SQLAlchemy models used in the application.
The models are organized by functionality:
- User authentication and roles
- Instructor profiles and services
- Availability management
- Password reset functionality

Note: RecurringAvailability has been removed as part of the refactoring
to use only date-specific availability.
"""

from .availability import AvailabilitySlot, BlackoutDate, InstructorAvailability
from .booking import Booking, BookingStatus
from .instructor import InstructorProfile
from .password_reset import PasswordResetToken
from .service import Service
from .user import User, UserRole

__all__ = [
    # User models
    "User",
    "UserRole",
    # Instructor models
    "InstructorProfile",
    "Service",
    # Availability models
    "InstructorAvailability",
    "AvailabilitySlot",
    "BlackoutDate",
    # Authentication models
    "PasswordResetToken",
    # Booking models
    "Booking",
    "BookingStatus",
]
