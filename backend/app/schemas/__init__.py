# backend/app/schemas/__init__.py
"""
Pydantic schemas for InstaInstru platform.

Clean Architecture: Exports only schemas that match our new architecture.
Clean architecture with no dead code.
"""

# Availability schemas - Bitmap-only storage now
# AvailabilitySlot schemas removed - bitmap-only storage now

# Availability window schemas - Date-specific operations
from .availability_window import (
    ApplyToDateRangeRequest,
    AvailabilityWindowBase,
    AvailabilityWindowResponse,
    BlackoutDateCreate,
    BlackoutDateResponse,
    BulkUpdateRequest,
    BulkUpdateResponse,
    CopyWeekRequest,
    OperationResult,
    SlotOperation,
    SpecificDateAvailabilityCreate,
    TimeSlot,
    ValidateWeekRequest,
    ValidationSlotDetail,
    ValidationSummary,
    WeekSpecificScheduleCreate,
    WeekValidationResponse,
)

# Booking schemas - Self-contained bookings
from .booking import (
    AvailabilityCheckRequest,
    AvailabilityCheckResponse,
    BookingBase,
    BookingCancel,
    BookingCreate,
    BookingListResponse,
    BookingOpportunity,
    BookingResponse,
    BookingServiceInfo,
    BookingStatsResponse,
    BookingStatus,
    BookingUpdate,
    FindBookingOpportunitiesRequest,
    FindBookingOpportunitiesResponse,
    InstructorInfo,
    StudentInfo,
    UpcomingBookingResponse,
)

# Conversation schemas
from .conversation import (
    BookingSummary,
    ConversationDetail,
    ConversationListItem,
    ConversationListResponse,
    CreateConversationRequest,
    CreateConversationResponse,
    LastMessage,
    MessageResponse as ConversationMessageResponse,
    MessagesResponse as ConversationMessagesResponse,
    SendMessageRequest as ConversationSendMessageRequest,
    SendMessageResponse as ConversationSendMessageResponse,
    UserSummary,
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
from .main_responses import ReadyProbeResponse

# Password reset schemas
from .password_reset import PasswordResetConfirm, PasswordResetRequest, PasswordResetResponse
from .public_availability import (
    PublicAvailabilityQuery,
    PublicDayAvailability,
    PublicInstructorAvailability,
    PublicTimeSlot,
)
from .referrals import (
    AdminReferralsConfigOut,
    AdminReferralsHealthOut,
    AdminReferralsSummaryOut,
    CheckoutApplyRequest,
    CheckoutApplyResponse,
    ReferralClaimRequest,
    ReferralClaimResponse,
    ReferralCodeOut,
    ReferralErrorResponse,
    ReferralLedgerResponse,
    ReferralResolveResponse,
    ReferralSendError,
    ReferralSendRequest,
    ReferralSendResponse,
    RewardOut,
    TopReferrerOut,
    WalletTxnOut,
)
from .security import PasswordChangeRequest, PasswordChangeResponse

# User and authentication schemas
from .user import (
    UserCreate,
    UserLogin,
    UserResponse,
    UserUpdate,
    UserWithPermissionsResponse,
)

__all__ = [
    # User schemas
    "UserCreate",
    "UserLogin",
    "UserResponse",
    "UserUpdate",
    "UserWithPermissionsResponse",
    # Security
    "PasswordChangeRequest",
    "PasswordChangeResponse",
    # Instructor schemas
    "InstructorProfileBase",
    "InstructorProfileCreate",
    "InstructorProfileUpdate",
    "InstructorProfileResponse",
    "ServiceBase",
    "ServiceCreate",
    "ServiceResponse",
    # Availability window schemas - Date operations (bitmap-only storage)
    "AvailabilityWindowBase",
    "AvailabilityWindowResponse",
    "SpecificDateAvailabilityCreate",
    "WeekSpecificScheduleCreate",
    "BlackoutDateCreate",
    "BlackoutDateResponse",
    "CopyWeekRequest",
    "ApplyToDateRangeRequest",
    "TimeSlot",
    "SlotOperation",
    "BulkUpdateRequest",
    "BulkUpdateResponse",
    "OperationResult",
    "ValidateWeekRequest",
    "WeekValidationResponse",
    "ValidationSummary",
    "ValidationSlotDetail",
    # Password reset schemas
    "PasswordResetRequest",
    "PasswordResetConfirm",
    "PasswordResetResponse",
    # Booking schemas - Self-contained
    "BookingCreate",
    "BookingUpdate",
    "BookingCancel",
    "BookingBase",
    "BookingResponse",
    "BookingListResponse",
    "StudentInfo",
    "InstructorInfo",
    "BookingServiceInfo",
    "AvailabilityCheckRequest",
    "AvailabilityCheckResponse",
    "BookingStatsResponse",
    "UpcomingBookingResponse",
    "BookingStatus",
    "FindBookingOpportunitiesRequest",
    "FindBookingOpportunitiesResponse",
    "BookingOpportunity",
    # Referrals
    "ReferralSendRequest",
    "ReferralSendResponse",
    "ReferralSendError",
    "ReferralCodeOut",
    "ReferralClaimRequest",
    "ReferralClaimResponse",
    "ReferralErrorResponse",
    "ReferralLedgerResponse",
    "ReferralResolveResponse",
    "CheckoutApplyRequest",
    "CheckoutApplyResponse",
    "AdminReferralsConfigOut",
    "AdminReferralsSummaryOut",
    "AdminReferralsHealthOut",
    "TopReferrerOut",
    "RewardOut",
    "WalletTxnOut",
    # Public availability schemas
    "PublicTimeSlot",
    "PublicDayAvailability",
    "PublicInstructorAvailability",
    "PublicAvailabilityQuery",
    "ReadyProbeResponse",
    # Conversation schemas
    "UserSummary",
    "BookingSummary",
    "LastMessage",
    "ConversationListItem",
    "ConversationListResponse",
    "ConversationDetail",
    "ConversationMessageResponse",
    "ConversationMessagesResponse",
    "CreateConversationRequest",
    "CreateConversationResponse",
    "ConversationSendMessageRequest",
    "ConversationSendMessageResponse",
]
