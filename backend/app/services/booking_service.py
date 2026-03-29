# backend/app/services/booking_service.py
"""
Booking Service for InstaInstru Platform

Handles all booking-related business logic including:
- Creating instant bookings using time ranges
- Finding booking opportunities
- Validating booking constraints
- Managing booking lifecycle
- Coordinating with other services

UPDATED IN v65: Added performance metrics and refactored long methods.
All methods now under 50 lines with comprehensive observability! ⚡
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
import logging
import os
from types import SimpleNamespace
from typing import TYPE_CHECKING, Optional

from sqlalchemy.orm import Session
import stripe

from ..constants.pricing_defaults import PRICING_DEFAULTS
from ..core.bgc_policy import is_verified, must_be_verified_for_public
from ..core.config import settings
from ..core.constants import VALID_LOCATION_TYPES
from ..core.exceptions import BookingConflictException
from ..events import EventPublisher
from ..events.booking_events import BookingCancelled
from ..integrations.hundredms_client import HundredMsClient, HundredMsError
from ..repositories.factory import RepositoryFactory
from ..repositories.filter_repository import FilterRepository
from ..repositories.job_repository import JobRepository
from .audit_service import AuditService
from .base import BaseService
from .booking.availability_conflicts import BookingAvailabilityConflictsMixin
from .booking.availability_opportunities import BookingAvailabilityOpportunitiesMixin
from .booking.availability_rules import BookingAvailabilityRulesMixin
from .booking.availability_service import BookingAvailabilityMixin
from .booking.cancellation_cleanup import BookingCancellationCleanupMixin
from .booking.cancellation_finalize import BookingCancellationFinalizeMixin
from .booking.cancellation_late_finalize import BookingCancellationLateFinalizeMixin
from .booking.cancellation_service import BookingCancellationMixin
from .booking.cancellation_stripe import BookingCancellationStripeMixin
from .booking.completion_service import BookingCompletionMixin
from .booking.creation_payment import BookingCreationPaymentMixin
from .booking.creation_service import BookingCreationMixin
from .booking.helpers import BookingHelpersMixin, _is_test_or_ci
from .booking.helpers_audit import BookingAuditCacheMixin
from .booking.lock_resolution import BookingLockResolutionMixin
from .booking.lock_service import BookingLockMixin
from .booking.noshow_resolution import BookingNoShowResolutionMixin
from .booking.noshow_service import BookingNoShowMixin
from .booking.noshow_settlement import BookingNoShowSettlementMixin
from .booking.notifications import BookingNotificationsMixin
from .booking.payment_retry import BookingPaymentRetryMixin
from .booking.payment_service import BookingPaymentMixin
from .booking.query_service import BookingQueryMixin
from .booking.reschedule_creation import BookingRescheduleCreationMixin
from .booking.reschedule_execution import BookingRescheduleExecutionMixin
from .booking.reschedule_service import BookingRescheduleMixin
from .cache_service import CacheService, CacheServiceSyncAdapter
from .config_service import ConfigService
from .conflict_checker import ConflictChecker
from .notification_service import NotificationService
from .pricing_service import PricingService
from .search.cache_invalidation import invalidate_on_availability_change
from .stripe_service import StripeService
from .student_credit_service import StudentCreditService
from .system_message_service import SystemMessageService
from .timezone_service import TimezoneService

if TYPE_CHECKING:
    # AvailabilitySlot removed - bitmap-only storage now
    from ..repositories.audit_repository import AuditRepository
    from ..repositories.availability_repository import AvailabilityRepository
    from ..repositories.booking_repository import BookingRepository
    from ..repositories.conflict_checker_repository import ConflictCheckerRepository
    from ..repositories.event_outbox_repository import EventOutboxRepository

logger = logging.getLogger(__name__)
UTC_REFERENCE = timezone.utc

AUDIT_ENABLED = os.getenv("AUDIT_ENABLED", "true").lower() in {"1", "true", "yes"}


INSTRUCTOR_CONFLICT_MESSAGE = "Instructor already has a booking that overlaps this time"
STUDENT_CONFLICT_MESSAGE = "Student already has a booking that overlaps this time"
GENERIC_CONFLICT_MESSAGE = "This time slot conflicts with an existing booking"
CANCELLATION_CREDIT_REASONS = {
    "Cancellation 12-24 hours before lesson (lesson price credit)",
    "Cancellation <12 hours before lesson (50% lesson price credit)",
    "Rescheduled booking cancellation (lesson price credit)",
    "Locked cancellation >=12 hours (lesson price credit)",
    "Locked cancellation <12 hours (50% lesson price credit)",
    "cancel_credit_12_24",
    "cancel_credit_lt12",
    "locked_cancel_ge12",
    "locked_cancel_lt12",
}

# Keep these facade exports stable for tests and extracted mixins that patch through
# app.services.booking_service.
__all__ = [
    "AuditService",
    "BookingCancelled",
    "BookingConflictException",
    "BookingService",
    "GENERIC_CONFLICT_MESSAGE",
    "HundredMsClient",
    "HundredMsError",
    "INSTRUCTOR_CONFLICT_MESSAGE",
    "PRICING_DEFAULTS",
    "PricingService",
    "ROUND_HALF_UP",
    "SimpleNamespace",
    "StripeService",
    "StudentCreditService",
    "TimezoneService",
    "VALID_LOCATION_TYPES",
    "Decimal",
    "_is_test_or_ci",
    "date",
    "datetime",
    "invalidate_on_availability_change",
    "is_verified",
    "must_be_verified_for_public",
    "settings",
    "stripe",
    "timedelta",
]


class BookingService(
    BookingHelpersMixin,
    BookingAuditCacheMixin,
    BookingAvailabilityRulesMixin,
    BookingAvailabilityConflictsMixin,
    BookingAvailabilityOpportunitiesMixin,
    BookingAvailabilityMixin,
    BookingQueryMixin,
    BookingCompletionMixin,
    BookingNotificationsMixin,
    BookingPaymentRetryMixin,
    BookingPaymentMixin,
    BookingLockResolutionMixin,
    BookingLockMixin,
    BookingNoShowSettlementMixin,
    BookingNoShowResolutionMixin,
    BookingNoShowMixin,
    BookingCreationPaymentMixin,
    BookingCreationMixin,
    BookingCancellationCleanupMixin,
    BookingCancellationStripeMixin,
    BookingCancellationLateFinalizeMixin,
    BookingCancellationFinalizeMixin,
    BookingCancellationMixin,
    BookingRescheduleCreationMixin,
    BookingRescheduleExecutionMixin,
    BookingRescheduleMixin,
    BaseService,
):
    """
    Service layer for booking operations.

    Centralizes all booking business logic and coordinates
    with other services.
    """

    # Attribute type annotations to help static typing
    repository: "BookingRepository"
    availability_repository: "AvailabilityRepository"
    conflict_checker_repository: "ConflictCheckerRepository"
    cache_service: Optional[CacheServiceSyncAdapter]
    config_service: ConfigService
    notification_service: NotificationService
    event_outbox_repository: "EventOutboxRepository"
    audit_repository: "AuditRepository"
    event_publisher: EventPublisher

    def __init__(
        self,
        db: Session,
        notification_service: Optional[NotificationService] = None,
        event_publisher: Optional[EventPublisher] = None,
        repository: Optional["BookingRepository"] = None,
        conflict_checker_repository: Optional["ConflictCheckerRepository"] = None,
        cache_service: Optional[CacheService | CacheServiceSyncAdapter] = None,
        system_message_service: Optional[SystemMessageService] = None,
        config_service: Optional[ConfigService] = None,
        pricing_service: Optional[PricingService] = None,
    ):
        """
        Initialize booking service.

        Args:
            db: Database session
            notification_service: Optional notification service instance
            event_publisher: Optional event publisher for async side effects
            repository: Optional BookingRepository instance
            conflict_checker_repository: Optional ConflictCheckerRepository instance
            cache_service: Optional cache service for invalidation
            system_message_service: Optional system message service for conversation messages
            config_service: Optional config service for booking rules and pricing config
            pricing_service: Optional pricing service for commission tier refresh
        """
        cache_impl = cache_service
        cache_adapter: Optional[CacheServiceSyncAdapter] = None
        if isinstance(cache_impl, CacheServiceSyncAdapter):
            cache_adapter = cache_impl
        elif isinstance(cache_impl, CacheService):
            cache_adapter = CacheServiceSyncAdapter(cache_impl)
        super().__init__(db, cache=cache_adapter)
        self.config_service = config_service or ConfigService(db)
        self.pricing_service = pricing_service or PricingService(db)
        self.notification_service = notification_service or NotificationService(db, cache_adapter)
        self.event_publisher = event_publisher or EventPublisher(JobRepository(db))
        self.system_message_service = system_message_service or SystemMessageService(db)
        # Pass cache_service to BookingRepository for caching support
        if repository:
            self.repository = repository
        else:
            from ..repositories.booking_repository import BookingRepository

            self.repository = BookingRepository(db, cache_service=cache_adapter)
        self.availability_repository = RepositoryFactory.create_availability_repository(db)
        self.conflict_checker_repository = (
            conflict_checker_repository or RepositoryFactory.create_conflict_checker_repository(db)
        )
        self.conflict_checker = ConflictChecker(
            db,
            repository=self.conflict_checker_repository,
            config_service=self.config_service,
        )
        self.cache_service = cache_adapter
        self.service_area_repository = RepositoryFactory.create_instructor_service_area_repository(
            db
        )
        self.filter_repository = FilterRepository(db)
        self.event_outbox_repository = RepositoryFactory.create_event_outbox_repository(db)
        self.audit_repository = RepositoryFactory.create_audit_repository(db)
