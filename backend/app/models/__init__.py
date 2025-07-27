"""
Database models for InstaInstru platform.

This module exports all SQLAlchemy models used in the application.
The models are organized by functionality:
- User authentication and roles
- Instructor profiles and services
- Service catalog system
- Availability management
- Password reset functionality

Note: The Service model has been replaced with a three-table catalog system:
- ServiceCategory: Categories for organizing services
- ServiceCatalog: Predefined services with standardized names
- InstructorService: Links instructors to catalog services
"""

from .availability import AvailabilitySlot, BlackoutDate
from .booking import Booking, BookingStatus
from .instructor import InstructorProfile
from .monitoring import AlertHistory
from .password_reset import PasswordResetToken
from .search_history import SearchHistory
from .service_catalog import InstructorService, ServiceAnalytics, ServiceCatalog, ServiceCategory
from .user import User, UserRole

__all__ = [
    # User models
    "User",
    "UserRole",
    # Instructor models
    "InstructorProfile",
    # Service catalog models
    "ServiceCategory",
    "ServiceCatalog",
    "InstructorService",
    "ServiceAnalytics",
    # Availability models
    "AvailabilitySlot",
    "BlackoutDate",
    # Authentication models
    "PasswordResetToken",
    # Booking models
    "Booking",
    "BookingStatus",
    # Monitoring models
    "AlertHistory",
    # Search history
    "SearchHistory",
]
