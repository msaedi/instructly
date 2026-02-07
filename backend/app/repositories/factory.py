# backend/app/repositories/factory.py
"""
Repository Factory for InstaInstru Platform

Provides centralized creation of repository instances,
ensuring consistent initialization and dependency injection.

This factory will grow as we add more specific repositories.
"""

from typing import TYPE_CHECKING, Type, TypeVar

from sqlalchemy.orm import Session

from .base_repository import BaseRepository

ModelT = TypeVar("ModelT")

# Avoid circular imports
if TYPE_CHECKING:
    from .address_repository import InstructorServiceAreaRepository
    from .analytics_repository import AnalyticsRepository
    from .audit_repository import AuditRepository
    from .availability_repository import AvailabilityRepository
    from .badge_repository import BadgeRepository
    from .booking_note_repository import BookingNoteRepository
    from .booking_repository import BookingRepository
    from .bulk_operation_repository import BulkOperationRepository
    from .communication_repository import CommunicationRepository
    from .conflict_checker_repository import ConflictCheckerRepository
    from .conversation_repository import ConversationRepository
    from .credit_repository import CreditRepository
    from .event_outbox_repository import EventOutboxRepository
    from .governance_audit_repository import GovernanceAuditRepository
    from .instructor_lifecycle_repository import InstructorLifecycleRepository
    from .instructor_preferred_place_repository import InstructorPreferredPlaceRepository
    from .instructor_profile_repository import InstructorProfileRepository
    from .message_repository import MessageRepository
    from .notification_delivery_repository import NotificationDeliveryRepository
    from .notification_repository import NotificationRepository
    from .payment_repository import PaymentRepository
    from .platform_config_repository import PlatformConfigRepository
    from .rbac_repository import RBACRepository
    from .referral_repository import (
        ReferralAttributionRepository,
        ReferralClickRepository,
        ReferralCodeRepository,
        ReferralLimitRepository,
        ReferralRewardRepository,
        WalletTransactionRepository,
    )
    from .review_repository import ReviewTipRepository
    from .search_event_repository import SearchEventRepository
    from .search_history_repository import SearchHistoryRepository
    from .service_catalog_repository import ServiceAnalyticsRepository, ServiceCatalogRepository
    from .taxonomy_filter_repository import TaxonomyFilterRepository

    # SlotManagerRepository removed - bitmap-only storage now
    from .user_repository import UserRepository
    from .week_operation_repository import WeekOperationRepository


class RepositoryFactory:
    """
    Factory class for creating repository instances.

    Centralizes repository creation to ensure consistent initialization
    and makes it easy to swap implementations if needed.
    """

    @staticmethod
    def create_base_repository(db: Session, model: Type[ModelT]) -> BaseRepository[ModelT]:
        """
        Create a generic base repository for any model.

        Args:
            db: Database session
            model: SQLAlchemy model class

        Returns:
            BaseRepository instance
        """
        return BaseRepository(db, model)

    # create_slot_manager_repository removed - SlotManagerRepository deleted (bitmap-only storage)

    @staticmethod
    def create_availability_repository(db: Session) -> "AvailabilityRepository":
        """Create repository for availability operations."""
        from .availability_repository import AvailabilityRepository

        return AvailabilityRepository(db)

    @staticmethod
    def create_conflict_checker_repository(db: Session) -> "ConflictCheckerRepository":
        """Create repository for conflict checking queries."""
        from .conflict_checker_repository import ConflictCheckerRepository

        return ConflictCheckerRepository(db)

    @staticmethod
    def create_credit_repository(db: Session) -> "CreditRepository":
        """Create repository for credit lifecycle queries."""
        from .credit_repository import CreditRepository

        return CreditRepository(db)

    @staticmethod
    def create_bulk_operation_repository(db: Session) -> "BulkOperationRepository":
        """Create repository for bulk operation queries."""
        from .bulk_operation_repository import BulkOperationRepository

        return BulkOperationRepository(db)

    @staticmethod
    def create_communication_repository(db: Session) -> "CommunicationRepository":
        """Create repository for admin communication queries."""
        from .communication_repository import CommunicationRepository

        return CommunicationRepository(db)

    @staticmethod
    def create_booking_repository(db: Session) -> "BookingRepository":
        """Create repository for booking operations."""
        from .booking_repository import BookingRepository

        return BookingRepository(db)

    @staticmethod
    def create_analytics_repository(db: Session) -> "AnalyticsRepository":
        """Create repository for analytics queries."""
        from .analytics_repository import AnalyticsRepository

        return AnalyticsRepository(db)

    @staticmethod
    def create_booking_note_repository(db: Session) -> "BookingNoteRepository":
        """Create repository for booking note operations."""
        from .booking_note_repository import BookingNoteRepository

        return BookingNoteRepository(db)

    @staticmethod
    def create_event_outbox_repository(db: Session) -> "EventOutboxRepository":
        """Create repository for event outbox operations."""
        from .event_outbox_repository import EventOutboxRepository

        return EventOutboxRepository(db)

    @staticmethod
    def create_audit_repository(db: Session) -> "AuditRepository":
        """Create repository for audit log operations."""
        from .audit_repository import AuditRepository

        return AuditRepository(db)

    @staticmethod
    def create_governance_audit_repository(db: Session) -> "GovernanceAuditRepository":
        """Create repository for governance audit log operations."""
        from .governance_audit_repository import GovernanceAuditRepository

        return GovernanceAuditRepository(db)

    @staticmethod
    def create_notification_delivery_repository(db: Session) -> "NotificationDeliveryRepository":
        """Create repository for notification delivery records."""
        from .notification_delivery_repository import NotificationDeliveryRepository

        return NotificationDeliveryRepository(db)

    @staticmethod
    def create_notification_repository(db: Session) -> "NotificationRepository":
        """Create repository for notification preferences and inbox."""
        from .notification_repository import NotificationRepository

        return NotificationRepository(db)

    @staticmethod
    def get_booking_repository(db: Session) -> "BookingRepository":
        """Alias for create_booking_repository for backward compatibility."""
        return RepositoryFactory.create_booking_repository(db)

    @staticmethod
    def create_week_operation_repository(db: Session) -> "WeekOperationRepository":
        """Create repository for week operation queries."""
        from .week_operation_repository import WeekOperationRepository

        return WeekOperationRepository(db)

    @staticmethod
    def create_instructor_profile_repository(db: Session) -> "InstructorProfileRepository":
        """Create repository for instructor profile operations with optimized queries."""
        from .instructor_profile_repository import InstructorProfileRepository

        return InstructorProfileRepository(db)

    @staticmethod
    def create_instructor_preferred_place_repository(
        db: Session,
    ) -> "InstructorPreferredPlaceRepository":
        """Create repository for instructor preferred places."""
        from .instructor_preferred_place_repository import InstructorPreferredPlaceRepository

        return InstructorPreferredPlaceRepository(db)

    @staticmethod
    def create_instructor_lifecycle_repository(db: Session) -> "InstructorLifecycleRepository":
        """Create repository for instructor lifecycle events."""
        from .instructor_lifecycle_repository import InstructorLifecycleRepository

        return InstructorLifecycleRepository(db)

    @staticmethod
    def create_instructor_service_area_repository(
        db: Session,
    ) -> "InstructorServiceAreaRepository":
        """Create repository for instructor service areas."""
        from .address_repository import InstructorServiceAreaRepository

        return InstructorServiceAreaRepository(db)

    @staticmethod
    def create_service_catalog_repository(db: Session) -> "ServiceCatalogRepository":
        """Create repository for service catalog operations with vector search."""
        from .service_catalog_repository import ServiceCatalogRepository

        return ServiceCatalogRepository(db)

    @staticmethod
    def create_service_analytics_repository(db: Session) -> "ServiceAnalyticsRepository":
        """Create repository for service analytics operations."""
        from .service_catalog_repository import ServiceAnalyticsRepository

        return ServiceAnalyticsRepository(db)

    @staticmethod
    def create_user_repository(db: Session) -> "UserRepository":
        """
        Create repository for user operations.

        Fixes 30+ repository pattern violations across:
        - PermissionService
        - PrivacyService
        - ConflictChecker
        - timezone_utils
        """
        from .user_repository import UserRepository

        return UserRepository(db)

    @staticmethod
    def create_rbac_repository(db: Session) -> "RBACRepository":
        """
        Create repository for RBAC (Role-Based Access Control) operations.

        Fixes 20+ repository pattern violations in PermissionService
        for Permission, Role, and UserPermission management.
        """
        from .rbac_repository import RBACRepository

        return RBACRepository(db)

    @staticmethod
    def create_search_history_repository(db: Session) -> "SearchHistoryRepository":
        """
        Create repository for search history operations.

        Fixes 34+ repository pattern violations in:
        - SearchHistoryService
        - SearchHistoryCleanupService
        - PrivacyService
        """
        from .search_history_repository import SearchHistoryRepository

        return SearchHistoryRepository(db)

    @staticmethod
    def create_badge_repository(db: Session) -> "BadgeRepository":
        """Create repository for student badge operations."""
        from .badge_repository import BadgeRepository

        return BadgeRepository(db)

    @staticmethod
    def create_payment_repository(db: Session) -> "PaymentRepository":
        """
        Create repository for payment operations.

        Handles Stripe payment integration including:
        - Customer records
        - Connected accounts
        - Payment intents
        - Payment methods
        """
        from .payment_repository import PaymentRepository

        return PaymentRepository(db)

    @staticmethod
    def create_platform_config_repository(db: Session) -> "PlatformConfigRepository":
        """Create repository for platform configuration access."""
        from .platform_config_repository import PlatformConfigRepository

        return PlatformConfigRepository(db)

    @staticmethod
    def get_payment_repository(db: Session) -> "PaymentRepository":
        """Alias for create_payment_repository for backward compatibility."""
        return RepositoryFactory.create_payment_repository(db)

    @staticmethod
    def create_search_event_repository(db: Session) -> "SearchEventRepository":
        """
        Create repository for search event operations.

        Used by PrivacyService for data export and retention policies.
        """
        from .search_event_repository import SearchEventRepository

        return SearchEventRepository(db)

    @staticmethod
    def create_conversation_repository(db: Session) -> "ConversationRepository":
        """
        Create repository for conversation operations.

        Handles per-user-pair conversations for messaging.
        """
        from .conversation_repository import ConversationRepository

        return ConversationRepository(db)

    @staticmethod
    def create_message_repository(db: Session) -> "MessageRepository":
        """
        Create repository for message operations.

        Handles chat messages and notifications for bookings.
        """
        from .message_repository import MessageRepository

        return MessageRepository(db)

    @staticmethod
    def create_referral_code_repository(db: Session) -> "ReferralCodeRepository":
        """Create repository for referral codes."""
        from .referral_repository import ReferralCodeRepository

        return ReferralCodeRepository(db)

    @staticmethod
    def create_referral_click_repository(db: Session) -> "ReferralClickRepository":
        """Create repository for referral clicks."""
        from .referral_repository import ReferralClickRepository

        return ReferralClickRepository(db)

    @staticmethod
    def create_referral_attribution_repository(db: Session) -> "ReferralAttributionRepository":
        """Create repository for referral attributions."""
        from .referral_repository import ReferralAttributionRepository

        return ReferralAttributionRepository(db)

    @staticmethod
    def create_referral_reward_repository(db: Session) -> "ReferralRewardRepository":
        """Create repository for referral rewards."""
        from .referral_repository import ReferralRewardRepository

        return ReferralRewardRepository(db)

    @staticmethod
    def create_wallet_transaction_repository(db: Session) -> "WalletTransactionRepository":
        """Create repository for referral wallet transactions."""
        from .referral_repository import WalletTransactionRepository

        return WalletTransactionRepository(db)

    @staticmethod
    def create_referral_limit_repository(db: Session) -> "ReferralLimitRepository":
        """Create repository for referral limits (placeholder)."""
        from .referral_repository import ReferralLimitRepository

        return ReferralLimitRepository(db)

    @staticmethod
    def create_review_tip_repository(db: Session) -> "ReviewTipRepository":
        """Create repository for review tips."""
        from .review_repository import ReviewTipRepository

        return ReviewTipRepository(db)

    @staticmethod
    def create_taxonomy_filter_repository(db: Session) -> "TaxonomyFilterRepository":
        """Create repository for taxonomy filter operations."""
        from .taxonomy_filter_repository import TaxonomyFilterRepository

        return TaxonomyFilterRepository(db)
