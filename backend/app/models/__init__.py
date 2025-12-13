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
from .audit_log import AuditLog
from .availability import BlackoutDate
from .availability_day import AvailabilityDay  # noqa: F401
from .booking import Booking, BookingStatus
from .conversation import Conversation
from .conversation_user_state import ConversationUserState
from .event_outbox import EventOutbox, EventOutboxStatus, NotificationDelivery
from .favorite import UserFavorite
from .instructor import BGCConsent, InstructorPreferredPlace, InstructorProfile
from .message import (
    MESSAGE_TYPE_SYSTEM_BOOKING_CANCELLED,
    MESSAGE_TYPE_SYSTEM_BOOKING_COMPLETED,
    MESSAGE_TYPE_SYSTEM_BOOKING_CREATED,
    MESSAGE_TYPE_SYSTEM_BOOKING_RESCHEDULED,
    MESSAGE_TYPE_SYSTEM_CONVERSATION_STARTED,
    MESSAGE_TYPE_USER,
    Message,
    MessageNotification,
)
from .monitoring import AlertHistory

# NL Search models
from .nl_search import (
    NYCLocation,  # Backward compatibility alias for SearchLocation
    PriceThreshold,
    RegionSettings,
    SearchClick,
    SearchLocation,
    SearchQuery,
)
from .password_reset import PasswordResetToken
from .payment import PaymentIntent, PaymentMethod, StripeConnectedAccount, StripeCustomer
from .platform_config import PlatformConfig
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
    "BlackoutDate",
    "AvailabilityDay",
    # Authentication models
    "PasswordResetToken",
    # Booking models
    "Booking",
    "BookingStatus",
    "AuditLog",
    "PlatformConfig",
    # Notification outbox
    "EventOutbox",
    "EventOutboxStatus",
    "NotificationDelivery",
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
    "Conversation",
    "Message",
    "MessageNotification",
    "ConversationUserState",
    # Message type constants
    "MESSAGE_TYPE_USER",
    "MESSAGE_TYPE_SYSTEM_BOOKING_CREATED",
    "MESSAGE_TYPE_SYSTEM_BOOKING_CANCELLED",
    "MESSAGE_TYPE_SYSTEM_BOOKING_RESCHEDULED",
    "MESSAGE_TYPE_SYSTEM_BOOKING_COMPLETED",
    "MESSAGE_TYPE_SYSTEM_CONVERSATION_STARTED",
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
    # NL Search models
    "SearchQuery",
    "SearchClick",
    "SearchLocation",
    "NYCLocation",  # Backward compatibility alias
    "RegionSettings",
    "PriceThreshold",
]
