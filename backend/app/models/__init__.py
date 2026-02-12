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
from .audit_log import AuditLog, AuditLogEntry
from .availability import BlackoutDate
from .availability_day import AvailabilityDay  # noqa: F401
from .badge import BadgeDefinition, BadgeProgress, StudentBadge
from .beta import BetaAccess, BetaInvite, BetaSettings
from .booking import Booking, BookingStatus
from .booking_note import BookingNote
from .conversation import Conversation
from .conversation_user_state import ConversationUserState
from .event_outbox import EventOutbox, EventOutboxStatus, NotificationDelivery
from .favorite import UserFavorite
from .filter import (
    FilterDefinition,
    FilterOption,
    SubcategoryFilter,
    SubcategoryFilterOption,
)
from .instructor import BGCConsent, InstructorPreferredPlace, InstructorProfile
from .instructor_lifecycle_event import InstructorLifecycleEvent

# Location resolution models
from .location_alias import NYC_CITY_ID, LocationAlias
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
    PriceThreshold,
    RegionSettings,
    SearchClick,
    SearchQuery,
)
from .notification import Notification, NotificationPreference, PushSubscription
from .password_reset import PasswordResetToken
from .payment import PaymentIntent, PaymentMethod, StripeConnectedAccount, StripeCustomer
from .platform_config import PlatformConfig
from .rbac import Permission, Role, RolePermission, UserPermission, UserRole
from .referrals import (
    InstructorReferralPayout,
    ReferralAttribution,
    ReferralClick,
    ReferralCode,
    ReferralLimit,
    ReferralReward,
    WalletTransaction,
)
from .region_boundary import RegionBoundary
from .review import Review, ReviewResponse, ReviewTip
from .search_event import SearchEvent, SearchEventCandidate
from .search_history import SearchHistory
from .search_interaction import SearchInteraction
from .service_catalog import InstructorService, ServiceAnalytics, ServiceCatalog, ServiceCategory
from .subcategory import ServiceSubcategory
from .unresolved_location_query import UnresolvedLocationQuery
from .user import User
from .webhook_event import WebhookEvent

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
    "InstructorLifecycleEvent",
    "BGCConsent",
    "InstructorPreferredPlace",
    # Badge models
    "BadgeDefinition",
    "StudentBadge",
    "BadgeProgress",
    # Beta models
    "BetaInvite",
    "BetaAccess",
    "BetaSettings",
    # Service catalog models
    "ServiceCategory",
    "ServiceSubcategory",
    "ServiceCatalog",
    "InstructorService",
    "ServiceAnalytics",
    # Filter models
    "FilterDefinition",
    "FilterOption",
    "SubcategoryFilter",
    "SubcategoryFilterOption",
    # Availability models
    "BlackoutDate",
    "AvailabilityDay",
    # Authentication models
    "PasswordResetToken",
    # Review models
    "Review",
    "ReviewResponse",
    "ReviewTip",
    # Booking models
    "Booking",
    "BookingStatus",
    "BookingNote",
    "AuditLog",
    "AuditLogEntry",
    "PlatformConfig",
    # Notification outbox
    "EventOutbox",
    "EventOutboxStatus",
    "NotificationDelivery",
    # Notifications
    "NotificationPreference",
    "Notification",
    "PushSubscription",
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
    "InstructorReferralPayout",
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
    "LocationAlias",
    "NYC_CITY_ID",
    "UnresolvedLocationQuery",
    # Search history
    "SearchHistory",
    "SearchEvent",
    "SearchEventCandidate",
    "SearchInteraction",
    # NL Search models
    "SearchQuery",
    "SearchClick",
    "RegionSettings",
    "PriceThreshold",
    "WebhookEvent",
]
