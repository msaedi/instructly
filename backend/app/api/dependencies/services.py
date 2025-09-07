# backend/app/api/dependencies/services.py
"""
Service layer dependencies for dependency injection.

This module provides factory functions that create service instances
with their required dependencies properly injected.
"""

from functools import lru_cache

from fastapi import Depends
from sqlalchemy.orm import Session

from ...services.account_lifecycle_service import AccountLifecycleService
from ...services.auth_service import AuthService
from ...services.availability_service import AvailabilityService
from ...services.booking_service import BookingService
from ...services.bulk_operation_service import BulkOperationService
from ...services.cache_service import CacheService, get_cache_service
from ...services.conflict_checker import ConflictChecker
from ...services.email import EmailService
from ...services.favorites_service import FavoritesService
from ...services.instructor_service import InstructorService
from ...services.notification_service import NotificationService
from ...services.password_reset_service import PasswordResetService
from ...services.presentation_service import PresentationService
from ...services.slot_manager import SlotManager
from ...services.two_factor_auth_service import TwoFactorAuthService
from ...services.week_operation_service import WeekOperationService
from .database import get_db

# Service instance cache
_service_instances = {}


@lru_cache(maxsize=1)
def get_cache_service_singleton() -> CacheService:
    """Get singleton cache service instance."""
    return get_cache_service()


def get_cache_service_dep() -> CacheService:
    """Get cache service instance for dependency injection."""
    return get_cache_service_singleton()


def get_email_service(
    db: Session = Depends(get_db), cache: CacheService = Depends(get_cache_service_dep)
) -> EmailService:
    """Get EmailService instance with proper dependencies."""
    return EmailService(db, cache)


def get_notification_service(
    db: Session = Depends(get_db), email_service: EmailService = Depends(get_email_service)
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

    template_service = TemplateService(db, None)

    return NotificationService(db, None, template_service, email_service)


def get_booking_service(
    db: Session = Depends(get_db),
    notification_service: NotificationService = Depends(get_notification_service),
    cache_service: CacheService = Depends(get_cache_service_dep),
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


def get_instructor_service(
    db: Session = Depends(get_db),
    cache_service: CacheService = Depends(get_cache_service_dep),
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
    cache_service: CacheService = Depends(get_cache_service_dep),
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
    cache_service: CacheService = Depends(get_cache_service_dep),
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


def get_slot_manager(
    db: Session = Depends(get_db),
    conflict_checker: ConflictChecker = Depends(get_conflict_checker),
) -> SlotManager:
    """
    Get slot manager service instance.

    Args:
        db: Database session
        conflict_checker: Conflict checker service

    Returns:
        SlotManager instance
    """
    return SlotManager(db, conflict_checker)


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
    slot_manager: SlotManager = Depends(get_slot_manager),
    conflict_checker: ConflictChecker = Depends(get_conflict_checker),
    cache_service: CacheService = Depends(get_cache_service_dep),
) -> BulkOperationService:
    """
    Get bulk operation service instance.

    Args:
        db: Database session
        slot_manager: Slot manager service
        conflict_checker: Conflict checker service

    Returns:
        BulkOperationService instance
    """
    return BulkOperationService(db, slot_manager, conflict_checker, cache_service)


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
    cache_service: CacheService = Depends(get_cache_service_dep),
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
