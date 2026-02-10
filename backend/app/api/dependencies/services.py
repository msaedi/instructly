# backend/app/api/dependencies/services.py
"""
Service layer dependencies for dependency injection.

This module provides factory functions that create service instances
with their required dependencies properly injected.
"""

from functools import lru_cache
import logging

from fastapi import Depends
from sqlalchemy.orm import Session

from ...core.config import settings
from ...integrations import CheckrClient, FakeCheckrClient
from ...repositories.instructor_profile_repository import InstructorProfileRepository
from ...services.account_lifecycle_service import AccountLifecycleService
from ...services.auth_service import AuthService
from ...services.availability_service import AvailabilityService
from ...services.background_check_service import BackgroundCheckService
from ...services.background_check_workflow_service import BackgroundCheckWorkflowService
from ...services.base import BaseService
from ...services.booking_admin_service import BookingAdminService
from ...services.booking_detail_service import BookingDetailService
from ...services.booking_service import BookingService
from ...services.bulk_operation_service import BulkOperationService
from ...services.cache_service import CacheService, CacheServiceSyncAdapter
from ...services.catalog_browse_service import CatalogBrowseService
from ...services.communication_admin_service import CommunicationAdminService
from ...services.conflict_checker import ConflictChecker
from ...services.email import EmailService
from ...services.favorites_service import FavoritesService
from ...services.funnel_analytics_service import FunnelAnalyticsService
from ...services.instructor_admin_service import InstructorAdminService
from ...services.instructor_service import InstructorService
from ...services.notification_service import NotificationService
from ...services.password_reset_service import PasswordResetService
from ...services.platform_analytics_service import PlatformAnalyticsService
from ...services.presentation_service import PresentationService
from ...services.pricing_service import PricingService
from ...services.referral_checkout_service import ReferralCheckoutService
from ...services.referral_service import ReferralService
from ...services.refund_service import RefundService
from ...services.sms_service import SMSService
from ...services.student_admin_service import StudentAdminService

# SlotManager removed - bitmap-only storage now
from ...services.two_factor_auth_service import TwoFactorAuthService
from ...services.wallet_service import WalletService
from ...services.week_operation_service import WeekOperationService
from .database import get_db
from .repositories import get_instructor_repo

logger = logging.getLogger(__name__)

# Service instance cache keyed by service type
_service_instances: dict[type[BaseService], BaseService] = {}


@lru_cache(maxsize=1)
def get_cache_service_singleton() -> CacheService:
    """Get singleton cache service instance."""
    # CacheService does not require a DB session; keep singleton for connection reuse.
    return CacheService()


def get_cache_service_dep() -> CacheService:
    """Get cache service instance for dependency injection."""
    return get_cache_service_singleton()


@lru_cache(maxsize=1)
def get_cache_service_sync_singleton() -> CacheServiceSyncAdapter:
    """Get singleton sync adapter over the async cache service."""
    return CacheServiceSyncAdapter(get_cache_service_singleton())


def get_cache_service_sync_dep() -> CacheServiceSyncAdapter:
    """Get sync cache service adapter for legacy sync services."""
    return get_cache_service_sync_singleton()


def get_email_service(
    db: Session = Depends(get_db),
    cache: CacheServiceSyncAdapter = Depends(get_cache_service_sync_dep),
) -> EmailService:
    """Get EmailService instance with proper dependencies."""
    return EmailService(db, cache)


def get_sms_service(
    cache: CacheService = Depends(get_cache_service_dep),
) -> SMSService:
    """Get SMSService instance with proper dependencies."""
    return SMSService(cache)


def get_notification_service(
    db: Session = Depends(get_db),
    cache: CacheServiceSyncAdapter = Depends(get_cache_service_sync_dep),
    email_service: EmailService = Depends(get_email_service),
    sms_service: SMSService = Depends(get_sms_service),
) -> NotificationService:
    """
    Get notification service instance.

    Args:
        db: Database session
        email_service: Email service for sending emails

    Returns:
        NotificationService instance
    """
    # Create template service internally
    from ...services.template_service import TemplateService

    template_service = TemplateService(db, cache)

    return NotificationService(db, cache, template_service, email_service, sms_service=sms_service)


def get_booking_service(
    db: Session = Depends(get_db),
    notification_service: NotificationService = Depends(get_notification_service),
    cache_service: CacheServiceSyncAdapter = Depends(get_cache_service_sync_dep),
) -> BookingService:
    """
    Get booking service instance with all dependencies.

    Args:
        db: Database session
        notification_service: Notification service for sending emails
        cache_service: Cache service for invalidation

    Returns:
        BookingService instance
    """
    return BookingService(
        db,
        notification_service,
        repository=None,
        conflict_checker_repository=None,
        cache_service=cache_service,
    )


def get_booking_detail_service(db: Session = Depends(get_db)) -> BookingDetailService:
    """Get booking detail service instance for MCP support tooling."""
    return BookingDetailService(db)


def get_refund_service(db: Session = Depends(get_db)) -> RefundService:
    """Get refund service instance for MCP refund tooling."""
    return RefundService(db)


def get_booking_admin_service(db: Session = Depends(get_db)) -> BookingAdminService:
    """Get booking admin service instance for MCP booking actions."""
    return BookingAdminService(db)


def get_instructor_admin_service(db: Session = Depends(get_db)) -> InstructorAdminService:
    """Get instructor admin service instance for MCP instructor actions."""
    return InstructorAdminService(db)


def get_student_admin_service(db: Session = Depends(get_db)) -> StudentAdminService:
    """Get student admin service instance for MCP student actions."""
    return StudentAdminService(db)


def get_communication_admin_service(
    db: Session = Depends(get_db),
) -> CommunicationAdminService:
    """Get communication admin service instance for MCP communication tools."""
    return CommunicationAdminService(db)


def get_platform_analytics_service(db: Session = Depends(get_db)) -> PlatformAnalyticsService:
    """Get platform analytics service instance for MCP analytics tooling."""
    return PlatformAnalyticsService(db)


def get_funnel_analytics_service(db: Session = Depends(get_db)) -> FunnelAnalyticsService:
    """Get funnel analytics service instance for MCP funnel snapshots."""
    return FunnelAnalyticsService(db)


def get_pricing_service(db: Session = Depends(get_db)) -> PricingService:
    """Provide pricing service instance for dependency injection."""

    return PricingService(db)


def get_catalog_browse_service(
    db: Session = Depends(get_db),
) -> CatalogBrowseService:
    """Get CatalogBrowseService instance for read-only taxonomy browsing."""
    return CatalogBrowseService(db)


def get_instructor_service(
    db: Session = Depends(get_db),
    cache_service: CacheServiceSyncAdapter = Depends(get_cache_service_sync_dep),
) -> InstructorService:
    """
    Get instructor service instance with all dependencies.

    Args:
        db: Database session
        cache_service: Cache service for performance optimization

    Returns:
        InstructorService instance
    """
    from ...services.instructor_service import InstructorService

    return InstructorService(db, cache_service)


def get_favorites_service(
    db: Session = Depends(get_db),
    cache_service: CacheServiceSyncAdapter = Depends(get_cache_service_sync_dep),
) -> FavoritesService:
    """
    Get favorites service instance with all dependencies.

    Args:
        db: Database session
        cache_service: Cache service for performance optimization

    Returns:
        FavoritesService instance
    """
    return FavoritesService(db, cache_service=cache_service)


def get_availability_service(
    db: Session = Depends(get_db),
    cache_service: CacheServiceSyncAdapter = Depends(get_cache_service_sync_dep),
) -> AvailabilityService:
    """
    Get availability service instance with cache support.

    Args:
        db: Database session
        cache_service: Cache service for performance optimization

    Returns:
        AvailabilityService instance with caching enabled
    """
    return AvailabilityService(db, cache_service)


def get_conflict_checker(db: Session = Depends(get_db)) -> ConflictChecker:
    """
    Get conflict checker service instance.

    Args:
        db: Database session

    Returns:
        ConflictChecker instance
    """
    return ConflictChecker(db)


# get_slot_manager removed - SlotManager service deleted (bitmap-only storage)


def get_referral_service(db: Session = Depends(get_db)) -> ReferralService:
    """Provide referral service instance."""

    return ReferralService(db)


def get_wallet_service(db: Session = Depends(get_db)) -> WalletService:
    """Provide wallet service instance."""

    return WalletService(db)


def get_background_check_workflow_service(
    repo: InstructorProfileRepository = Depends(get_instructor_repo),
) -> BackgroundCheckWorkflowService:
    """Provide the background check workflow service."""

    return BackgroundCheckWorkflowService(repo)


def get_referral_checkout_service(
    db: Session = Depends(get_db),
    wallet_service: WalletService = Depends(get_wallet_service),
) -> ReferralCheckoutService:
    """Provide referral checkout helper service."""

    return ReferralCheckoutService(db, wallet_service)


def get_background_check_service(
    db: Session = Depends(get_db),
) -> BackgroundCheckService:
    """Provide background check service wired to Checkr."""

    repository = InstructorProfileRepository(db)
    use_fake = bool(settings.checkr_fake)
    config_error: str | None = None

    logger.info(
        "Background check client selection",
        extra={
            "site_mode": settings.site_mode,
            "checkr_env": settings.checkr_env,
            "checkr_fake": use_fake,
        },
    )

    if use_fake:
        client: CheckrClient = FakeCheckrClient()
    else:
        try:
            client = CheckrClient(
                api_key=settings.checkr_api_key,
                base_url=settings.checkr_api_base,
            )
        except ValueError as exc:  # Missing API key or malformed configuration
            if settings.site_mode == "prod":
                raise

            config_error = str(exc)
            logger.warning(
                "Falling back to FakeCheckrClient due to configuration error",
                extra={
                    "error": config_error,
                    "site_mode": settings.site_mode,
                },
            )
            client = FakeCheckrClient()

    service = BackgroundCheckService(
        db,
        client=client,
        repository=repository,
        package=settings.checkr_package,
        env=settings.checkr_env,
        is_fake_client=isinstance(client, FakeCheckrClient),
        config_error=config_error,
    )

    return service


def get_week_operation_service(
    db: Session = Depends(get_db),
    availability_service: AvailabilityService = Depends(get_availability_service),
    conflict_checker: ConflictChecker = Depends(get_conflict_checker),
    cache_service: CacheService = Depends(get_cache_service_dep),
) -> WeekOperationService:
    """
    Get week operation service instance.

    Args:
        db: Database session
        availability_service: Availability service
        conflict_checker: Conflict checker service
        cache_service: Cache service for warming

    Returns:
        WeekOperationService instance
    """
    return WeekOperationService(db, availability_service, conflict_checker, cache_service)


def get_bulk_operation_service(
    db: Session = Depends(get_db),
    conflict_checker: ConflictChecker = Depends(get_conflict_checker),
    cache_service: CacheServiceSyncAdapter = Depends(get_cache_service_sync_dep),
) -> BulkOperationService:
    """
    Get bulk operation service instance.

    Args:
        db: Database session
        conflict_checker: Conflict checker service
        cache_service: Cache service

    Returns:
        BulkOperationService instance
    """
    return BulkOperationService(
        db, slot_manager=None, conflict_checker=conflict_checker, cache_service=cache_service
    )


def get_presentation_service(db: Session = Depends(get_db)) -> PresentationService:
    """
    Get presentation service instance.

    Args:
        db: Database session

    Returns:
        PresentationService instance
    """
    return PresentationService(db)


def get_auth_service(db: Session = Depends(get_db)) -> AuthService:
    """Get AuthService instance."""
    return AuthService(db)


def get_two_factor_auth_service(db: Session = Depends(get_db)) -> TwoFactorAuthService:
    """Get TwoFactorAuthService instance."""
    return TwoFactorAuthService(db)


def get_password_reset_service(
    db: Session = Depends(get_db),
    email_service: EmailService = Depends(get_email_service),
) -> PasswordResetService:
    """
    Get PasswordResetService instance with dependencies.

    Args:
        db: Database session
        email_service: Email service for sending reset emails

    Returns:
        PasswordResetService instance
    """
    return PasswordResetService(db, email_service=email_service)


def get_account_lifecycle_service(
    db: Session = Depends(get_db),
    cache_service: CacheServiceSyncAdapter = Depends(get_cache_service_sync_dep),
) -> AccountLifecycleService:
    """
    Get AccountLifecycleService instance with dependencies.

    Handles instructor account status changes (suspend, deactivate, reactivate).

    Args:
        db: Database session
        cache_service: Cache service for invalidation

    Returns:
        AccountLifecycleService instance
    """
    return AccountLifecycleService(db, cache_service)
