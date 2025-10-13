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

from .address import InstructorServiceArea, NYCNeighborhood, UserAddress
from .availability import AvailabilitySlot, BlackoutDate
from .booking import Booking, BookingStatus
from .config import PlatformConfig
from .favorite import UserFavorite
from .instructor import BGCConsent, InstructorPreferredPlace, InstructorProfile
from .message import Message, MessageNotification
from .monitoring import AlertHistory
from .password_reset import PasswordResetToken
from .payment import PaymentIntent, PaymentMethod, StripeConnectedAccount, StripeCustomer
from .rbac import Permission, Role, RolePermission, UserPermission, UserRole
from .referrals import (
    ReferralAttribution,
    ReferralClick,
    ReferralCode,
    ReferralLimit,
    ReferralReward,
    WalletTransaction,
)
from .region_boundary import RegionBoundary
from .search_event import SearchEvent, SearchEventCandidate
from .search_history import SearchHistory
from .search_interaction import SearchInteraction
from .service_catalog import InstructorService, ServiceAnalytics, ServiceCatalog, ServiceCategory
from .user import User

__all__ = [
    # User models
    "User",
    "UserFavorite",
    # RBAC models
    "Role",
    "Permission",
    "UserRole",
    "RolePermission",
    "UserPermission",
    # Instructor models
    "InstructorProfile",
    "BGCConsent",
    "InstructorPreferredPlace",
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
    "PlatformConfig",
    # Payment models
    "PaymentIntent",
    "PaymentMethod",
    "StripeConnectedAccount",
    "StripeCustomer",
    # Referral models
    "ReferralCode",
    "ReferralClick",
    "ReferralAttribution",
    "ReferralReward",
    "WalletTransaction",
    "ReferralLimit",
    # Messaging models
    "Message",
    "MessageNotification",
    # Monitoring models
    "AlertHistory",
    # Address/Spatial models
    "UserAddress",
    "NYCNeighborhood",
    "InstructorServiceArea",
    "RegionBoundary",
    # Search history
    "SearchHistory",
    "SearchEvent",
    "SearchEventCandidate",
    "SearchInteraction",
]
