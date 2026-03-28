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

from datetime import date, datetime, time, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
import logging
import os
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, Dict, Optional, Tuple, cast

from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session
import stripe

from ..constants.pricing_defaults import PRICING_DEFAULTS
from ..core.bgc_policy import is_verified, must_be_verified_for_public
from ..core.config import settings
from ..core.constants import (
    VALID_LOCATION_TYPES,
)
from ..core.enums import RoleName
from ..core.exceptions import (
    BookingConflictException,
    BusinessRuleException,
    ForbiddenException,
    NotFoundException,
    RepositoryException,
    ServiceException,
    ValidationException,
)
from ..events import BookingCancelled, EventPublisher
from ..integrations.hundredms_client import HundredMsClient, HundredMsError
from ..models.booking import Booking, BookingStatus, PaymentStatus
from ..models.instructor import InstructorProfile
from ..models.service_catalog import InstructorService
from ..models.user import User
from ..repositories.factory import RepositoryFactory
from ..repositories.filter_repository import FilterRepository
from ..repositories.job_repository import JobRepository
from ..schemas.booking import BookingCreate, BookingRescheduleRequest
from ..utils.safe_cast import safe_float as _safe_float, safe_str as _safe_str
from .base import BaseService
from .booking.availability_service import BookingAvailabilityMixin
from .booking.completion_service import BookingCompletionMixin
from .booking.helpers import BookingHelpersMixin, _is_test_or_ci
from .booking.notifications import BookingNotificationsMixin
from .booking.query_service import BookingQueryMixin
from .cache_service import CacheService, CacheServiceSyncAdapter
from .config_service import ConfigService
from .conflict_checker import ConflictChecker
from .notification_service import NotificationService
from .pricing_service import PricingService
from .stripe_service import StripeService
from .student_credit_service import StudentCreditService
from .system_message_service import SystemMessageService
from .timezone_service import TimezoneService

if TYPE_CHECKING:
    # AvailabilitySlot removed - bitmap-only storage now
    from ..models.booking_transfer import BookingTransfer
    from ..repositories.audit_repository import AuditRepository
    from ..repositories.availability_repository import AvailabilityRepository
    from ..repositories.booking_repository import BookingRepository
    from ..repositories.conflict_checker_repository import ConflictCheckerRepository
    from ..repositories.event_outbox_repository import EventOutboxRepository

logger = logging.getLogger(__name__)

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


class BookingService(
    BookingHelpersMixin,
    BookingAvailabilityMixin,
    BookingQueryMixin,
    BookingCompletionMixin,
    BookingNotificationsMixin,
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

    @BaseService.measure_operation("create_booking")
    def create_booking(
        self, student: User, booking_data: BookingCreate, selected_duration: int
    ) -> Booking:
        """
        Create an instant booking using selected duration.

        REFACTORED: Split into helper methods to stay under 50 lines.

        Args:
            student: The student creating the booking
            booking_data: Booking creation data with date/time range
            selected_duration: Selected duration in minutes

        Returns:
            Created booking instance

        Raises:
            ValidationException: If validation fails
            NotFoundException: If resources not found
            BusinessRuleException: If business rules violated
            ConflictException: If time slot already booked
        """
        self.log_operation(
            "create_booking",
            student_id=student.id,
            instructor_id=booking_data.instructor_id,
            date=booking_data.booking_date,
            selected_duration=selected_duration,
        )
        self._validate_min_session_duration_floor(selected_duration)

        # 1. Validate and load required data
        service, instructor_profile = self._validate_booking_prerequisites(student, booking_data)

        # 2. Validate selected duration (strict for new bookings)
        if selected_duration not in service.duration_options:
            raise BusinessRuleException(
                f"Invalid duration {selected_duration}. Available options: {service.duration_options}"
            )

        # 3. Calculate end time for conflict checking
        calculated_end_time = self._calculate_and_validate_end_time(
            booking_data.booking_date,
            booking_data.start_time,
            selected_duration,
        )
        booking_data.end_time = calculated_end_time

        # 4. Ensure requested interval fits published availability (bitmap V2)
        self._validate_against_availability_bits(booking_data, instructor_profile)

        # 5. Create the booking with transaction-scoped conflict protection
        transactional_repo = cast(Any, self.repository)
        try:
            with transactional_repo.transaction():
                self._acquire_booking_create_advisory_lock(
                    booking_data.instructor_id,
                    booking_data.booking_date,
                )
                self._check_conflicts_and_rules(booking_data, service, instructor_profile, student)
                booking = self._create_booking_record(
                    student, booking_data, service, instructor_profile, selected_duration
                )
                self._enqueue_booking_outbox_event(booking, "booking.created")
                audit_after = self._snapshot_booking(booking)
                self._write_booking_audit(
                    booking,
                    "create",
                    actor=student,
                    before=None,
                    after=audit_after,
                    default_role=RoleName.STUDENT.value,
                )
        except IntegrityError as exc:
            message, scope = self._resolve_integrity_conflict_message(exc)
            conflict_details = self._build_conflict_details(booking_data, student.id)
            if scope:
                conflict_details["conflict_scope"] = scope
            raise BookingConflictException(
                message=message,
                details=conflict_details,
            ) from exc
        except OperationalError as exc:
            if self._is_deadlock_error(exc):
                conflict_details = self._build_conflict_details(booking_data, student.id)
                raise BookingConflictException(
                    message=GENERIC_CONFLICT_MESSAGE,
                    details=conflict_details,
                ) from exc
            raise
        except RepositoryException as exc:
            self._raise_conflict_from_repo_error(exc, booking_data, student.id)

        # 7. Handle post-creation tasks
        self._handle_post_booking_tasks(booking)

        return booking

    @BaseService.measure_operation("create_booking_with_payment_setup")
    def create_booking_with_payment_setup(
        self,
        student: User,
        booking_data: BookingCreate,
        selected_duration: int,
        rescheduled_from_booking_id: Optional[str] = None,
    ) -> Booking:
        """
        Create a booking with payment setup (Phase 2.1).

        Similar to create_booking but:
        1. Sets status to 'PENDING' initially
        2. Creates Stripe SetupIntent for card collection
        3. Returns booking with setup_intent_client_secret attached

        Args:
            student: The student creating the booking
            booking_data: Booking creation data
            selected_duration: Selected duration in minutes

        Returns:
            Booking with setup_intent_client_secret attached
        """
        from ..services.stripe_service import StripeService

        self.log_operation(
            "create_booking_with_payment_setup",
            student_id=student.id,
            instructor_id=booking_data.instructor_id,
            date=booking_data.booking_date,
        )
        self._validate_min_session_duration_floor(selected_duration)

        # 1. Validate and load required data
        service, instructor_profile = self._validate_booking_prerequisites(student, booking_data)

        # 2. Validate selected duration
        if selected_duration not in service.duration_options:
            raise BusinessRuleException(
                f"Invalid duration {selected_duration}. Available options: {service.duration_options}"
            )

        # 3. Calculate end time
        calculated_end_time = self._calculate_and_validate_end_time(
            booking_data.booking_date,
            booking_data.start_time,
            selected_duration,
        )
        booking_data.end_time = calculated_end_time

        # 4. Ensure requested interval fits published availability (bitmap V2)
        self._validate_against_availability_bits(booking_data, instructor_profile)

        # 5. Create booking with PENDING status initially and transaction-scoped conflict protection
        transactional_repo = cast(Any, self.repository)
        try:
            with transactional_repo.transaction():
                self._acquire_booking_create_advisory_lock(
                    booking_data.instructor_id,
                    booking_data.booking_date,
                )
                self._check_conflicts_and_rules(booking_data, service, instructor_profile, student)
                booking = self._create_booking_record(
                    student, booking_data, service, instructor_profile, selected_duration
                )

                # If this booking was created via reschedule, persist linkage and original lesson datetime
                # for fair cancellation policy (Part 4b: Fair Reschedule Loophole Fix)
                #
                # IMPORTANT: We store the IMMEDIATE previous booking's lesson datetime, NOT traced
                # back to the very first booking in a chain. The question we're answering is:
                # "Was the user in a penalty window when they made THIS reschedule?"
                # That's relative to the booking they're rescheduling FROM.
                #
                # Example: A → B → C (if Part 5 weren't blocking chains)
                # When creating C from B, original_lesson_datetime = B's lesson time
                # NOT: trace back to find A's lesson time
                if rescheduled_from_booking_id:
                    # Fetch the IMMEDIATE previous booking (NOT the chain's original)
                    previous_booking = self.repository.get_by_id(rescheduled_from_booking_id)
                    original_lesson_dt = None
                    if previous_booking:
                        # Store the previous booking's lesson datetime for fair cancellation policy
                        original_lesson_dt = self._get_booking_start_utc(previous_booking)

                    updated_booking = self.repository.update(
                        booking.id,
                        rescheduled_from_booking_id=rescheduled_from_booking_id,
                    )
                    if updated_booking is not None:
                        booking = updated_booking
                    if previous_booking:
                        # Policy-critical satellite writes — must succeed
                        previous_reschedule = self.repository.ensure_reschedule(previous_booking.id)
                        current_reschedule = self.repository.ensure_reschedule(booking.id)
                        current_reschedule.original_lesson_datetime = original_lesson_dt
                        previous_reschedule.rescheduled_to_booking_id = booking.id
                        if bool(previous_reschedule.late_reschedule_used):
                            current_reschedule.late_reschedule_used = True
                        # Analytics-only counter — safe to swallow
                        try:
                            previous_count = int(previous_reschedule.reschedule_count or 0)
                            new_count = previous_count + 1
                            previous_reschedule.reschedule_count = new_count
                            current_reschedule.reschedule_count = new_count
                        except Exception:
                            logger.warning(
                                "Failed to increment reschedule_count for booking %s",
                                booking.id,
                                exc_info=True,
                            )
                # Override status to PENDING until payment confirmed
                booking.status = BookingStatus.PENDING
                bp = self.repository.ensure_payment(booking.id)
                bp.payment_status = PaymentStatus.PAYMENT_METHOD_REQUIRED.value
                self._enqueue_booking_outbox_event(booking, "booking.created")

                # Transaction handles flush/commit automatically
                audit_after = self._snapshot_booking(booking)
                self._write_booking_audit(
                    booking,
                    "create",
                    actor=student,
                    before=None,
                    after=audit_after,
                    default_role=RoleName.STUDENT.value,
                )
        except IntegrityError as exc:
            message, scope = self._resolve_integrity_conflict_message(exc)
            conflict_details = self._build_conflict_details(booking_data, student.id)
            if scope:
                conflict_details["conflict_scope"] = scope
            raise BookingConflictException(
                message=message,
                details=conflict_details,
            ) from exc
        except OperationalError as exc:
            if self._is_deadlock_error(exc):
                conflict_details = self._build_conflict_details(booking_data, student.id)
                raise BookingConflictException(
                    message=GENERIC_CONFLICT_MESSAGE,
                    details=conflict_details,
                ) from exc
            raise
        except RepositoryException as exc:
            self._raise_conflict_from_repo_error(exc, booking_data, student.id)

        # ========== Phase 2: Stripe SetupIntent (NO transaction) ==========
        stripe_service = StripeService(
            self.db,
            config_service=self.config_service,
            pricing_service=PricingService(self.db),
        )

        stripe_customer = stripe_service.get_or_create_customer(student.id)

        setup_intent: Any = None
        try:
            # Attempt real Stripe call; tests patch this in CI
            setup_intent = stripe.SetupIntent.create(
                customer=stripe_customer.stripe_customer_id,
                automatic_payment_methods={"enabled": True, "allow_redirects": "never"},
                usage="off_session",  # Will be used for future off-session payments
                metadata={
                    "booking_id": booking.id,
                    "student_id": student.id,
                    "instructor_id": booking_data.instructor_id,
                    "amount_cents": int(booking.total_price * 100),
                },
            )
        except Exception as e:
            site_mode = (os.getenv("SITE_MODE", "") or settings.site_mode).lower()
            is_test_or_ci = _is_test_or_ci()
            if site_mode == "prod" or not is_test_or_ci:
                logger.error(
                    "SetupIntent creation failed for booking %s (site_mode=%s, test_or_ci=%s)",
                    booking.id,
                    site_mode,
                    is_test_or_ci,
                    exc_info=True,
                )
                raise

            # Test/CI fallback to keep deterministic fixtures when Stripe is unavailable.
            logger.warning(
                "SetupIntent creation failed for booking %s in test/CI: %s. Falling back to mock.",
                booking.id,
                e,
            )
            setup_intent = SimpleNamespace(
                id=f"seti_mock_{booking.id}",
                client_secret=f"seti_mock_secret_{booking.id}",
                status="requires_payment_method",
            )

        # ========== Phase 3: Persist SetupIntent (quick transaction) ==========
        with self.transaction():
            refreshed_booking = self.repository.get_by_id(booking.id)
            if not refreshed_booking:
                raise NotFoundException("Booking not found after setup intent creation")

            # Avoid mixing SetupIntent IDs with PaymentIntent IDs.
            # PaymentIntent IDs are stored later during authorization.
            setattr(
                refreshed_booking,
                "setup_intent_client_secret",
                getattr(setup_intent, "client_secret", None),
            )

            from ..repositories.payment_repository import PaymentRepository

            payment_repo = PaymentRepository(self.db)
            payment_repo.create_payment_event(
                booking_id=refreshed_booking.id,
                event_type="setup_intent_created",
                event_data={
                    "setup_intent_id": setup_intent.id,
                    "status": setup_intent.status,
                },
            )

            booking = refreshed_booking

        # The checkout flow creates bookings through this path, so availability/search
        # caches must be invalidated here after the booking transaction commits.
        try:
            self._invalidate_booking_caches(booking)
        except Exception:
            logger.debug(
                "Failed to invalidate booking caches after payment setup for booking %s",
                booking.id,
                exc_info=True,
            )

        self.log_operation("create_booking_with_payment_setup_completed", booking_id=booking.id)
        return booking

    def _validate_rescheduled_booking_inputs(
        self,
        student: User,
        booking_data: BookingCreate,
        selected_duration: int,
        original_booking_id: str,
    ) -> tuple[InstructorService, InstructorProfile, Booking]:
        """Validate the common inputs needed to create a replacement booking."""
        self._validate_min_session_duration_floor(selected_duration)

        existing_booking = self.repository.get_by_id(original_booking_id)
        if not existing_booking:
            raise NotFoundException("Original booking not found")
        if booking_data.instructor_id != existing_booking.instructor_id:
            raise BusinessRuleException(
                "Cannot change instructor during reschedule. Please cancel and create a new booking."
            )

        service, instructor_profile = self._validate_booking_prerequisites(student, booking_data)

        if selected_duration not in service.duration_options:
            raise BusinessRuleException(
                f"Invalid duration {selected_duration}. Available options: {service.duration_options}"
            )

        booking_data.end_time = self._calculate_and_validate_end_time(
            booking_data.booking_date,
            booking_data.start_time,
            selected_duration,
        )
        self._validate_against_availability_bits(booking_data, instructor_profile)
        return service, instructor_profile, existing_booking

    def _create_rescheduled_booking_base_in_transaction(
        self,
        student: User,
        booking_data: BookingCreate,
        selected_duration: int,
        original_booking_id: str,
        service: InstructorService,
        instructor_profile: InstructorProfile,
    ) -> tuple[Booking, Booking, Any, Any]:
        """Create a replacement booking and reschedule linkage inside an active transaction."""
        self._acquire_booking_create_advisory_lock(
            booking_data.instructor_id,
            booking_data.booking_date,
        )
        self._check_conflicts_and_rules(booking_data, service, instructor_profile, student)
        booking = self._create_booking_record(
            student, booking_data, service, instructor_profile, selected_duration
        )

        old_booking = self.repository.get_by_id(original_booking_id)
        if not old_booking:
            raise NotFoundException("Original booking not found")
        if booking_data.instructor_id != old_booking.instructor_id:
            raise BusinessRuleException(
                "Cannot change instructor during reschedule. Please cancel and create a new booking."
            )

        original_lesson_dt = self._get_booking_start_utc(old_booking)
        booking.rescheduled_from_booking_id = old_booking.id
        old_reschedule = self.repository.ensure_reschedule(old_booking.id)
        current_reschedule = self.repository.ensure_reschedule(booking.id)
        current_reschedule.original_lesson_datetime = original_lesson_dt
        old_reschedule.rescheduled_to_booking_id = booking.id
        previous_count = int(old_reschedule.reschedule_count or 0)
        new_count = previous_count + 1
        old_reschedule.reschedule_count = new_count
        current_reschedule.reschedule_count = new_count
        if bool(old_reschedule.late_reschedule_used):
            current_reschedule.late_reschedule_used = True

        self._enqueue_booking_outbox_event(booking, "booking.created")
        audit_after = self._snapshot_booking(booking)
        self._write_booking_audit(
            booking,
            "create",
            actor=student,
            before=None,
            after=audit_after,
            default_role=RoleName.STUDENT.value,
        )

        return booking, old_booking, old_reschedule, current_reschedule

    def _apply_existing_payment_to_rescheduled_booking_in_transaction(
        self,
        booking: Booking,
        old_booking: Booking,
        *,
        payment_intent_id: str,
        payment_status: Optional[str],
        payment_method_id: Optional[str],
    ) -> None:
        """Copy reusable payment state from the original booking onto the replacement booking."""
        from ..repositories.payment_repository import PaymentRepository

        bp = self.repository.ensure_payment(booking.id)
        bp.payment_intent_id = payment_intent_id
        if isinstance(payment_method_id, str):
            bp.payment_method_id = payment_method_id
        if isinstance(payment_status, str):
            bp.payment_status = payment_status

        try:
            credit_repo = RepositoryFactory.create_credit_repository(self.db)
            reserved_credits = credit_repo.get_reserved_credits_for_booking(
                booking_id=old_booking.id
            )
            reserved_total = 0
            for credit in reserved_credits:
                reserved_total += int(credit.reserved_amount_cents or credit.amount_cents or 0)
                credit.reserved_for_booking_id = booking.id
            if reserved_total > 0:
                bp.credits_reserved_cents = reserved_total
                old_bp = self.repository.ensure_payment(old_booking.id)
                old_bp.credits_reserved_cents = 0
        except Exception as exc:
            logger.warning(
                "Failed to transfer reserved credits from booking %s: %s",
                old_booking.id,
                exc,
            )

        payment_repo = PaymentRepository(self.db)
        payment_record = payment_repo.get_payment_by_intent_id(payment_intent_id)
        if payment_record:
            payment_record.booking_id = booking.id

    def _apply_locked_funds_to_rescheduled_booking_in_transaction(
        self,
        booking: Booking,
        current_reschedule: Any,
    ) -> None:
        """Mark a replacement booking as carrying locked funds."""
        booking.has_locked_funds = True
        bp = self.repository.ensure_payment(booking.id)
        bp.payment_status = PaymentStatus.LOCKED.value
        current_reschedule.late_reschedule_used = True

    def _cancel_booking_without_stripe_in_transaction(
        self,
        booking_id: str,
        user: User,
        reason: Optional[str] = None,
        *,
        clear_payment_intent: bool = False,
    ) -> tuple[Booking, str]:
        """Apply a no-Stripe cancellation inside an active transaction."""
        booking = self.repository.get_booking_with_details(booking_id)
        if not booking:
            raise NotFoundException("Booking not found")

        if user.id not in [booking.student_id, booking.instructor_id]:
            raise ValidationException("You don't have permission to cancel this booking")

        if not booking.is_cancellable:
            raise BusinessRuleException(
                f"Booking cannot be cancelled - current status: {booking.status}"
            )

        audit_before = self._snapshot_booking(booking)

        if clear_payment_intent:
            bp = self.repository.ensure_payment(booking.id)
            bp.payment_intent_id = None

        booking.cancel(user.id, reason)
        self._mark_video_session_terminal_on_cancellation(booking)
        self._enqueue_booking_outbox_event(booking, "booking.cancelled")
        audit_after = self._snapshot_booking(booking)
        default_role = (
            RoleName.STUDENT.value if user.id == booking.student_id else RoleName.INSTRUCTOR.value
        )
        self._write_booking_audit(
            booking,
            "cancel",
            actor=user,
            before=audit_before,
            after=audit_after,
            default_role=default_role,
        )

        cancelled_by_role = "student" if user.id == booking.student_id else "instructor"
        return booking, cancelled_by_role

    def _rollback_reschedule_replacement(self, booking: Booking, user: User) -> None:
        """Best-effort rollback of a replacement booking when the original cannot be cancelled."""
        try:
            if booking.status == BookingStatus.PENDING:
                if self.abort_pending_booking(booking.id):
                    return
            self.cancel_booking(
                booking.id,
                user,
                "Reschedule failed - replacement booking cancelled",
            )
        except Exception as exc:  # pragma: no cover - defensive failure path
            logger.critical(
                "Failed to rollback replacement booking %s after reschedule failure: %s",
                booking.id,
                exc,
                exc_info=True,
            )

    def _normalize_reschedule_location_type(self, original_booking: Booking) -> str:
        """Return a canonical location type for rescheduling the original booking."""
        location_type_raw = getattr(original_booking, "location_type", None)
        if isinstance(location_type_raw, str):
            if location_type_raw in VALID_LOCATION_TYPES:
                return location_type_raw
            raise ValidationException(
                f"Invalid location_type: '{location_type_raw}'. Must be one of: {', '.join(sorted(VALID_LOCATION_TYPES))}"
            )
        return "online"

    def _build_reschedule_booking_data(
        self,
        original_booking: Booking,
        payload: BookingRescheduleRequest,
    ) -> BookingCreate:
        """Carry forward immutable booking fields into a replacement-booking payload."""
        location_type = self._normalize_reschedule_location_type(original_booking)
        student_note = (
            original_booking.student_note
            if isinstance(getattr(original_booking, "student_note", None), str)
            else None
        )
        meeting_location = (
            original_booking.meeting_location
            if isinstance(getattr(original_booking, "meeting_location", None), str)
            else None
        )

        return BookingCreate(
            instructor_id=original_booking.instructor_id,
            instructor_service_id=payload.instructor_service_id
            or original_booking.instructor_service_id,
            booking_date=payload.booking_date,
            start_time=payload.start_time,
            selected_duration=payload.selected_duration,
            student_note=student_note,
            meeting_location=meeting_location,
            location_type=location_type,
            location_address=_safe_str(getattr(original_booking, "location_address", None)),
            location_lat=_safe_float(getattr(original_booking, "location_lat", None)),
            location_lng=_safe_float(getattr(original_booking, "location_lng", None)),
            location_place_id=_safe_str(getattr(original_booking, "location_place_id", None)),
        )

    def _ensure_reschedule_slot_available(
        self,
        *,
        original_booking: Booking,
        booking_data: BookingCreate,
        selected_duration: int,
        student_id: str,
    ) -> None:
        """Validate the proposed replacement slot before any payment or cancellation work."""
        proposed_start = datetime.combine(  # tz-pattern-ok: duration math only
            booking_data.booking_date,
            booking_data.start_time,
            tzinfo=timezone.utc,
        )
        proposed_end_time = (proposed_start + timedelta(minutes=selected_duration)).time()

        availability = self.check_availability(
            instructor_id=original_booking.instructor_id,
            booking_date=booking_data.booking_date,
            start_time=booking_data.start_time,
            end_time=proposed_end_time,
            service_id=booking_data.instructor_service_id,
            instructor_service_id=None,
            exclude_booking_id=original_booking.id,
            location_type=booking_data.location_type,
            student_id=student_id,
            selected_duration=selected_duration,
            location_lat=booking_data.location_lat,
            location_lng=booking_data.location_lng,
        )

        if isinstance(availability, dict):
            is_available = availability.get("available", False)
            reason = availability.get("reason")
        else:
            try:
                is_available = bool(availability)
            except Exception:
                is_available = False
            reason = None

        if not is_available:
            raise BookingConflictException(message=reason or "Requested time is unavailable")

    def _resolve_reschedule_student(self, original_booking: Booking) -> User:
        """Return the canonical student for a reschedule, even if the actor is different."""
        student = getattr(original_booking, "student", None)
        if student is not None and str(getattr(student, "id", "")) == str(
            original_booking.student_id
        ):
            return cast(User, student)

        user_repository = RepositoryFactory.create_user_repository(self.db)
        resolved_student = user_repository.get_by_id(original_booking.student_id)
        if not resolved_student:
            raise NotFoundException("Student not found")
        return resolved_student

    def _create_rescheduled_booking_with_existing_payment_in_transaction(
        self,
        *,
        student: User,
        booking_data: BookingCreate,
        selected_duration: int,
        original_booking_id: str,
        service: InstructorService,
        instructor_profile: InstructorProfile,
        payment_intent_id: str,
        payment_status: Optional[str],
        payment_method_id: Optional[str],
    ) -> tuple[Booking, Booking]:
        """Create a replacement booking and copy the original payment within an open transaction."""
        (
            booking,
            old_booking,
            _old_reschedule,
            _current_reschedule,
        ) = self._create_rescheduled_booking_base_in_transaction(
            student,
            booking_data,
            selected_duration,
            original_booking_id,
            service,
            instructor_profile,
        )
        self._apply_existing_payment_to_rescheduled_booking_in_transaction(
            booking,
            old_booking,
            payment_intent_id=payment_intent_id,
            payment_status=payment_status,
            payment_method_id=payment_method_id,
        )
        return booking, old_booking

    def _create_rescheduled_booking_with_locked_funds_in_transaction(
        self,
        *,
        student: User,
        booking_data: BookingCreate,
        selected_duration: int,
        original_booking_id: str,
        service: InstructorService,
        instructor_profile: InstructorProfile,
    ) -> tuple[Booking, Booking]:
        """Create a replacement booking that inherits a reschedule lock within an open transaction."""
        (
            booking,
            old_booking,
            _old_reschedule,
            current_reschedule,
        ) = self._create_rescheduled_booking_base_in_transaction(
            student,
            booking_data,
            selected_duration,
            original_booking_id,
            service,
            instructor_profile,
        )
        self._apply_locked_funds_to_rescheduled_booking_in_transaction(booking, current_reschedule)
        return booking, old_booking

    @BaseService.measure_operation("reschedule_booking")
    def reschedule_booking(
        self,
        *,
        booking_id: str,
        payload: BookingRescheduleRequest,
        current_user: User,
    ) -> Booking:
        """Reschedule a booking while keeping cancellation and replacement creation consistent."""
        original_booking = self.get_booking_for_user(booking_id, current_user)
        if not original_booking:
            raise NotFoundException("Booking not found")

        self.validate_reschedule_allowed(original_booking)
        reschedule_student = self._resolve_reschedule_student(original_booking)

        new_booking_data = self._build_reschedule_booking_data(original_booking, payload)
        self._ensure_reschedule_slot_available(
            original_booking=original_booking,
            booking_data=new_booking_data,
            selected_duration=payload.selected_duration,
            student_id=str(reschedule_student.id),
        )

        payment_detail = original_booking.payment_detail
        raw_payment_intent_id = payment_detail.payment_intent_id if payment_detail else None
        raw_payment_status = payment_detail.payment_status if payment_detail else None
        raw_payment_method_id = payment_detail.payment_method_id if payment_detail else None

        normalized_payment_status = raw_payment_status
        if raw_payment_status == "requires_capture":
            normalized_payment_status = PaymentStatus.AUTHORIZED.value
        elif raw_payment_status == "succeeded":
            normalized_payment_status = PaymentStatus.SETTLED.value

        reuse_payment = (
            isinstance(raw_payment_intent_id, str)
            and raw_payment_intent_id.startswith("pi_")
            and isinstance(normalized_payment_status, str)
            and normalized_payment_status
            in {PaymentStatus.AUTHORIZED.value, PaymentStatus.SETTLED.value}
        )

        initiator_role = (
            "student" if current_user.id == original_booking.student_id else "instructor"
        )
        hours_until_original = self.get_hours_until_start(original_booking)
        should_lock = self.should_trigger_lock(original_booking, initiator_role)
        force_stripe_cancel = initiator_role == "student" and hours_until_original < 12

        if should_lock:
            self.activate_lock_for_reschedule(original_booking.id)
            return self._reschedule_with_lock(
                original_booking=original_booking,
                booking_data=new_booking_data,
                selected_duration=payload.selected_duration,
                current_user=current_user,
                reschedule_student=reschedule_student,
            )

        if reuse_payment and not force_stripe_cancel:
            return self._reschedule_with_existing_payment(
                original_booking=original_booking,
                booking_data=new_booking_data,
                selected_duration=payload.selected_duration,
                current_user=current_user,
                reschedule_student=reschedule_student,
                payment_intent_id=cast(str, raw_payment_intent_id),
                payment_status=cast(Optional[str], normalized_payment_status),
                payment_method_id=cast(Optional[str], raw_payment_method_id),
            )

        return self._reschedule_with_new_payment(
            original_booking=original_booking,
            booking_data=new_booking_data,
            selected_duration=payload.selected_duration,
            current_user=current_user,
            reschedule_student=reschedule_student,
        )

    def _reschedule_with_lock(
        self,
        *,
        original_booking: Booking,
        booking_data: BookingCreate,
        selected_duration: int,
        current_user: User,
        reschedule_student: User,
    ) -> Booking:
        """Handle the LOCK reschedule path with one transaction for create + cancel."""
        service, instructor_profile, _ = self._validate_rescheduled_booking_inputs(
            reschedule_student,
            booking_data,
            selected_duration,
            original_booking.id,
        )
        transactional_repo = cast(Any, self.repository)
        old_booking: Optional[Booking] = None
        try:
            with transactional_repo.transaction():
                (
                    replacement_booking,
                    old_booking,
                ) = self._create_rescheduled_booking_with_locked_funds_in_transaction(
                    student=reschedule_student,
                    booking_data=booking_data,
                    selected_duration=selected_duration,
                    original_booking_id=original_booking.id,
                    service=service,
                    instructor_profile=instructor_profile,
                )
                (
                    cancelled_booking,
                    cancelled_by_role,
                ) = self._cancel_booking_without_stripe_in_transaction(
                    original_booking.id,
                    current_user,
                    "Rescheduled",
                )
        except IntegrityError as exc:
            message, scope = self._resolve_integrity_conflict_message(exc)
            conflict_details = self._build_conflict_details(
                booking_data, str(reschedule_student.id)
            )
            if scope:
                conflict_details["conflict_scope"] = scope
            raise BookingConflictException(
                message=message,
                details=conflict_details,
            ) from exc
        except OperationalError as exc:
            if self._is_deadlock_error(exc):
                conflict_details = self._build_conflict_details(
                    booking_data, str(reschedule_student.id)
                )
                raise BookingConflictException(
                    message=GENERIC_CONFLICT_MESSAGE,
                    details=conflict_details,
                ) from exc
            raise
        except RepositoryException as exc:
            self._raise_conflict_from_repo_error(exc, booking_data, str(reschedule_student.id))

        self._handle_post_booking_tasks(
            replacement_booking,
            is_reschedule=old_booking is not None,
            old_booking=old_booking,
        )
        self._post_cancellation_actions(cancelled_booking, cancelled_by_role)
        return replacement_booking

    def _reschedule_with_existing_payment(
        self,
        *,
        original_booking: Booking,
        booking_data: BookingCreate,
        selected_duration: int,
        current_user: User,
        reschedule_student: User,
        payment_intent_id: str,
        payment_status: Optional[str],
        payment_method_id: Optional[str],
    ) -> Booking:
        """Handle the payment-reuse reschedule path with one transaction for create + cancel."""
        service, instructor_profile, _ = self._validate_rescheduled_booking_inputs(
            reschedule_student,
            booking_data,
            selected_duration,
            original_booking.id,
        )
        transactional_repo = cast(Any, self.repository)
        old_booking: Optional[Booking] = None
        try:
            with transactional_repo.transaction():
                (
                    replacement_booking,
                    old_booking,
                ) = self._create_rescheduled_booking_with_existing_payment_in_transaction(
                    student=reschedule_student,
                    booking_data=booking_data,
                    selected_duration=selected_duration,
                    original_booking_id=original_booking.id,
                    service=service,
                    instructor_profile=instructor_profile,
                    payment_intent_id=payment_intent_id,
                    payment_status=payment_status,
                    payment_method_id=payment_method_id,
                )
                (
                    cancelled_booking,
                    cancelled_by_role,
                ) = self._cancel_booking_without_stripe_in_transaction(
                    original_booking.id,
                    current_user,
                    "Rescheduled",
                    clear_payment_intent=True,
                )
        except IntegrityError as exc:
            message, scope = self._resolve_integrity_conflict_message(exc)
            conflict_details = self._build_conflict_details(
                booking_data, str(reschedule_student.id)
            )
            if scope:
                conflict_details["conflict_scope"] = scope
            raise BookingConflictException(
                message=message,
                details=conflict_details,
            ) from exc
        except OperationalError as exc:
            if self._is_deadlock_error(exc):
                conflict_details = self._build_conflict_details(
                    booking_data, str(reschedule_student.id)
                )
                raise BookingConflictException(
                    message=GENERIC_CONFLICT_MESSAGE,
                    details=conflict_details,
                ) from exc
            raise
        except RepositoryException as exc:
            self._raise_conflict_from_repo_error(exc, booking_data, str(reschedule_student.id))

        self._handle_post_booking_tasks(
            replacement_booking,
            is_reschedule=old_booking is not None,
            old_booking=old_booking,
        )
        self._post_cancellation_actions(cancelled_booking, cancelled_by_role)
        return replacement_booking

    def _reschedule_with_new_payment(
        self,
        *,
        original_booking: Booking,
        booking_data: BookingCreate,
        selected_duration: int,
        current_user: User,
        reschedule_student: User,
    ) -> Booking:
        """Handle the new-payment reschedule path with compensation if the original cancel fails."""
        has_payment_method, stripe_payment_method_id = self.validate_reschedule_payment_method(
            str(reschedule_student.id)
        )
        if not has_payment_method or not stripe_payment_method_id:
            raise ValidationException(
                "A payment method is required to reschedule this lesson. Please add a payment method and try again.",
                code="payment_method_required_for_reschedule",
            )

        replacement_booking = self.create_booking_with_payment_setup(
            reschedule_student,
            booking_data,
            selected_duration,
            original_booking.id,
        )

        try:
            replacement_booking = self.confirm_booking_payment(
                replacement_booking.id,
                reschedule_student,
                stripe_payment_method_id,
                False,
            )
        except Exception as exc:
            logger.error(
                "Failed to confirm payment for rescheduled booking %s: %s",
                replacement_booking.id,
                exc,
            )
            self.abort_pending_booking(replacement_booking.id)
            raise ValidationException(
                "We couldn't process your payment method. Please try again or update your payment method.",
                code="payment_confirmation_failed",
            ) from exc

        try:
            self.cancel_booking(original_booking.id, current_user, "Rescheduled")
        except Exception as exc:
            logger.critical(
                "Failed to cancel original booking %s after creating replacement booking %s during reschedule: %s",
                original_booking.id,
                replacement_booking.id,
                exc,
                exc_info=True,
            )
            self._rollback_reschedule_replacement(replacement_booking, current_user)
            raise

        return replacement_booking

    @BaseService.measure_operation("create_rescheduled_booking_with_existing_payment")
    def create_rescheduled_booking_with_existing_payment(
        self,
        student: User,
        booking_data: BookingCreate,
        selected_duration: int,
        original_booking_id: str,
        payment_intent_id: str,
        payment_status: Optional[str],
        payment_method_id: Optional[str],
    ) -> Booking:
        """
        Create a rescheduled booking that reuses an existing PaymentIntent.

        This avoids creating a new PaymentIntent when the original payment was
        already authorized or captured.
        """

        self.log_operation(
            "create_rescheduled_booking_with_existing_payment",
            student_id=student.id,
            instructor_id=booking_data.instructor_id,
            date=booking_data.booking_date,
            original_booking_id=original_booking_id,
        )
        service, instructor_profile, _ = self._validate_rescheduled_booking_inputs(
            student,
            booking_data,
            selected_duration,
            original_booking_id,
        )

        # 5. Create the booking with transaction-scoped conflict protection
        transactional_repo = cast(Any, self.repository)
        old_booking: Optional[Booking] = None
        try:
            with transactional_repo.transaction():
                (
                    booking,
                    old_booking,
                ) = self._create_rescheduled_booking_with_existing_payment_in_transaction(
                    student=student,
                    booking_data=booking_data,
                    selected_duration=selected_duration,
                    original_booking_id=original_booking_id,
                    service=service,
                    instructor_profile=instructor_profile,
                    payment_intent_id=payment_intent_id,
                    payment_status=payment_status,
                    payment_method_id=payment_method_id,
                )
        except IntegrityError as exc:
            message, scope = self._resolve_integrity_conflict_message(exc)
            conflict_details = self._build_conflict_details(booking_data, student.id)
            if scope:
                conflict_details["conflict_scope"] = scope
            raise BookingConflictException(
                message=message,
                details=conflict_details,
            ) from exc
        except OperationalError as exc:
            if self._is_deadlock_error(exc):
                conflict_details = self._build_conflict_details(booking_data, student.id)
                raise BookingConflictException(
                    message=GENERIC_CONFLICT_MESSAGE,
                    details=conflict_details,
                ) from exc
            raise
        except RepositoryException as exc:
            self._raise_conflict_from_repo_error(exc, booking_data, student.id)

        # 7. Handle post-creation tasks
        self._handle_post_booking_tasks(
            booking,
            is_reschedule=old_booking is not None,
            old_booking=old_booking,
        )

        return booking

    @BaseService.measure_operation("create_rescheduled_booking_with_locked_funds")
    def create_rescheduled_booking_with_locked_funds(
        self,
        student: User,
        booking_data: BookingCreate,
        selected_duration: int,
        original_booking_id: str,
    ) -> Booking:
        """
        Create a rescheduled booking when LOCK is active.

        The new booking carries a has_locked_funds flag and does not reuse
        the original payment intent.
        """
        self.log_operation(
            "create_rescheduled_booking_with_locked_funds",
            student_id=student.id,
            instructor_id=booking_data.instructor_id,
            date=booking_data.booking_date,
            original_booking_id=original_booking_id,
        )
        service, instructor_profile, _ = self._validate_rescheduled_booking_inputs(
            student,
            booking_data,
            selected_duration,
            original_booking_id,
        )

        # 5. Create booking with transaction-scoped conflict protection
        transactional_repo = cast(Any, self.repository)
        old_booking: Optional[Booking] = None
        try:
            with transactional_repo.transaction():
                (
                    booking,
                    old_booking,
                ) = self._create_rescheduled_booking_with_locked_funds_in_transaction(
                    student=student,
                    booking_data=booking_data,
                    selected_duration=selected_duration,
                    original_booking_id=original_booking_id,
                    service=service,
                    instructor_profile=instructor_profile,
                )
        except IntegrityError as exc:
            message, scope = self._resolve_integrity_conflict_message(exc)
            conflict_details = self._build_conflict_details(booking_data, student.id)
            if scope:
                conflict_details["conflict_scope"] = scope
            raise BookingConflictException(
                message=message,
                details=conflict_details,
            ) from exc
        except OperationalError as exc:
            if self._is_deadlock_error(exc):
                conflict_details = self._build_conflict_details(booking_data, student.id)
                raise BookingConflictException(
                    message=GENERIC_CONFLICT_MESSAGE,
                    details=conflict_details,
                ) from exc
            raise
        except RepositoryException as exc:
            self._raise_conflict_from_repo_error(exc, booking_data, student.id)

        self._handle_post_booking_tasks(
            booking,
            is_reschedule=old_booking is not None,
            old_booking=old_booking,
        )

        return booking

    def _determine_auth_timing(self, lesson_start_at: datetime) -> Dict[str, Any]:
        """
        Determine authorization timing based on lesson start time.

        Returns:
            {
                "immediate": bool,
                "scheduled_for": datetime | None,
                "initial_payment_status": str,
                "hours_until_lesson": float,
            }
        """
        if lesson_start_at.tzinfo is None:
            lesson_start_at = lesson_start_at.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        hours_until_lesson = (lesson_start_at - now).total_seconds() / 3600

        if hours_until_lesson >= 24:
            scheduled_for = lesson_start_at - timedelta(hours=24)
            return {
                "immediate": False,
                "scheduled_for": scheduled_for,
                "initial_payment_status": PaymentStatus.SCHEDULED.value,
                "hours_until_lesson": hours_until_lesson,
            }

        return {
            "immediate": True,
            "scheduled_for": None,
            "initial_payment_status": PaymentStatus.SCHEDULED.value,
            "hours_until_lesson": hours_until_lesson,
        }

    @BaseService.measure_operation("confirm_booking_payment")
    def confirm_booking_payment(
        self,
        booking_id: str,
        student: User,
        payment_method_id: str,
        save_payment_method: bool = False,
    ) -> Booking:
        """
        Confirm payment method for a booking (Phase 2.1 & 2.2).

        1. Validates booking ownership
        2. Saves payment method to booking
        3. Schedules authorization based on lesson timing
        4. Updates status from PENDING to CONFIRMED

        Args:
            booking_id: The booking to confirm
            student: The student confirming payment
            payment_method_id: Stripe payment method ID
            save_payment_method: Whether to save for future use

        Returns:
            Updated booking with confirmed status
        """
        from datetime import datetime

        from ..repositories.payment_repository import PaymentRepository

        self.log_operation("confirm_booking_payment", booking_id=booking_id, student_id=student.id)

        # Defense-in-depth: filter by student at DB level (AUTHZ-VULN-01)
        booking = self.repository.get_booking_for_student(booking_id, student.id)
        if not booking:
            raise NotFoundException("Booking not found")

        if booking.status != BookingStatus.PENDING:
            raise NotFoundException("Booking not found")

        trigger_immediate_auth = False
        immediate_auth_hours_until: Optional[float] = None

        # Save payment method for future use (Stripe call should be outside DB transaction)
        if save_payment_method:
            stripe_service = StripeService(
                self.db,
                config_service=self.config_service,
                pricing_service=PricingService(self.db),
            )
            stripe_service.save_payment_method(
                user_id=student.id, payment_method_id=payment_method_id, set_as_default=False
            )

        with self.transaction():
            # Save payment method
            bp = self.repository.ensure_payment(booking.id)
            bp.payment_method_id = payment_method_id
            bp.payment_status = PaymentStatus.SCHEDULED.value

            # Phase 2.2: Schedule authorization based on lesson timing (UTC)
            booking_start_utc = self._get_booking_start_utc(booking)
            auth_timing = self._determine_auth_timing(booking_start_utc)
            hours_until_lesson = auth_timing["hours_until_lesson"]

            is_gaming_reschedule = False
            hours_from_original: Optional[float] = None
            reschedule_record = self.repository.get_reschedule_by_booking_id(booking.id)
            original_lesson_datetime = (
                reschedule_record.original_lesson_datetime if reschedule_record else None
            )
            if booking.rescheduled_from_booking_id and original_lesson_datetime:
                original_dt = original_lesson_datetime
                if original_dt.tzinfo is None:
                    original_dt = original_dt.replace(tzinfo=timezone.utc)
                reschedule_time = booking.created_at
                if reschedule_time is not None:
                    if reschedule_time.tzinfo is None:
                        reschedule_time = reschedule_time.replace(tzinfo=timezone.utc)
                    hours_from_original_value = (
                        original_dt - reschedule_time
                    ).total_seconds() / 3600
                    hours_from_original = hours_from_original_value
                    is_gaming_reschedule = hours_from_original_value < 24

            if is_gaming_reschedule:
                # Gaming reschedule: authorize immediately to prevent delayed-auth loophole.
                bp.payment_status = PaymentStatus.SCHEDULED.value
                bp.auth_scheduled_for = datetime.now(timezone.utc)
                bp.auth_last_error = None
                bp.auth_failure_count = 0
                trigger_immediate_auth = True
                immediate_auth_hours_until = hours_until_lesson

                payment_repo = PaymentRepository(self.db)
                payment_repo.create_payment_event(
                    booking_id=booking.id,
                    event_type="auth_immediate",
                    event_data={
                        "payment_method_id": payment_method_id,
                        "hours_until_lesson": hours_until_lesson,
                        "hours_from_original": hours_from_original,
                        "scheduled_for": "immediate",
                        "reason": "gaming_reschedule",
                    },
                )

            elif auth_timing["immediate"]:
                # Lesson is within 24 hours - mark for immediate authorization by background task
                bp.payment_status = PaymentStatus.SCHEDULED.value
                bp.auth_scheduled_for = datetime.now(timezone.utc)
                bp.auth_last_error = None
                bp.auth_failure_count = 0

                # Create auth event; actual authorization is handled by worker
                payment_repo = PaymentRepository(self.db)
                payment_repo.create_payment_event(
                    booking_id=booking.id,
                    event_type="auth_immediate",
                    event_data={
                        "payment_method_id": payment_method_id,
                        "hours_until_lesson": hours_until_lesson,
                        "scheduled_for": "immediate",
                    },
                )
                trigger_immediate_auth = True
                immediate_auth_hours_until = hours_until_lesson

            else:
                # Lesson is >24 hours away - schedule authorization
                auth_time = auth_timing["scheduled_for"]
                bp.payment_status = PaymentStatus.SCHEDULED.value
                bp.auth_scheduled_for = auth_time
                bp.auth_last_error = None
                bp.auth_failure_count = 0

                # Create scheduled event using repository
                payment_repo = PaymentRepository(self.db)
                payment_repo.create_payment_event(
                    booking_id=booking.id,
                    event_type="auth_scheduled",
                    event_data={
                        "payment_method_id": payment_method_id,
                        "scheduled_for": auth_time.isoformat() if auth_time else None,
                        "hours_until_lesson": hours_until_lesson,
                    },
                )

            # Update booking status to CONFIRMED only when auth is scheduled (>24h)
            # For immediate auth (<24h), confirmation happens after successful authorization.
            if not trigger_immediate_auth:
                booking.status = BookingStatus.CONFIRMED
                booking.confirmed_at = datetime.now(timezone.utc)
            else:
                booking.status = BookingStatus.PENDING
                booking.confirmed_at = None

            # Transaction handles flush/commit automatically

        self.log_operation(
            "confirm_booking_payment_completed",
            booking_id=booking.id,
            payment_status=getattr(booking.payment_detail, "payment_status", None),
        )

        auth_result: Optional[Dict[str, Any]] = None
        if trigger_immediate_auth:
            try:
                from app.tasks.payment_tasks import _process_authorization_for_booking

                auth_result = _process_authorization_for_booking(
                    booking.id, immediate_auth_hours_until or 0.0
                )
                if not auth_result or not auth_result.get("success"):
                    logger.warning(
                        "Immediate auth failed for gaming reschedule booking %s: %s",
                        booking.id,
                        auth_result.get("error") if auth_result else "unknown error",
                    )
            except Exception as exc:
                logger.error(
                    "Immediate auth error for gaming reschedule booking %s: %s",
                    booking.id,
                    exc,
                )

        if auth_result and auth_result.get("success"):
            try:
                with self.transaction():
                    refreshed = self.repository.get_by_id(booking.id)
                    if refreshed and refreshed.status == BookingStatus.PENDING:
                        refreshed.status = BookingStatus.CONFIRMED
                        refreshed.confirmed_at = datetime.now(timezone.utc)
                        refreshed_bp = self.repository.ensure_payment(refreshed.id)
                        if refreshed_bp.payment_status == PaymentStatus.SCHEDULED.value:
                            refreshed_bp.payment_status = PaymentStatus.AUTHORIZED.value
                self.repository.refresh(booking)
            except Exception:
                logger.warning(
                    "Booking %s was updated after immediate authorization, but ORM refresh failed",
                    booking.id,
                    exc_info=True,
                )
        elif trigger_immediate_auth:
            try:
                self.repository.refresh(booking)
            except Exception:
                logger.warning(
                    "Failed to refresh booking %s after immediate authorization attempt",
                    booking.id,
                    exc_info=True,
                )
        # Create system message in conversation only after confirmation
        if booking.status != BookingStatus.CONFIRMED:
            return booking

        try:
            service_name = "Lesson"
            if booking.instructor_service and booking.instructor_service.name:
                service_name = booking.instructor_service.name

            # Check if this is a rescheduled booking
            if booking.rescheduled_from_booking_id:
                old_booking = self.repository.get_by_id(booking.rescheduled_from_booking_id)
                if old_booking:
                    self.system_message_service.create_booking_rescheduled_message(
                        student_id=booking.student_id,
                        instructor_id=booking.instructor_id,
                        booking_id=booking.id,
                        old_date=old_booking.booking_date,
                        old_time=old_booking.start_time,
                        new_date=booking.booking_date,
                        new_time=booking.start_time,
                    )
                else:
                    # Old booking not found, create as new booking
                    self.system_message_service.create_booking_created_message(
                        student_id=booking.student_id,
                        instructor_id=booking.instructor_id,
                        booking_id=booking.id,
                        service_name=service_name,
                        booking_date=booking.booking_date,
                        start_time=booking.start_time,
                    )
            else:
                self.system_message_service.create_booking_created_message(
                    student_id=booking.student_id,
                    instructor_id=booking.instructor_id,
                    booking_id=booking.id,
                    service_name=service_name,
                    booking_date=booking.booking_date,
                    start_time=booking.start_time,
                )
        except Exception as e:
            logger.error("Failed to create system message for booking %s: %s", booking.id, str(e))

        # Invalidate caches so upcoming lists include the newly confirmed booking
        try:
            self._invalidate_booking_caches(booking)
        except Exception:
            # Side-effect only — does not affect booking state.
            logger.debug(
                "Failed to invalidate booking caches after confirmation for booking %s",
                booking.id,
                exc_info=True,
            )
        return booking

    @BaseService.measure_operation("retry_authorization")
    def retry_authorization(self, *, booking_id: str, user: User) -> Dict[str, Any]:
        """
        Retry payment authorization for a booking after failure.
        """
        from ..repositories.payment_repository import PaymentRepository
        from ..services.stripe_service import StripeService

        booking = self.repository.get_booking_with_details(booking_id)
        if not booking:
            raise NotFoundException("Booking not found")

        if booking.student_id != user.id:
            raise ForbiddenException("Only the student can retry payment authorization")

        if booking.status == BookingStatus.CANCELLED:
            raise BusinessRuleException("Booking has been cancelled")

        pd = booking.payment_detail
        cur_payment_status = pd.payment_status if pd is not None else None
        if cur_payment_status not in {
            PaymentStatus.PAYMENT_METHOD_REQUIRED.value,
            PaymentStatus.SCHEDULED.value,
        }:
            raise BusinessRuleException(f"Cannot retry payment in status: {cur_payment_status}")

        payment_repo = PaymentRepository(self.db)
        default_method = payment_repo.get_default_payment_method(user.id)
        payment_method_id = (
            default_method.stripe_payment_method_id
            if default_method and default_method.stripe_payment_method_id
            else (pd.payment_method_id if pd is not None else None)
        )

        if not payment_method_id:
            raise ValidationException("No payment method available for retry")

        stripe_service = StripeService(
            self.db,
            config_service=self.config_service,
            pricing_service=PricingService(self.db),
        )

        ctx = stripe_service.build_charge_context(
            booking_id=booking.id, requested_credit_cents=None
        )

        now = datetime.now(timezone.utc)
        if ctx.student_pay_cents <= 0:
            with self.transaction():
                booking = self.repository.get_booking_with_details(booking_id)
                if not booking:
                    raise NotFoundException("Booking not found")
                bp = self.repository.ensure_payment(booking.id)
                bp.payment_status = PaymentStatus.AUTHORIZED.value
                bp.auth_attempted_at = now
                bp.auth_failure_count = 0
                bp.auth_last_error = None
                bp.payment_method_id = payment_method_id

                payment_repo.create_payment_event(
                    booking_id=booking.id,
                    event_type="auth_retry_succeeded",
                    event_data={
                        "credits_applied_cents": ctx.applied_credit_cents,
                        "authorized_at": now.isoformat(),
                    },
                )

            return {
                "success": True,
                "payment_status": PaymentStatus.AUTHORIZED.value,
                "failure_count": 0,
            }

        pd_for_pi = booking.payment_detail
        raw_pi_id = pd_for_pi.payment_intent_id if pd_for_pi is not None else None
        payment_intent_id = (
            raw_pi_id if isinstance(raw_pi_id, str) and raw_pi_id.startswith("pi_") else None
        )

        stripe_error: Optional[str] = None
        stripe_status: Optional[str] = None
        try:
            if payment_intent_id:
                payment_record = stripe_service.confirm_payment_intent(
                    payment_intent_id, payment_method_id
                )
                stripe_status = getattr(payment_record, "status", None)
            else:
                payment_intent = stripe_service.create_or_retry_booking_payment_intent(
                    booking_id=booking.id,
                    payment_method_id=payment_method_id,
                    requested_credit_cents=None,
                )
                payment_intent_id = getattr(payment_intent, "id", None)
                stripe_status = getattr(payment_intent, "status", None)
        except Exception as exc:
            stripe_error = str(exc)

        success = stripe_status in {"requires_capture", "succeeded"}
        with self.transaction():
            booking = self.repository.get_booking_with_details(booking_id)
            if not booking:
                raise NotFoundException("Booking not found")

            bp = self.repository.ensure_payment(booking.id)
            bp.payment_method_id = payment_method_id
            bp.auth_attempted_at = now
            bp.auth_scheduled_for = None

            if success:
                bp.payment_status = PaymentStatus.AUTHORIZED.value
                bp.payment_intent_id = payment_intent_id
                bp.auth_failure_count = 0
                bp.auth_last_error = None
                payment_repo.create_payment_event(
                    booking_id=booking.id,
                    event_type="auth_retry_succeeded",
                    event_data={
                        "payment_intent_id": payment_intent_id,
                        "authorized_at": now.isoformat(),
                        "amount_cents": ctx.student_pay_cents,
                        "application_fee_cents": ctx.application_fee_cents,
                    },
                )
            else:
                bp.payment_status = PaymentStatus.PAYMENT_METHOD_REQUIRED.value
                bp.auth_failure_count = int(bp.auth_failure_count or 0) + 1
                bp.auth_last_error = stripe_error or stripe_status or "authorization_failed"
                payment_repo.create_payment_event(
                    booking_id=booking.id,
                    event_type="auth_retry_failed",
                    event_data={
                        "payment_intent_id": payment_intent_id,
                        "error": bp.auth_last_error,
                        "failed_at": now.isoformat(),
                    },
                )

        return {
            "success": success,
            "payment_status": bp.payment_status,
            "failure_count": bp.auth_failure_count,
            "error": None if success else bp.auth_last_error,
        }

    @BaseService.measure_operation("cancel_booking")
    def cancel_booking(self, booking_id: str, user: User, reason: Optional[str] = None) -> Booking:
        """
        Cancel a booking.

        Architecture Note (v123): Uses 3-phase pattern to avoid holding DB locks
        during Stripe network calls:
        - Phase 1: Read/validate booking, determine scenario (~5ms)
        - Phase 2: Execute Stripe calls based on scenario (no transaction, 100-500ms)
        - Phase 3: Update booking status, create events (~5ms)

        Args:
            booking_id: ID of booking to cancel
            user: User performing cancellation
            reason: Optional cancellation reason

        Returns:
            Cancelled booking

        Raises:
            NotFoundException: If booking not found
            ValidationException: If user cannot cancel
            BusinessRuleException: If booking not cancellable
        """
        from ..repositories.payment_repository import PaymentRepository

        # ========== PHASE 1: Read/validate (quick transaction) ==========
        with self.transaction():
            # Defense-in-depth: filter by participant at DB level (AUTHZ-VULN-01)
            booking = self.repository.get_booking_for_participant_for_update(booking_id, user.id)
            if not booking:
                raise NotFoundException("Booking not found")

            if booking.status == BookingStatus.CANCELLED:
                return booking

            if not booking.is_cancellable:
                raise BusinessRuleException(
                    f"Booking cannot be cancelled - current status: {booking.status}"
                )

            cancelled_by_role = "student" if user.id == booking.student_id else "instructor"
            lock_ctx: Optional[Dict[str, Any]] = None

            if (
                getattr(booking, "has_locked_funds", False) is True
                and booking.rescheduled_from_booking_id
            ):
                booking_start_utc = self._get_booking_start_utc(booking)
                hours_until = TimezoneService.hours_until(booking_start_utc)
                if cancelled_by_role == "instructor":
                    resolution = "instructor_cancelled"
                elif hours_until >= 12:
                    resolution = "new_lesson_cancelled_ge12"
                else:
                    resolution = "new_lesson_cancelled_lt12"

                lock_ctx = {
                    "locked_booking_id": booking.rescheduled_from_booking_id,
                    "resolution": resolution,
                    "cancelled_by_role": cancelled_by_role,
                    "default_role": (
                        RoleName.STUDENT.value
                        if cancelled_by_role == "student"
                        else RoleName.INSTRUCTOR.value
                    ),
                }
            elif (
                getattr(booking.payment_detail, "payment_status", None)
                == PaymentStatus.LOCKED.value
            ):
                booking_start_utc = self._get_booking_start_utc(booking)
                hours_until = TimezoneService.hours_until(booking_start_utc)
                if cancelled_by_role == "instructor":
                    resolution = "instructor_cancelled"
                elif hours_until >= 12:
                    resolution = "new_lesson_cancelled_ge12"
                else:
                    resolution = "new_lesson_cancelled_lt12"
                lock_ctx = {
                    "locked_booking_id": booking.id,
                    "resolution": resolution,
                    "cancelled_by_role": cancelled_by_role,
                    "default_role": (
                        RoleName.STUDENT.value
                        if cancelled_by_role == "student"
                        else RoleName.INSTRUCTOR.value
                    ),
                }

            if lock_ctx:
                cancel_ctx = lock_ctx
            else:
                # Extract data needed for Phase 2 (avoid holding ORM objects)
                cancel_ctx = self._build_cancellation_context(booking, user)

        # ========== PHASE 2: Stripe calls (NO transaction) ==========
        stripe_results: Dict[str, Any] = {}
        if "locked_booking_id" in cancel_ctx:
            stripe_results = self.resolve_lock_for_booking(
                cancel_ctx["locked_booking_id"],
                cancel_ctx["resolution"],
            )
        else:
            stripe_service = StripeService(
                self.db,
                config_service=self.config_service,
                pricing_service=PricingService(self.db),
            )
            stripe_results = self._execute_cancellation_stripe_calls(cancel_ctx, stripe_service)

        # ========== PHASE 3: Write results (quick transaction) ==========
        with self.transaction():
            # Re-fetch booking to avoid stale ORM object
            booking = self.repository.get_by_id_for_update(booking_id)
            if not booking:
                raise NotFoundException("Booking not found after Stripe calls")

            payment_repo = PaymentRepository(self.db)
            audit_before = self._snapshot_booking(booking)

            if "locked_booking_id" in cancel_ctx:
                # LOCK-driven cancellation: no direct Stripe updates on this booking
                if stripe_results.get("success") or stripe_results.get("skipped"):
                    bp = self.repository.ensure_payment(booking.id)
                    bp.payment_status = PaymentStatus.SETTLED.value
            else:
                # Finalize cancellation with Stripe results
                self._finalize_cancellation(booking, cancel_ctx, stripe_results, payment_repo)

            # Cancel the booking
            booking.cancel(user.id, reason)
            self._mark_video_session_terminal_on_cancellation(booking)
            self._enqueue_booking_outbox_event(booking, "booking.cancelled")
            audit_after = self._snapshot_booking(booking)
            self._write_booking_audit(
                booking,
                "cancel",
                actor=user,
                before=audit_before,
                after=audit_after,
                default_role=cancel_ctx["default_role"],
            )

        cancelled_by_role = cancel_ctx["cancelled_by_role"]

        # Post-transaction: Publish events and notifications
        self._post_cancellation_actions(booking, cancelled_by_role)

        return booking

    @BaseService.measure_operation("cancel_booking_without_stripe")
    def cancel_booking_without_stripe(
        self,
        booking_id: str,
        user: User,
        reason: Optional[str] = None,
        *,
        clear_payment_intent: bool = False,
    ) -> Booking:
        """
        Cancel a booking without invoking Stripe or cancellation policy logic.

        This is intended for reschedule flows where the existing payment is reused.
        """
        with self.transaction():
            booking, cancelled_by_role = self._cancel_booking_without_stripe_in_transaction(
                booking_id,
                user,
                reason,
                clear_payment_intent=clear_payment_intent,
            )
        self._post_cancellation_actions(booking, cancelled_by_role)

        return booking

    def _mark_video_session_terminal_on_cancellation(self, booking: Booking) -> None:
        """Mark booking video session state as terminal on cancellation."""
        video_session = getattr(booking, "video_session", None)
        if video_session is None:
            return

        ended_at = booking.cancelled_at or datetime.now(timezone.utc)
        if video_session.session_ended_at is None:
            video_session.session_ended_at = ended_at

        if (
            video_session.session_duration_seconds is None
            and isinstance(video_session.session_started_at, datetime)
            and isinstance(video_session.session_ended_at, datetime)
        ):
            duration_seconds = int(
                (video_session.session_ended_at - video_session.session_started_at).total_seconds()
            )
            video_session.session_duration_seconds = max(duration_seconds, 0)

    def _build_hundredms_client_for_cleanup(self) -> HundredMsClient | None:
        """Create a 100ms client for post-cancellation cleanup, when configured."""
        if not settings.hundredms_enabled:
            return None

        access_key = (settings.hundredms_access_key or "").strip()
        raw_secret = settings.hundredms_app_secret
        if raw_secret is None:
            if settings.site_mode == "prod":
                raise RuntimeError("HUNDREDMS_APP_SECRET is required in production")
            app_secret = str()
        elif hasattr(raw_secret, "get_secret_value"):
            app_secret = str(raw_secret.get_secret_value()).strip()
        else:
            app_secret = str(raw_secret).strip()

        if not access_key or not app_secret:
            logger.warning(
                "Skipping 100ms room disable for cancellation cleanup due to missing credentials"
            )
            return None

        return HundredMsClient(
            access_key=access_key,
            app_secret=app_secret,
            base_url=settings.hundredms_base_url,
            template_id=(settings.hundredms_template_id or "").strip() or None,
        )

    def _disable_video_room_after_cancellation(self, booking: Booking) -> None:
        """Best-effort 100ms room disable after cancellation commit."""
        video_session = getattr(booking, "video_session", None)
        room_id = getattr(video_session, "room_id", None)
        if not room_id:
            return

        client = self._build_hundredms_client_for_cleanup()
        if client is None:
            return

        try:
            client.disable_room(room_id)
        except HundredMsError as exc:
            logger.warning(
                "Best-effort 100ms room disable failed for booking %s room %s: %s",
                booking.id,
                room_id,
                exc.message,
                extra={"status_code": exc.status_code},
            )
        except Exception as exc:
            logger.warning(
                "Unexpected error during 100ms room disable for booking %s room %s: %s",
                booking.id,
                room_id,
                exc,
            )

    @BaseService.measure_operation("should_trigger_lock")
    def should_trigger_lock(self, booking: Booking, initiated_by: str) -> bool:
        """Public helper: check if a reschedule should activate LOCK."""
        return self._should_trigger_lock(booking, initiated_by)

    @BaseService.measure_operation("get_hours_until_start")
    def get_hours_until_start(self, booking: Booking) -> float:
        """Public helper: hours until booking start (UTC)."""
        booking_start_utc = self._get_booking_start_utc(booking)
        return float(TimezoneService.hours_until(booking_start_utc))

    def _should_trigger_lock(self, booking: Booking, initiated_by: str) -> bool:
        """Return True when LOCK should activate for a reschedule."""
        if initiated_by != "student":
            return False

        booking_start_utc = self._get_booking_start_utc(booking)
        hours_until_start = float(TimezoneService.hours_until(booking_start_utc))
        if not (12 <= hours_until_start < 24):
            return False

        pd = booking.payment_detail
        payment_status = (pd.payment_status if pd is not None else None) or ""
        payment_status = payment_status.lower()
        if payment_status == PaymentStatus.LOCKED.value:
            return False

        return payment_status in {
            PaymentStatus.AUTHORIZED.value,
            PaymentStatus.SCHEDULED.value,
        }

    @BaseService.measure_operation("activate_reschedule_lock")
    def activate_lock_for_reschedule(self, booking_id: str) -> Dict[str, Any]:
        """Capture + reverse transfer to activate LOCK for a reschedule."""
        from ..repositories.payment_repository import PaymentRepository
        from ..services.stripe_service import StripeService

        # Phase 1: Load booking and validate
        hours_until_lesson: Optional[float] = None
        needs_authorization = False
        with self.transaction():
            booking = self.repository.get_by_id_for_update(booking_id)
            if not booking:
                raise NotFoundException("Booking not found")

            pd = booking.payment_detail
            cur_ps = pd.payment_status if pd is not None else None
            if cur_ps == PaymentStatus.LOCKED.value:
                return {"locked": True, "already_locked": True}

            payment_status = (cur_ps or "").lower()
            if payment_status not in {
                PaymentStatus.AUTHORIZED.value,
                PaymentStatus.SCHEDULED.value,
            }:
                raise BusinessRuleException(f"Cannot lock booking with status {cur_ps}")

            if payment_status == PaymentStatus.SCHEDULED.value:
                booking_start_utc = self._get_booking_start_utc(booking)
                hours_until_lesson = float(TimezoneService.hours_until(booking_start_utc))
                needs_authorization = True

        if needs_authorization:
            from app.tasks.payment_tasks import _process_authorization_for_booking

            auth_result = _process_authorization_for_booking(booking_id, hours_until_lesson or 0.0)
            if not auth_result.get("success"):
                raise BusinessRuleException(
                    f"Unable to authorize payment for lock: {auth_result.get('error')}"
                )
            try:
                self.db.expire_all()
            except Exception:
                logger.warning(
                    "Failed to expire session state after authorizing booking %s for reschedule lock",
                    booking_id,
                    exc_info=True,
                )
        # Refresh booking after possible authorization
        booking = self.repository.get_booking_with_details(booking_id)
        if not booking:
            raise NotFoundException("Booking not found after authorization")

        pd = booking.payment_detail
        raw_pi = pd.payment_intent_id if pd is not None else None
        payment_intent_id = raw_pi if isinstance(raw_pi, str) and raw_pi.startswith("pi_") else None
        if not payment_intent_id:
            raise BusinessRuleException("No authorized payment available to lock")
        cur_ps = pd.payment_status if pd is not None else None
        if cur_ps != PaymentStatus.AUTHORIZED.value:
            raise BusinessRuleException(f"Cannot lock booking with status {cur_ps}")

        # Phase 2: Stripe calls (no transaction)
        stripe_service = StripeService(
            self.db,
            config_service=self.config_service,
            pricing_service=PricingService(self.db),
        )

        try:
            capture = stripe_service.capture_payment_intent(
                payment_intent_id,
                idempotency_key=f"lock_capture_{booking_id}",
            )
        except Exception as exc:
            logger.error("Lock capture failed for booking %s: %s", booking_id, exc)
            raise BusinessRuleException("Unable to lock payment at this time") from exc

        transfer_id = capture.get("transfer_id")
        transfer_amount = capture.get("transfer_amount")
        reverse_failed = False
        reversal_id: Optional[str] = None
        reversal_error: Optional[str] = None
        if transfer_id:
            try:
                reversal = stripe_service.reverse_transfer(
                    transfer_id=transfer_id,
                    amount_cents=transfer_amount,
                    idempotency_key=f"lock_reverse_{booking_id}",
                    reason="reschedule_lock",
                )
                reversal_obj = reversal.get("reversal") if isinstance(reversal, dict) else None
                reversal_id = getattr(reversal_obj, "id", None) if reversal_obj else None
            except Exception as exc:
                reverse_failed = True
                reversal_error = str(exc)
                logger.error("Lock reversal failed for booking %s: %s", booking_id, exc)

        # Phase 3: Persist lock state
        locked_amount = capture.get("amount_received")
        try:
            locked_amount = int(locked_amount) if locked_amount is not None else None
        except (TypeError, ValueError):
            locked_amount = None

        with self.transaction():
            booking = self.repository.get_by_id_for_update(booking_id)
            if not booking:
                raise NotFoundException("Booking not found after lock capture")

            payment_repo = PaymentRepository(self.db)
            from ..services.credit_service import CreditService

            credit_service = CreditService(self.db)
            bp = self.repository.ensure_payment(booking.id)
            if reverse_failed:
                bp.payment_status = PaymentStatus.MANUAL_REVIEW.value
                transfer_record = self._ensure_transfer_record(booking.id)
                transfer_record.stripe_transfer_id = transfer_id
                transfer_record.transfer_reversal_failed = True
                transfer_record.transfer_reversal_error = reversal_error
                transfer_record.transfer_reversal_failed_at = datetime.now(timezone.utc)
                transfer_record.transfer_reversal_retry_count = (
                    int(getattr(transfer_record, "transfer_reversal_retry_count", 0) or 0) + 1
                )
                payment_repo.create_payment_event(
                    booking_id=booking.id,
                    event_type="lock_activation_failed",
                    event_data={
                        "payment_intent_id": payment_intent_id,
                        "transfer_id": transfer_id,
                        "reason": "transfer_reversal_failed",
                    },
                )
            else:
                try:
                    credit_service.forfeit_credits_for_booking(
                        booking_id=booking.id, use_transaction=False
                    )
                except Exception as exc:
                    logger.warning(
                        "Failed to forfeit reserved credits for lock activation %s: %s",
                        booking.id,
                        exc,
                    )
                bp.credits_reserved_cents = 0
                bp.payment_status = PaymentStatus.LOCKED.value
                lock_record = self.repository.ensure_lock(booking.id)
                lock_record.locked_at = datetime.now(timezone.utc)
                lock_record.locked_amount_cents = locked_amount
                transfer_record = self._ensure_transfer_record(booking.id)
                transfer_record.stripe_transfer_id = transfer_id
                transfer_record.transfer_reversed = True if transfer_id else False
                transfer_record.transfer_reversal_id = reversal_id
                reschedule_record = self.repository.ensure_reschedule(booking.id)
                reschedule_record.late_reschedule_used = True
                payment_repo.create_payment_event(
                    booking_id=booking.id,
                    event_type="lock_activated",
                    event_data={
                        "payment_intent_id": payment_intent_id,
                        "transfer_id": transfer_id,
                        "locked_amount_cents": locked_amount,
                        "reason": "reschedule_in_12_24h_window",
                    },
                )

        if reverse_failed:
            raise BusinessRuleException("Unable to lock payment at this time")

        return {"locked": True, "locked_amount_cents": locked_amount}

    @BaseService.measure_operation("resolve_reschedule_lock")
    def resolve_lock_for_booking(self, locked_booking_id: str, resolution: str) -> Dict[str, Any]:
        """Resolve a LOCK based on the new lesson outcome.

        Uses a 3-phase flow to avoid holding booking row locks during Stripe API calls:
        1) Read/validate and collect context under SELECT ... FOR UPDATE
        2) Execute outbound Stripe calls with no DB transaction held
        3) Re-lock, re-validate state, and persist final lock resolution
        """
        from ..repositories.payment_repository import PaymentRepository
        from ..services.credit_service import CreditService

        stripe_service = StripeService(
            self.db,
            config_service=self.config_service,
            pricing_service=PricingService(self.db),
        )

        stripe_result: Dict[str, Any] = {
            "payout_success": False,
            "payout_transfer_id": None,
            "payout_amount_cents": None,
            "refund_success": False,
            "refund_data": None,
            "error": None,
        }

        resolution_ctx: Dict[str, Any]

        # ========== PHASE 1: Read/validate (quick transaction) ==========
        with self.transaction():
            locked_booking = self.repository.get_by_id_for_update(locked_booking_id)
            if not locked_booking:
                raise NotFoundException("Locked booking not found")

            lock_record = self.repository.get_lock_by_booking_id(locked_booking.id)
            if lock_record is not None and lock_record.lock_resolved_at is not None:
                return {"success": True, "skipped": True, "reason": "already_resolved"}

            locked_pd = locked_booking.payment_detail
            locked_ps = locked_pd.payment_status if locked_pd is not None else None
            if locked_ps == PaymentStatus.SETTLED.value:
                return {"success": True, "skipped": True, "reason": "already_settled"}
            if locked_ps != PaymentStatus.LOCKED.value:
                return {"success": False, "skipped": True, "reason": "not_locked"}

            payment_intent_id = locked_pd.payment_intent_id if locked_pd is not None else None
            locked_amount_cents = lock_record.locked_amount_cents if lock_record else None
            lesson_price_cents = int(
                float(locked_booking.hourly_rate) * locked_booking.duration_minutes * 100 / 60
            )

            payment_repo = PaymentRepository(self.db)

            instructor_stripe_account_id: Optional[str] = None
            try:
                instructor_profile = self.conflict_checker_repository.get_instructor_profile(
                    locked_booking.instructor_id
                )
                if instructor_profile:
                    connected_account = payment_repo.get_connected_account_by_instructor_id(
                        instructor_profile.id
                    )
                    if connected_account and connected_account.stripe_account_id:
                        instructor_stripe_account_id = connected_account.stripe_account_id
            except Exception as exc:
                logger.warning(
                    "Failed to load instructor Stripe account for booking %s: %s",
                    locked_booking.id,
                    exc,
                )

            payout_full_cents: Optional[int] = None
            try:
                payment_record = payment_repo.get_payment_by_booking_id(locked_booking.id)
                if payment_record:
                    payout_value = getattr(payment_record, "instructor_payout_cents", None)
                    if payout_value is not None:
                        payout_full_cents = int(payout_value)
            except Exception:
                payout_full_cents = None

            if payout_full_cents is None:
                pricing_service = PricingService(self.db)
                pricing = pricing_service.compute_booking_pricing(
                    booking_id=locked_booking.id, applied_credit_cents=0
                )
                payout_full_cents = int(pricing.get("target_instructor_payout_cents", 0))

            resolution_ctx = {
                "booking_id": locked_booking.id,
                "student_id": locked_booking.student_id,
                "payment_intent_id": payment_intent_id,
                "locked_amount_cents": locked_amount_cents,
                "lesson_price_cents": lesson_price_cents,
                "instructor_stripe_account_id": instructor_stripe_account_id,
                "payout_full_cents": int(payout_full_cents or 0),
            }

        # ========== PHASE 2: Stripe calls (NO transaction) ==========
        if resolution == "new_lesson_completed":
            try:
                instructor_account_id = resolution_ctx.get("instructor_stripe_account_id")
                if not instructor_account_id:
                    raise ServiceException("missing_instructor_account")
                payout_amount_cents = int(resolution_ctx.get("payout_full_cents") or 0)
                transfer_result = stripe_service.create_manual_transfer(
                    booking_id=locked_booking_id,
                    destination_account_id=instructor_account_id,
                    amount_cents=payout_amount_cents,
                    idempotency_key=f"lock_resolve_payout_{locked_booking_id}",
                    metadata={"resolution": resolution},
                )
                stripe_result["payout_success"] = True
                stripe_result["payout_transfer_id"] = transfer_result.get("transfer_id")
                stripe_result["payout_amount_cents"] = payout_amount_cents
            except Exception as exc:
                stripe_result["error"] = str(exc)

        elif resolution == "new_lesson_cancelled_lt12":
            try:
                instructor_account_id = resolution_ctx.get("instructor_stripe_account_id")
                if not instructor_account_id:
                    raise ServiceException("missing_instructor_account")
                payout_amount_cents = int(
                    round((resolution_ctx.get("payout_full_cents") or 0) * 0.5)
                )
                transfer_result = stripe_service.create_manual_transfer(
                    booking_id=locked_booking_id,
                    destination_account_id=instructor_account_id,
                    amount_cents=payout_amount_cents,
                    idempotency_key=f"lock_resolve_split_{locked_booking_id}",
                    metadata={"resolution": resolution},
                )
                stripe_result["payout_success"] = True
                stripe_result["payout_transfer_id"] = transfer_result.get("transfer_id")
                stripe_result["payout_amount_cents"] = payout_amount_cents
            except Exception as exc:
                stripe_result["error"] = str(exc)

        elif resolution == "instructor_cancelled":
            payment_intent_id = resolution_ctx.get("payment_intent_id")
            if payment_intent_id:
                try:
                    refund = stripe_service.refund_payment(
                        payment_intent_id,
                        reverse_transfer=True,
                        refund_application_fee=True,
                        idempotency_key=f"lock_resolve_refund_{locked_booking_id}",
                    )
                    stripe_result["refund_success"] = True
                    stripe_result["refund_data"] = refund
                except Exception as exc:
                    stripe_result["error"] = str(exc)
            else:
                stripe_result["error"] = "missing_payment_intent"

        # ========== PHASE 3: Re-lock/re-validate and persist ==========
        with self.transaction():
            locked_booking = self.repository.get_by_id_for_update(locked_booking_id)
            if not locked_booking:
                raise NotFoundException("Locked booking not found")

            lock_record = self.repository.get_lock_by_booking_id(locked_booking.id)
            if lock_record is not None and lock_record.lock_resolved_at is not None:
                logger.info(
                    "Skipping stale lock resolution for booking %s after external call: already resolved",
                    locked_booking.id,
                )
                return {"success": True, "skipped": True, "reason": "already_resolved"}

            locked_pd = locked_booking.payment_detail
            locked_ps = locked_pd.payment_status if locked_pd is not None else None
            if locked_ps == PaymentStatus.SETTLED.value:
                logger.info(
                    "Skipping stale lock resolution for booking %s after external call: already settled",
                    locked_booking.id,
                )
                return {"success": True, "skipped": True, "reason": "already_settled"}
            if locked_ps != PaymentStatus.LOCKED.value:
                logger.warning(
                    "Skipping stale lock resolution for booking %s after external call: payment status=%s",
                    locked_booking.id,
                    locked_ps,
                )
                return {"success": False, "skipped": True, "reason": "not_locked"}

            payment_repo = PaymentRepository(self.db)
            credit_service = CreditService(self.db)

            def _credit_already_issued() -> bool:
                try:
                    credits = payment_repo.get_credits_issued_for_source(locked_booking_id)
                except Exception as exc:
                    logger.warning(
                        "Failed to check existing credits for booking %s: %s",
                        locked_booking_id,
                        exc,
                    )
                    return False
                return any(
                    getattr(credit, "reason", None) in CANCELLATION_CREDIT_REASONS
                    or getattr(credit, "source_type", None) in CANCELLATION_CREDIT_REASONS
                    for credit in credits
                )

            def _locked_transfer() -> BookingTransfer:
                return self._ensure_transfer_record(locked_booking.id)

            lesson_price_cents = int(resolution_ctx.get("lesson_price_cents") or 0)
            locked_amount_cents = resolution_ctx.get("locked_amount_cents")

            locked_bp = self.repository.ensure_payment(locked_booking.id)
            if resolution == "new_lesson_completed":
                locked_bp.settlement_outcome = "lesson_completed_full_payout"
                locked_booking.student_credit_amount = 0
                locked_bp.instructor_payout_amount = stripe_result.get("payout_amount_cents")
                locked_booking.refunded_to_card_amount = 0
                locked_bp.credits_reserved_cents = 0
                if stripe_result.get("payout_success"):
                    locked_bp.payment_status = PaymentStatus.SETTLED.value
                    transfer_record = _locked_transfer()
                    transfer_record.payout_transfer_id = stripe_result.get("payout_transfer_id")
                else:
                    locked_bp.payment_status = PaymentStatus.MANUAL_REVIEW.value
                    transfer_record = _locked_transfer()
                    transfer_record.payout_transfer_failed_at = datetime.now(timezone.utc)
                    transfer_record.payout_transfer_error = stripe_result.get("error")
                    transfer_record.payout_transfer_retry_count = (
                        int(getattr(transfer_record, "payout_transfer_retry_count", 0) or 0) + 1
                    )
                    transfer_record.transfer_failed_at = transfer_record.payout_transfer_failed_at
                    transfer_record.transfer_error = transfer_record.payout_transfer_error
                    transfer_record.transfer_retry_count = (
                        int(getattr(transfer_record, "transfer_retry_count", 0) or 0) + 1
                    )

            elif resolution == "new_lesson_cancelled_ge12":
                credit_amount = lesson_price_cents
                if not _credit_already_issued():
                    credit_service.issue_credit(
                        user_id=locked_booking.student_id,
                        amount_cents=credit_amount,
                        source_type="locked_cancel_ge12",
                        reason="Locked cancellation >=12 hours (lesson price credit)",
                        source_booking_id=locked_booking_id,
                        use_transaction=False,
                    )
                locked_bp.settlement_outcome = "locked_cancel_ge12_full_credit"
                locked_booking.student_credit_amount = credit_amount
                locked_bp.instructor_payout_amount = 0
                locked_booking.refunded_to_card_amount = 0
                locked_bp.credits_reserved_cents = 0
                locked_bp.payment_status = PaymentStatus.SETTLED.value

            elif resolution == "new_lesson_cancelled_lt12":
                credit_amount = int(round(lesson_price_cents * 0.5))
                if not _credit_already_issued():
                    credit_service.issue_credit(
                        user_id=locked_booking.student_id,
                        amount_cents=credit_amount,
                        source_type="locked_cancel_lt12",
                        reason="Locked cancellation <12 hours (50% lesson price credit)",
                        source_booking_id=locked_booking_id,
                        use_transaction=False,
                    )
                locked_bp.settlement_outcome = "locked_cancel_lt12_split_50_50"
                locked_booking.student_credit_amount = credit_amount
                locked_bp.instructor_payout_amount = stripe_result.get("payout_amount_cents")
                locked_booking.refunded_to_card_amount = 0
                locked_bp.credits_reserved_cents = 0
                if stripe_result.get("payout_success"):
                    locked_bp.payment_status = PaymentStatus.SETTLED.value
                    transfer_record = _locked_transfer()
                    transfer_record.payout_transfer_id = stripe_result.get("payout_transfer_id")
                else:
                    locked_bp.payment_status = PaymentStatus.MANUAL_REVIEW.value
                    transfer_record = _locked_transfer()
                    transfer_record.payout_transfer_failed_at = datetime.now(timezone.utc)
                    transfer_record.payout_transfer_error = stripe_result.get("error")
                    transfer_record.payout_transfer_retry_count = (
                        int(getattr(transfer_record, "payout_transfer_retry_count", 0) or 0) + 1
                    )
                    transfer_record.transfer_failed_at = transfer_record.payout_transfer_failed_at
                    transfer_record.transfer_error = transfer_record.payout_transfer_error
                    transfer_record.transfer_retry_count = (
                        int(getattr(transfer_record, "transfer_retry_count", 0) or 0) + 1
                    )

            elif resolution == "instructor_cancelled":
                refund_data = stripe_result.get("refund_data") or {}
                refund_amount = refund_data.get("amount_refunded")
                if refund_amount is not None:
                    try:
                        refund_amount = int(refund_amount)
                    except (TypeError, ValueError):
                        refund_amount = None
                locked_bp.settlement_outcome = "instructor_cancel_full_refund"
                locked_booking.student_credit_amount = 0
                locked_bp.instructor_payout_amount = 0
                locked_booking.refunded_to_card_amount = (
                    refund_amount if refund_amount is not None else locked_amount_cents or 0
                )
                if stripe_result.get("refund_success"):
                    transfer_record = _locked_transfer()
                    transfer_record.refund_id = refund_data.get("refund_id")
                locked_bp.credits_reserved_cents = 0
                locked_bp.payment_status = (
                    PaymentStatus.SETTLED.value
                    if stripe_result.get("refund_success")
                    else PaymentStatus.MANUAL_REVIEW.value
                )
                if not stripe_result.get("refund_success"):
                    transfer_record = _locked_transfer()
                    transfer_record.refund_failed_at = datetime.now(timezone.utc)
                    transfer_record.refund_error = stripe_result.get("error")
                    transfer_record.refund_retry_count = (
                        int(getattr(transfer_record, "refund_retry_count", 0) or 0) + 1
                    )

            lock_record = self.repository.ensure_lock(locked_booking.id)
            lock_record.lock_resolution = resolution
            lock_record.lock_resolved_at = datetime.now(timezone.utc)

            payment_repo.create_payment_event(
                booking_id=locked_booking_id,
                event_type="lock_resolved",
                event_data={
                    "resolution": resolution,
                    "payout_amount_cents": locked_bp.instructor_payout_amount,
                    "student_credit_cents": locked_booking.student_credit_amount,
                    "refunded_cents": locked_booking.refunded_to_card_amount,
                    "error": stripe_result.get("error"),
                },
            )

            return {"success": True, "resolution": resolution}

    def _build_cancellation_context(self, booking: Booking, user: User) -> Dict[str, Any]:
        """
        Build context for cancellation (Phase 1 helper).
        Extracts all data needed for Stripe calls and finalization.
        """
        booking_start_utc = self._get_booking_start_utc(booking)
        hours_until = TimezoneService.hours_until(booking_start_utc)

        pd = booking.payment_detail
        raw_payment_intent_id = pd.payment_intent_id if pd is not None else None
        payment_intent_id = (
            raw_payment_intent_id
            if isinstance(raw_payment_intent_id, str) and raw_payment_intent_id.startswith("pi_")
            else None
        )

        # Part 4b: Fair Reschedule Loophole Fix
        was_gaming_reschedule = False
        hours_from_original: Optional[float] = None
        reschedule_record = self.repository.get_reschedule_by_booking_id(booking.id)
        original_lesson_datetime = (
            reschedule_record.original_lesson_datetime if reschedule_record else None
        )
        if booking.rescheduled_from_booking_id and original_lesson_datetime:
            original_dt = original_lesson_datetime
            if original_dt.tzinfo is None:
                original_dt = original_dt.replace(tzinfo=timezone.utc)
            reschedule_time = booking.created_at
            if reschedule_time is not None:
                if reschedule_time.tzinfo is None:
                    reschedule_time = reschedule_time.replace(tzinfo=timezone.utc)
                hours_from_original_value = (original_dt - reschedule_time).total_seconds() / 3600
                hours_from_original = hours_from_original_value
                was_gaming_reschedule = hours_from_original_value < 24

        cancelled_by_role = "student" if user.id == booking.student_id else "instructor"

        # Determine cancellation scenario
        cur_ps = pd.payment_status if pd is not None else None
        is_pending_payment = (
            booking.status == BookingStatus.PENDING
            or cur_ps == PaymentStatus.PAYMENT_METHOD_REQUIRED.value
        ) and payment_intent_id is None
        if is_pending_payment:
            scenario = "pending_payment"
        elif cancelled_by_role == "instructor":
            if hours_until >= 24:
                scenario = "instructor_cancel_over_24h"
            else:
                scenario = "instructor_cancel_under_24h"
        else:
            if hours_until >= 24:
                scenario = "over_24h_gaming" if was_gaming_reschedule else "over_24h_regular"
            elif 12 <= hours_until < 24:
                scenario = "between_12_24h"
            else:
                scenario = "under_12h" if payment_intent_id else "under_12h_no_pi"

            if scenario == "over_24h_gaming" and cur_ps != PaymentStatus.AUTHORIZED.value:
                raise BusinessRuleException(
                    "Gaming reschedule cancellations require an authorized payment"
                )

        # Calculate lesson price for credit scenarios
        lesson_price_cents = int(float(booking.hourly_rate) * booking.duration_minutes * 100 / 60)

        default_role = (
            RoleName.STUDENT.value if user.id == booking.student_id else RoleName.INSTRUCTOR.value
        )

        instructor_stripe_account_id: Optional[str] = None
        try:
            from ..repositories.payment_repository import PaymentRepository

            payment_repo = PaymentRepository(self.db)
            try:
                instructor_profile = self.conflict_checker_repository.get_instructor_profile(
                    booking.instructor_id
                )
                if instructor_profile:
                    connected_account = payment_repo.get_connected_account_by_instructor_id(
                        instructor_profile.id
                    )
                    if connected_account and connected_account.stripe_account_id:
                        instructor_stripe_account_id = connected_account.stripe_account_id
            except Exception as exc:
                logger.warning(
                    "Failed to load instructor Stripe account for booking %s: %s",
                    booking.id,
                    exc,
                )
        except Exception as exc:
            logger.warning(
                "Failed to load instructor Stripe account for booking %s: %s",
                booking.id,
                exc,
            )

        return {
            "booking_id": booking.id,
            "student_id": booking.student_id,
            "instructor_id": booking.instructor_id,
            "payment_intent_id": payment_intent_id,
            "payment_status": cur_ps,
            "scenario": scenario,
            "hours_until": hours_until,
            "hours_from_original": hours_from_original,
            "was_gaming_reschedule": was_gaming_reschedule,
            "lesson_price_cents": lesson_price_cents,
            "instructor_stripe_account_id": instructor_stripe_account_id,
            "rescheduled_from_booking_id": booking.rescheduled_from_booking_id,
            "original_lesson_datetime": original_lesson_datetime,
            "default_role": default_role,
            "cancelled_by_role": cancelled_by_role,
            "booking_date": booking.booking_date,
            "start_time": booking.start_time,
        }

    def _execute_cancellation_stripe_calls(
        self, ctx: Dict[str, Any], stripe_service: Any
    ) -> Dict[str, Any]:
        """
        Execute Stripe calls for cancellation (Phase 2).
        No transaction held during network calls.
        """
        results: Dict[str, Any] = {
            "cancel_pi_success": False,
            "capture_success": False,
            "reverse_success": False,
            "reverse_attempted": False,
            "reverse_failed": False,
            "reverse_reversal_id": None,
            "refund_success": False,
            "refund_failed": False,
            "refund_data": None,
            "payout_success": False,
            "payout_failed": False,
            "payout_transfer_id": None,
            "payout_amount_cents": None,
            "capture_data": None,
            "error": None,
        }

        scenario = ctx["scenario"]
        payment_intent_id = ctx["payment_intent_id"]
        booking_id = ctx["booking_id"]
        payment_status = (ctx.get("payment_status") or "").lower()
        already_captured = payment_status in {
            PaymentStatus.SETTLED.value,
            PaymentStatus.LOCKED.value,
        }

        if scenario == "over_24h_gaming":
            # Capture payment intent, then reverse transfer to retain fee and issue credit.
            if payment_intent_id:
                try:
                    if already_captured:
                        capture = stripe_service.get_payment_intent_capture_details(
                            payment_intent_id
                        )
                    else:
                        capture = stripe_service.capture_payment_intent(
                            payment_intent_id,
                            idempotency_key=f"capture_resched_{booking_id}",
                        )
                    results["capture_success"] = True
                    results["capture_data"] = {
                        "transfer_id": capture.get("transfer_id"),
                        "amount_received": capture.get("amount_received"),
                        "transfer_amount": capture.get("transfer_amount"),
                    }

                    transfer_id = capture.get("transfer_id")
                    transfer_amount = capture.get("transfer_amount")
                    if transfer_id and transfer_amount:
                        results["reverse_attempted"] = True
                        try:
                            reversal = stripe_service.reverse_transfer(
                                transfer_id=transfer_id,
                                amount_cents=transfer_amount,
                                idempotency_key=f"reverse_resched_{booking_id}",
                                reason="gaming_reschedule_cancel",
                            )
                            results["reverse_success"] = True
                            reversal_obj = (
                                reversal.get("reversal") if isinstance(reversal, dict) else None
                            )
                            results["reverse_reversal_id"] = (
                                reversal_obj.get("id")
                                if isinstance(reversal_obj, dict)
                                else getattr(reversal_obj, "id", None)
                            )
                        except Exception as e:
                            results["reverse_failed"] = True
                            logger.error(
                                "Transfer reversal failed for booking %s: %s", booking_id, e
                            )
                except Exception as e:
                    logger.warning("Capture not performed for booking %s: %s", booking_id, e)
                    results["error"] = str(e)

        elif scenario in ("over_24h_regular",):
            # Cancel payment intent (release authorization)
            if payment_intent_id:
                try:
                    stripe_service.cancel_payment_intent(
                        payment_intent_id, idempotency_key=f"cancel_{booking_id}"
                    )
                    results["cancel_pi_success"] = True
                except Exception as e:
                    logger.warning("Cancel PI failed for booking %s: %s", booking_id, e)
                    results["error"] = str(e)

        elif scenario in ("instructor_cancel_over_24h", "instructor_cancel_under_24h"):
            if payment_intent_id:
                if already_captured:
                    try:
                        refund = stripe_service.refund_payment(
                            payment_intent_id,
                            reverse_transfer=True,
                            refund_application_fee=True,
                            idempotency_key=f"refund_instructor_cancel_{booking_id}",
                        )
                        results["refund_success"] = True
                        results["refund_data"] = refund
                    except Exception as e:
                        logger.warning(
                            "Instructor refund failed for booking %s: %s",
                            booking_id,
                            e,
                        )
                        results["refund_failed"] = True
                        results["error"] = str(e)
                else:
                    try:
                        stripe_service.cancel_payment_intent(
                            payment_intent_id,
                            idempotency_key=f"cancel_instructor_{booking_id}",
                        )
                        results["cancel_pi_success"] = True
                    except Exception as e:
                        logger.warning("Cancel PI failed for booking %s: %s", booking_id, e)
                        results["error"] = str(e)

        elif scenario == "between_12_24h":
            # Capture payment intent, then reverse transfer
            if payment_intent_id:
                try:
                    if already_captured:
                        capture = stripe_service.get_payment_intent_capture_details(
                            payment_intent_id
                        )
                    else:
                        capture = stripe_service.capture_payment_intent(
                            payment_intent_id,
                            idempotency_key=f"capture_cancel_{booking_id}",
                        )
                    results["capture_success"] = True
                    results["capture_data"] = {
                        "transfer_id": capture.get("transfer_id"),
                        "amount_received": capture.get("amount_received"),
                        "transfer_amount": capture.get("transfer_amount"),
                    }

                    # Reverse transfer if available
                    transfer_id = capture.get("transfer_id")
                    transfer_amount = capture.get("transfer_amount")
                    if transfer_id and transfer_amount:
                        results["reverse_attempted"] = True
                        try:
                            reversal = stripe_service.reverse_transfer(
                                transfer_id=transfer_id,
                                amount_cents=transfer_amount,
                                idempotency_key=f"reverse_{booking_id}",
                                reason="student_cancel_12-24h",
                            )
                            results["reverse_success"] = True
                            reversal_obj = (
                                reversal.get("reversal") if isinstance(reversal, dict) else None
                            )
                            results["reverse_reversal_id"] = (
                                reversal_obj.get("id")
                                if isinstance(reversal_obj, dict)
                                else getattr(reversal_obj, "id", None)
                            )
                        except Exception as e:
                            results["reverse_failed"] = True
                            logger.error(
                                "Transfer reversal failed for booking %s: %s", booking_id, e
                            )
                except Exception as e:
                    logger.warning("Capture not performed for booking %s: %s", booking_id, e)
                    results["error"] = str(e)

        elif scenario == "under_12h":
            # Capture payment intent, reverse transfer, and create 50% payout transfer
            if payment_intent_id:
                try:
                    if already_captured:
                        capture = stripe_service.get_payment_intent_capture_details(
                            payment_intent_id
                        )
                    else:
                        capture = stripe_service.capture_payment_intent(
                            payment_intent_id,
                            idempotency_key=f"capture_late_cancel_{booking_id}",
                        )
                    results["capture_success"] = True
                    results["capture_data"] = {
                        "amount_received": capture.get("amount_received"),
                        "transfer_id": capture.get("transfer_id"),
                        "transfer_amount": capture.get("transfer_amount"),
                    }

                    transfer_id = capture.get("transfer_id")
                    transfer_amount = capture.get("transfer_amount")

                    if transfer_id:
                        results["reverse_attempted"] = True
                        try:
                            reversal = stripe_service.reverse_transfer(
                                transfer_id=transfer_id,
                                amount_cents=transfer_amount,
                                idempotency_key=f"reverse_lt12_{booking_id}",
                                reason="student_cancel_under_12h",
                            )
                            results["reverse_success"] = True
                            reversal_obj = (
                                reversal.get("reversal") if isinstance(reversal, dict) else None
                            )
                            results["reverse_reversal_id"] = (
                                reversal_obj.get("id")
                                if isinstance(reversal_obj, dict)
                                else getattr(reversal_obj, "id", None)
                            )
                        except Exception as e:
                            results["reverse_failed"] = True
                            logger.error(
                                "Transfer reversal failed for booking %s: %s", booking_id, e
                            )
                    else:
                        results["reverse_failed"] = True
                        logger.error(
                            "Missing transfer_id for under-12h cancellation booking %s",
                            booking_id,
                        )

                    if results["reverse_success"]:
                        payout_full_cents = transfer_amount
                        if payout_full_cents is None:
                            try:
                                payout_ctx = stripe_service.build_charge_context(
                                    booking_id=booking_id, requested_credit_cents=None
                                )
                                payout_full_cents = int(
                                    getattr(payout_ctx, "target_instructor_payout_cents", 0) or 0
                                )
                            except Exception as exc:
                                logger.warning(
                                    "Failed to resolve instructor payout for booking %s: %s",
                                    booking_id,
                                    exc,
                                )
                                payout_full_cents = None

                        if payout_full_cents is None:
                            results["payout_failed"] = True
                            results["error"] = "missing_payout_amount"
                        else:
                            payout_amount_cents = int(round(payout_full_cents * 0.5))
                            results["payout_amount_cents"] = payout_amount_cents
                            if payout_amount_cents <= 0:
                                results["payout_success"] = True
                            else:
                                destination_account_id = ctx.get("instructor_stripe_account_id")
                                if not destination_account_id:
                                    results["payout_failed"] = True
                                    results["error"] = "missing_instructor_account"
                                else:
                                    try:
                                        transfer_result = stripe_service.create_manual_transfer(
                                            booking_id=booking_id,
                                            destination_account_id=destination_account_id,
                                            amount_cents=payout_amount_cents,
                                            idempotency_key=f"payout_lt12_{booking_id}",
                                        )
                                        results["payout_success"] = True
                                        results["payout_transfer_id"] = transfer_result.get(
                                            "transfer_id"
                                        )
                                    except Exception as e:
                                        results["payout_failed"] = True
                                        results["error"] = str(e)
                except Exception as e:
                    logger.warning("Capture not performed for booking %s: %s", booking_id, e)
                    results["error"] = str(e)

        # scenario == "under_12h_no_pi" - no Stripe calls needed

        return results

    def _finalize_cancellation(
        self,
        booking: Booking,
        ctx: Dict[str, Any],
        stripe_results: Dict[str, Any],
        payment_repo: Any,
    ) -> None:
        """
        Finalize cancellation with Stripe results (Phase 3 helper).
        Creates payment events and updates booking status.
        """
        scenario = ctx["scenario"]
        booking_id = ctx["booking_id"]
        from ..services.credit_service import CreditService

        credit_service = CreditService(self.db)
        bp = self.repository.ensure_payment(booking.id)

        def _cancellation_credit_already_issued() -> bool:
            try:
                credits = payment_repo.get_credits_issued_for_source(booking_id)
            except Exception as exc:
                logger.warning(
                    "Failed to check existing credits for booking %s: %s",
                    booking_id,
                    exc,
                )
                return False
            return any(
                getattr(credit, "reason", None) in CANCELLATION_CREDIT_REASONS
                or getattr(credit, "source_type", None) in CANCELLATION_CREDIT_REASONS
                for credit in credits
            )

        def _apply_settlement(
            outcome: str,
            *,
            student_credit_cents: Optional[int] = None,
            instructor_payout_cents: Optional[int] = None,
            refunded_cents: Optional[int] = None,
        ) -> None:
            bp.settlement_outcome = outcome
            booking.student_credit_amount = student_credit_cents
            bp.instructor_payout_amount = instructor_payout_cents
            booking.refunded_to_card_amount = refunded_cents

        def _mark_capture_failed(error: Optional[str]) -> None:
            bp.payment_status = PaymentStatus.PAYMENT_METHOD_REQUIRED.value
            bp.capture_failed_at = datetime.now(timezone.utc)
            bp.capture_retry_count = int(bp.capture_retry_count or 0) + 1
            if error:
                bp.auth_last_error = error
                bp.capture_error = error

        def _mark_manual_review(reason: Optional[str]) -> None:
            bp.payment_status = PaymentStatus.MANUAL_REVIEW.value
            if reason:
                bp.auth_last_error = reason

        def _transfer_record() -> BookingTransfer:
            return self._ensure_transfer_record(booking_id)

        if scenario == "over_24h_gaming":
            if stripe_results["capture_success"]:
                capture_data = stripe_results.get("capture_data") or {}
                transfer_record = _transfer_record()
                transfer_record.stripe_transfer_id = capture_data.get("transfer_id")
                if stripe_results.get("reverse_failed"):
                    payment_repo.create_payment_event(
                        booking_id=booking_id,
                        event_type="transfer_reversal_failed",
                        event_data={
                            "payment_intent_id": ctx["payment_intent_id"],
                            "scenario": scenario,
                        },
                    )
                    transfer_record.transfer_reversal_failed = True
                    transfer_record.transfer_reversal_failed_at = datetime.now(timezone.utc)
                    transfer_record.transfer_reversal_retry_count = (
                        int(getattr(transfer_record, "transfer_reversal_retry_count", 0) or 0) + 1
                    )
                    transfer_record.transfer_reversal_error = stripe_results.get("error")
                    _mark_manual_review("transfer_reversal_failed")
                    logger.error(
                        "Transfer reversal failed for booking %s; manual review required",
                        booking_id,
                    )
                    return
                if stripe_results.get("reverse_reversal_id"):
                    transfer_record.transfer_reversal_id = stripe_results.get("reverse_reversal_id")
                credit_amount_cents = ctx["lesson_price_cents"]
                try:
                    credit_service.forfeit_credits_for_booking(
                        booking_id=booking_id, use_transaction=False
                    )
                except Exception as exc:
                    logger.warning(
                        "Failed to forfeit reserved credits for booking %s: %s",
                        booking_id,
                        exc,
                    )
                bp.credits_reserved_cents = 0
                if not _cancellation_credit_already_issued():
                    try:
                        credit_service.issue_credit(
                            user_id=ctx["student_id"],
                            amount_cents=credit_amount_cents,
                            source_type="cancel_credit_12_24",
                            reason="Rescheduled booking cancellation (lesson price credit)",
                            source_booking_id=booking_id,
                            use_transaction=False,
                        )
                    except Exception as e:
                        logger.error(
                            "Failed to create credit for gaming reschedule %s: %s", booking_id, e
                        )

                    payment_repo.create_payment_event(
                        booking_id=booking_id,
                        event_type="credit_created_gaming_reschedule_cancel",
                        event_data={
                            "hours_before_new": round(ctx["hours_until"], 2),
                            "hours_from_original": round(ctx["hours_from_original"], 2)
                            if ctx["hours_from_original"] is not None
                            else None,
                            "lesson_price_cents": ctx["lesson_price_cents"],
                            "credit_issued_cents": credit_amount_cents,
                            "rescheduled_from": ctx["rescheduled_from_booking_id"],
                            "original_lesson_datetime": ctx["original_lesson_datetime"].isoformat()
                            if ctx["original_lesson_datetime"]
                            else None,
                        },
                    )
                bp.payment_status = PaymentStatus.SETTLED.value
                _apply_settlement(
                    "student_cancel_12_24_full_credit",
                    student_credit_cents=credit_amount_cents,
                    instructor_payout_cents=0,
                    refunded_cents=0,
                )
            else:
                payment_repo.create_payment_event(
                    booking_id=booking_id,
                    event_type="capture_failed_gaming_reschedule_cancel",
                    event_data={
                        "payment_intent_id": ctx["payment_intent_id"],
                        "error": stripe_results.get("error"),
                    },
                )
                _mark_capture_failed(stripe_results.get("error"))

        elif scenario == "over_24h_regular":
            try:
                credit_service.release_credits_for_booking(
                    booking_id=booking_id, use_transaction=False
                )
            except Exception as exc:
                logger.warning(
                    "Failed to release reserved credits for booking %s: %s",
                    booking_id,
                    exc,
                )
            bp.credits_reserved_cents = 0
            payment_repo.create_payment_event(
                booking_id=booking_id,
                event_type="auth_released",
                event_data={
                    "hours_before": round(ctx["hours_until"], 2),
                    "payment_intent_id": ctx["payment_intent_id"],
                },
            )
            if ctx.get("payment_intent_id") and not stripe_results.get("cancel_pi_success"):
                _mark_manual_review(stripe_results.get("error"))
            else:
                bp.payment_status = PaymentStatus.SETTLED.value
            _apply_settlement(
                "student_cancel_gt24_no_charge",
                student_credit_cents=0,
                instructor_payout_cents=0,
                refunded_cents=0,
            )

        elif scenario == "between_12_24h":
            capture_data = stripe_results.get("capture_data") or {}
            transfer_record = _transfer_record()
            transfer_record.stripe_transfer_id = capture_data.get("transfer_id")

            if stripe_results["reverse_success"]:
                payment_repo.create_payment_event(
                    booking_id=booking_id,
                    event_type="transfer_reversed_late_cancel",
                    event_data={
                        "transfer_id": capture_data.get("transfer_id"),
                        "amount": capture_data.get("transfer_amount"),
                        "original_charge_amount": capture_data.get("amount_received"),
                    },
                )
                if stripe_results.get("reverse_reversal_id"):
                    transfer_record.transfer_reversal_id = stripe_results.get("reverse_reversal_id")

            if stripe_results["capture_success"]:
                if stripe_results.get("reverse_failed"):
                    payment_repo.create_payment_event(
                        booking_id=booking_id,
                        event_type="transfer_reversal_failed",
                        event_data={
                            "payment_intent_id": ctx["payment_intent_id"],
                            "scenario": scenario,
                        },
                    )
                    transfer_record.transfer_reversal_failed = True
                    transfer_record.transfer_reversal_failed_at = datetime.now(timezone.utc)
                    transfer_record.transfer_reversal_retry_count = (
                        int(getattr(transfer_record, "transfer_reversal_retry_count", 0) or 0) + 1
                    )
                    transfer_record.transfer_reversal_error = stripe_results.get("error")
                    _mark_manual_review("transfer_reversal_failed")
                    logger.error(
                        "Transfer reversal failed for booking %s; manual review required",
                        booking_id,
                    )
                    return
                credit_amount_cents = ctx["lesson_price_cents"]
                try:
                    credit_service.forfeit_credits_for_booking(
                        booking_id=booking_id, use_transaction=False
                    )
                except Exception as exc:
                    logger.warning(
                        "Failed to forfeit reserved credits for booking %s: %s",
                        booking_id,
                        exc,
                    )
                bp.credits_reserved_cents = 0
                if not _cancellation_credit_already_issued():
                    try:
                        credit_service.issue_credit(
                            user_id=ctx["student_id"],
                            amount_cents=credit_amount_cents,
                            source_type="cancel_credit_12_24",
                            reason="Cancellation 12-24 hours before lesson (lesson price credit)",
                            source_booking_id=booking_id,
                            use_transaction=False,
                        )
                    except Exception as e:
                        logger.error(
                            "Failed to create platform credit for booking %s: %s", booking_id, e
                        )

                    payment_repo.create_payment_event(
                        booking_id=booking_id,
                        event_type="credit_created_late_cancel",
                        event_data={
                            "amount": credit_amount_cents,
                            "lesson_price_cents": ctx["lesson_price_cents"],
                            "total_charged_cents": capture_data.get("amount_received"),
                        },
                    )
                bp.payment_status = PaymentStatus.SETTLED.value
                _apply_settlement(
                    "student_cancel_12_24_full_credit",
                    student_credit_cents=credit_amount_cents,
                    instructor_payout_cents=0,
                    refunded_cents=0,
                )
            else:
                payment_repo.create_payment_event(
                    booking_id=booking_id,
                    event_type="capture_failed_late_cancel",
                    event_data={
                        "payment_intent_id": ctx["payment_intent_id"],
                        "error": stripe_results.get("error"),
                    },
                )
                _mark_capture_failed(stripe_results.get("error"))

        elif scenario == "under_12h":
            if stripe_results["capture_success"]:
                capture_data = stripe_results.get("capture_data") or {}
                transfer_record = _transfer_record()
                transfer_record.stripe_transfer_id = capture_data.get("transfer_id")
                payment_repo.create_payment_event(
                    booking_id=booking_id,
                    event_type="captured_last_minute_cancel",
                    event_data={
                        "payment_intent_id": ctx["payment_intent_id"],
                        "amount": capture_data.get("amount_received"),
                    },
                )

                if stripe_results.get("reverse_failed"):
                    payment_repo.create_payment_event(
                        booking_id=booking_id,
                        event_type="transfer_reversal_failed",
                        event_data={
                            "payment_intent_id": ctx["payment_intent_id"],
                            "scenario": scenario,
                        },
                    )
                    transfer_record.transfer_reversal_failed = True
                    _mark_manual_review("transfer_reversal_failed")
                    logger.error(
                        "Transfer reversal failed for booking %s; manual review required",
                        booking_id,
                    )
                    return

                if stripe_results.get("reverse_success"):
                    payment_repo.create_payment_event(
                        booking_id=booking_id,
                        event_type="transfer_reversed_last_minute_cancel",
                        event_data={
                            "transfer_id": capture_data.get("transfer_id"),
                            "amount": capture_data.get("transfer_amount"),
                            "original_charge_amount": capture_data.get("amount_received"),
                        },
                    )
                    if stripe_results.get("reverse_reversal_id"):
                        transfer_record.transfer_reversal_id = stripe_results.get(
                            "reverse_reversal_id"
                        )

                if stripe_results.get("payout_failed"):
                    payment_repo.create_payment_event(
                        booking_id=booking_id,
                        event_type="payout_failed_last_minute_cancel",
                        event_data={
                            "payment_intent_id": ctx["payment_intent_id"],
                            "payout_amount_cents": stripe_results.get("payout_amount_cents"),
                            "error": stripe_results.get("error"),
                        },
                    )
                    transfer_record.payout_transfer_failed_at = datetime.now(timezone.utc)
                    transfer_record.payout_transfer_error = stripe_results.get("error")
                    transfer_record.payout_transfer_retry_count = (
                        int(getattr(transfer_record, "payout_transfer_retry_count", 0) or 0) + 1
                    )
                    transfer_record.transfer_failed_at = transfer_record.payout_transfer_failed_at
                    transfer_record.transfer_error = transfer_record.payout_transfer_error
                    transfer_record.transfer_retry_count = (
                        int(getattr(transfer_record, "transfer_retry_count", 0) or 0) + 1
                    )
                    _mark_manual_review(stripe_results.get("error"))

                if stripe_results.get("payout_success"):
                    payment_repo.create_payment_event(
                        booking_id=booking_id,
                        event_type="payout_created_last_minute_cancel",
                        event_data={
                            "transfer_id": stripe_results.get("payout_transfer_id"),
                            "payout_amount_cents": stripe_results.get("payout_amount_cents"),
                        },
                    )
                    transfer_record.payout_transfer_id = stripe_results.get("payout_transfer_id")

                credit_return_cents = int(round(ctx["lesson_price_cents"] * 0.5))
                try:
                    credit_service.forfeit_credits_for_booking(
                        booking_id=booking_id, use_transaction=False
                    )
                except Exception as exc:
                    logger.warning(
                        "Failed to forfeit reserved credits for booking %s: %s",
                        booking_id,
                        exc,
                    )
                bp.credits_reserved_cents = 0
                if not _cancellation_credit_already_issued():
                    try:
                        credit_service.issue_credit(
                            user_id=ctx["student_id"],
                            amount_cents=credit_return_cents,
                            source_type="cancel_credit_lt12",
                            reason="Cancellation <12 hours before lesson (50% lesson price credit)",
                            source_booking_id=booking_id,
                            use_transaction=False,
                        )
                    except Exception as e:
                        logger.error(
                            "Failed to create platform credit for booking %s: %s", booking_id, e
                        )

                    payment_repo.create_payment_event(
                        booking_id=booking_id,
                        event_type="credit_created_last_minute_cancel",
                        event_data={
                            "amount": credit_return_cents,
                            "lesson_price_cents": ctx["lesson_price_cents"],
                            "total_charged_cents": capture_data.get("amount_received"),
                            "payout_amount_cents": stripe_results.get("payout_amount_cents"),
                        },
                    )
                if bp.payment_status != PaymentStatus.MANUAL_REVIEW.value:
                    bp.payment_status = PaymentStatus.SETTLED.value
                payout_amount_cents = stripe_results.get("payout_amount_cents")
                if payout_amount_cents is not None:
                    try:
                        payout_amount_cents = int(payout_amount_cents)
                    except (TypeError, ValueError):
                        payout_amount_cents = None
                _apply_settlement(
                    "student_cancel_lt12_split_50_50",
                    student_credit_cents=credit_return_cents,
                    instructor_payout_cents=payout_amount_cents or 0,
                    refunded_cents=0,
                )
            else:
                payment_repo.create_payment_event(
                    booking_id=booking_id,
                    event_type="capture_failed_last_minute_cancel",
                    event_data={"payment_intent_id": ctx["payment_intent_id"]},
                )
                _mark_capture_failed(stripe_results.get("error"))

        elif scenario == "under_12h_no_pi":
            try:
                credit_service.release_credits_for_booking(
                    booking_id=booking_id, use_transaction=False
                )
            except Exception as exc:
                logger.warning(
                    "Failed to release reserved credits for booking %s: %s",
                    booking_id,
                    exc,
                )
            bp.credits_reserved_cents = 0
            payment_repo.create_payment_event(
                booking_id=booking_id,
                event_type="capture_skipped_no_intent",
                event_data={"reason": "<12h cancellation without payment_intent"},
            )
            _mark_manual_review("missing_payment_intent")

        elif scenario == "pending_payment":
            try:
                credit_service.release_credits_for_booking(
                    booking_id=booking_id, use_transaction=False
                )
            except Exception as exc:
                logger.warning(
                    "Failed to release reserved credits for booking %s: %s",
                    booking_id,
                    exc,
                )
            bp.credits_reserved_cents = 0
            payment_repo.create_payment_event(
                booking_id=booking_id,
                event_type="cancelled_before_payment",
                event_data={"reason": "pending_payment_method"},
            )
            bp.payment_status = PaymentStatus.SETTLED.value
            _apply_settlement(
                "student_cancel_gt24_no_charge",
                student_credit_cents=0,
                instructor_payout_cents=0,
                refunded_cents=0,
            )

        elif scenario in ("instructor_cancel_over_24h", "instructor_cancel_under_24h"):
            try:
                credit_service.release_credits_for_booking(
                    booking_id=booking_id, use_transaction=False
                )
            except Exception as exc:
                logger.warning(
                    "Failed to release reserved credits for booking %s: %s",
                    booking_id,
                    exc,
                )
            bp.credits_reserved_cents = 0
            if stripe_results.get("refund_success"):
                refund_data = stripe_results.get("refund_data") or {}
                payment_repo.create_payment_event(
                    booking_id=booking_id,
                    event_type="instructor_cancel_refunded",
                    event_data={
                        "hours_before": round(ctx["hours_until"], 2),
                        "payment_intent_id": ctx["payment_intent_id"],
                        "refund_id": refund_data.get("refund_id"),
                        "amount_refunded": refund_data.get("amount_refunded"),
                    },
                )
                bp.payment_status = PaymentStatus.SETTLED.value
                transfer_record = _transfer_record()
                transfer_record.refund_id = refund_data.get("refund_id")
                refund_amount = refund_data.get("amount_refunded")
                if refund_amount is not None:
                    try:
                        refund_amount = int(refund_amount)
                    except (TypeError, ValueError):
                        refund_amount = None
                _apply_settlement(
                    "instructor_cancel_full_refund",
                    student_credit_cents=0,
                    instructor_payout_cents=0,
                    refunded_cents=refund_amount or 0,
                )
            elif stripe_results.get("refund_failed"):
                transfer_record = _transfer_record()
                transfer_record.refund_failed_at = datetime.now(timezone.utc)
                transfer_record.refund_error = stripe_results.get("error")
                transfer_record.refund_retry_count = (
                    int(getattr(transfer_record, "refund_retry_count", 0) or 0) + 1
                )
                _mark_manual_review(stripe_results.get("error"))
            elif stripe_results.get("cancel_pi_success"):
                payment_repo.create_payment_event(
                    booking_id=booking_id,
                    event_type="instructor_cancelled",
                    event_data={
                        "hours_before": round(ctx["hours_until"], 2),
                        "payment_intent_id": ctx["payment_intent_id"],
                    },
                )
                bp.payment_status = PaymentStatus.SETTLED.value
                _apply_settlement(
                    "instructor_cancel_full_refund",
                    student_credit_cents=0,
                    instructor_payout_cents=0,
                    refunded_cents=0,
                )
            elif not ctx.get("payment_intent_id"):
                payment_repo.create_payment_event(
                    booking_id=booking_id,
                    event_type="instructor_cancelled",
                    event_data={
                        "hours_before": round(ctx["hours_until"], 2),
                        "reason": "no_payment_intent",
                    },
                )
                bp.payment_status = PaymentStatus.SETTLED.value
                _apply_settlement(
                    "instructor_cancel_full_refund",
                    student_credit_cents=0,
                    instructor_payout_cents=0,
                    refunded_cents=0,
                )
            else:
                payment_repo.create_payment_event(
                    booking_id=booking_id,
                    event_type="instructor_cancel_refund_failed",
                    event_data={
                        "hours_before": round(ctx["hours_until"], 2),
                        "payment_intent_id": ctx["payment_intent_id"],
                        "error": stripe_results.get("error"),
                    },
                )
                _mark_manual_review(stripe_results.get("error"))

    def _post_cancellation_actions(self, booking: Booking, cancelled_by_role: str) -> None:
        """
        Post-transaction actions for cancellation.
        Handles event publishing, notifications, and cache invalidation.
        """
        # Publish cancellation event
        try:
            self.event_publisher.publish(
                BookingCancelled(
                    booking_id=booking.id,
                    cancelled_by=cancelled_by_role,
                    cancelled_at=booking.cancelled_at or datetime.now(timezone.utc),
                    refund_amount=None,
                )
            )
        except Exception as e:
            logger.error("Failed to send cancellation notification event: %s", str(e))

        # Create system message in conversation
        try:
            self.system_message_service.create_booking_cancelled_message(
                student_id=booking.student_id,
                instructor_id=booking.instructor_id,
                booking_id=booking.id,
                booking_date=booking.booking_date,
                start_time=booking.start_time,
                cancelled_by=cancelled_by_role,
            )
        except Exception as e:
            logger.error(
                "Failed to create cancellation system message for booking %s: %s",
                booking.id,
                str(e),
            )

        self._send_cancellation_notifications(booking, cancelled_by_role)

        # Invalidate caches
        self._invalidate_booking_caches(booking)

        # Process refund hooks
        refund_hook_outcomes = {
            "student_cancel_gt24_no_charge",
            "instructor_cancel_full_refund",
            "instructor_no_show_full_refund",
            "student_wins_dispute_full_refund",
            "admin_refund",
        }
        pd = booking.payment_detail
        if (pd is not None and pd.payment_status == PaymentStatus.SETTLED.value) and (
            pd is not None and pd.settlement_outcome in refund_hook_outcomes
        ):
            try:
                credit_service = StudentCreditService(self.db)
                credit_service.process_refund_hooks(booking=booking)
            except Exception as exc:
                logger.error(
                    "Failed to adjust student credits for cancelled booking %s: %s",
                    booking.id,
                    exc,
                )

        self._disable_video_room_after_cancellation(booking)

    @BaseService.measure_operation("report_no_show")
    def report_no_show(
        self,
        *,
        booking_id: str,
        reporter: User,
        no_show_type: str,
        reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Report a no-show and freeze payment automation.

        Reporting window: lesson_start <= now <= lesson_end + 24h
        """
        from ..repositories.payment_repository import PaymentRepository

        now = datetime.now(timezone.utc)
        with self.transaction():
            booking = self.repository.get_booking_with_details(booking_id)
            if not booking:
                raise NotFoundException("Booking not found")

            is_admin = self._user_has_role(reporter, RoleName.ADMIN)
            is_student = reporter.id == booking.student_id
            is_instructor = reporter.id == booking.instructor_id

            if no_show_type == "instructor":
                if not (is_student or is_admin):
                    raise ForbiddenException(
                        "Only the student or admin can report an instructor no-show"
                    )
            elif no_show_type == "student":
                if not is_admin:
                    raise ForbiddenException("Only admin can report a student no-show")
            else:
                raise ValidationException("Invalid no_show_type")

            booking_start_utc = self._get_booking_start_utc(booking)
            booking_end_utc = self._get_booking_end_utc(booking)
            window_end = booking_end_utc + timedelta(hours=24)
            if not (booking_start_utc <= now <= window_end):
                raise BusinessRuleException(
                    "No-show can only be reported between lesson start and 24 hours after lesson end"
                )

            if booking.status == BookingStatus.CANCELLED:
                raise BusinessRuleException("Cannot report no-show for cancelled booking")

            no_show_record = self.repository.get_no_show_by_booking_id(booking.id)
            if no_show_record is not None and no_show_record.no_show_reported_at is not None:
                raise BusinessRuleException("No-show already reported for this booking")

            audit_before = self._snapshot_booking(booking)
            noshow_bp = self.repository.ensure_payment(booking.id)
            previous_payment_status = noshow_bp.payment_status

            noshow_bp.payment_status = PaymentStatus.MANUAL_REVIEW.value
            no_show_record = self.repository.ensure_no_show(booking.id)
            no_show_record.no_show_reported_by = reporter.id
            no_show_record.no_show_reported_at = now
            no_show_record.no_show_type = no_show_type
            no_show_record.no_show_disputed = False
            no_show_record.no_show_disputed_at = None
            no_show_record.no_show_dispute_reason = None
            no_show_record.no_show_resolved_at = None
            no_show_record.no_show_resolution = None

            payment_repo = PaymentRepository(self.db)
            payment_repo.create_payment_event(
                booking_id=booking.id,
                event_type="no_show_reported",
                event_data={
                    "type": no_show_type,
                    "reported_by": reporter.id,
                    "reason": reason,
                    "previous_payment_status": previous_payment_status,
                    "dispute_window_ends": (now + timedelta(hours=24)).isoformat(),
                },
            )

            audit_after = self._snapshot_booking(booking)
            default_role = (
                RoleName.STUDENT.value
                if is_student
                else (RoleName.INSTRUCTOR.value if is_instructor else RoleName.ADMIN.value)
            )
            self._write_booking_audit(
                booking,
                "no_show_reported",
                actor=reporter,
                before=audit_before,
                after=audit_after,
                default_role=default_role,
            )

        self._invalidate_booking_caches(booking)

        return {
            "success": True,
            "booking_id": booking_id,
            "no_show_type": no_show_type,
            "payment_status": PaymentStatus.MANUAL_REVIEW.value,
            "dispute_window_ends": (now + timedelta(hours=24)).isoformat(),
        }

    @BaseService.measure_operation("report_automated_no_show")
    def report_automated_no_show(
        self,
        *,
        booking_id: str,
        no_show_type: str,
        reason: str,
    ) -> Dict[str, Any]:
        """System-initiated no-show report from video attendance detection.

        No User reporter needed — actor=None with default_role="system".
        """
        from ..repositories.payment_repository import PaymentRepository

        now = datetime.now(timezone.utc)
        with self.transaction():
            booking = self.repository.get_booking_with_details(booking_id)
            if not booking:
                raise NotFoundException("Booking not found")

            if booking.status != BookingStatus.CONFIRMED.value:
                raise ValidationException(
                    f"Cannot report no-show for booking in status {booking.status}"
                )

            no_show_record = self.repository.get_no_show_by_booking_id(booking.id)
            if no_show_record is not None and no_show_record.no_show_reported_at is not None:
                raise BusinessRuleException("No-show already reported for this booking")

            audit_before = self._snapshot_booking(booking)
            noshow_bp = self.repository.ensure_payment(booking.id)
            previous_payment_status = noshow_bp.payment_status

            noshow_bp.payment_status = PaymentStatus.MANUAL_REVIEW.value
            no_show_record = self.repository.ensure_no_show(booking.id)
            no_show_record.no_show_reported_by = None
            no_show_record.no_show_reported_at = now
            no_show_record.no_show_type = no_show_type
            no_show_record.no_show_disputed = False
            no_show_record.no_show_disputed_at = None
            no_show_record.no_show_dispute_reason = None
            no_show_record.no_show_resolved_at = None
            no_show_record.no_show_resolution = None

            payment_repo = PaymentRepository(self.db)
            payment_repo.create_payment_event(
                booking_id=booking.id,
                event_type="no_show_reported",
                event_data={
                    "type": no_show_type,
                    "reported_by": None,
                    "reason": reason,
                    "automated": True,
                    "previous_payment_status": previous_payment_status,
                    "dispute_window_ends": (now + timedelta(hours=24)).isoformat(),
                },
            )

            audit_after = self._snapshot_booking(booking)
            self._write_booking_audit(
                booking,
                "no_show_reported_automated",
                actor=None,
                before=audit_before,
                after=audit_after,
                default_role="system",
            )

        self._invalidate_booking_caches(booking)

        return {
            "success": True,
            "booking_id": booking_id,
            "no_show_type": no_show_type,
            "payment_status": PaymentStatus.MANUAL_REVIEW.value,
            "dispute_window_ends": (now + timedelta(hours=24)).isoformat(),
        }

    @BaseService.measure_operation("dispute_no_show")
    def dispute_no_show(
        self,
        *,
        booking_id: str,
        disputer: User,
        reason: str,
    ) -> Dict[str, Any]:
        """Dispute a no-show report within the allowed window."""
        from ..repositories.payment_repository import PaymentRepository

        now = datetime.now(timezone.utc)
        with self.transaction():
            booking = self.repository.get_booking_with_details(booking_id)
            if not booking:
                raise NotFoundException("Booking not found")

            no_show_record = self.repository.get_no_show_by_booking_id(booking.id)
            if no_show_record is None or no_show_record.no_show_reported_at is None:
                raise BusinessRuleException("No no-show report exists for this booking")

            if no_show_record.no_show_disputed:
                raise BusinessRuleException("No-show already disputed")

            if no_show_record.no_show_resolved_at is not None:
                raise BusinessRuleException("No-show already resolved")

            if no_show_record.no_show_type == "instructor":
                if disputer.id != booking.instructor_id:
                    raise ForbiddenException("Only the accused instructor can dispute")
            elif no_show_record.no_show_type == "student":
                if disputer.id != booking.student_id:
                    raise ForbiddenException("Only the accused student can dispute")
            elif no_show_record.no_show_type == "mutual":
                if disputer.id not in {booking.student_id, booking.instructor_id}:
                    raise ForbiddenException("Only lesson participants can dispute")
            else:
                raise BusinessRuleException("Invalid no-show type")

            reported_at = no_show_record.no_show_reported_at
            if reported_at.tzinfo is None:
                reported_at = reported_at.replace(tzinfo=timezone.utc)
            dispute_deadline = reported_at + timedelta(hours=24)
            if now > dispute_deadline:
                raise BusinessRuleException(
                    f"Dispute window closed at {dispute_deadline.isoformat()}"
                )

            audit_before = self._snapshot_booking(booking)
            no_show_record.no_show_disputed = True
            no_show_record.no_show_disputed_at = now
            no_show_record.no_show_dispute_reason = reason

            payment_repo = PaymentRepository(self.db)
            payment_repo.create_payment_event(
                booking_id=booking.id,
                event_type="no_show_disputed",
                event_data={
                    "type": no_show_record.no_show_type,
                    "disputed_by": disputer.id,
                    "reason": reason,
                },
            )

            audit_after = self._snapshot_booking(booking)
            default_role = (
                RoleName.STUDENT.value
                if disputer.id == booking.student_id
                else RoleName.INSTRUCTOR.value
            )
            self._write_booking_audit(
                booking,
                "no_show_disputed",
                actor=disputer,
                before=audit_before,
                after=audit_after,
                default_role=default_role,
            )

        self._invalidate_booking_caches(booking)

        return {
            "success": True,
            "booking_id": booking_id,
            "disputed": True,
            "requires_platform_review": True,
        }

    @BaseService.measure_operation("resolve_no_show")
    def resolve_no_show(
        self,
        *,
        booking_id: str,
        resolution: str,
        resolved_by: Optional[User],
        admin_notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Resolve a no-show report and apply settlement.
        """
        from ..repositories.payment_repository import PaymentRepository
        from ..services.credit_service import CreditService
        from ..services.stripe_service import StripeService

        now = datetime.now(timezone.utc)
        with self.transaction():
            booking = self.repository.get_booking_with_details(booking_id)
            if not booking:
                raise NotFoundException("Booking not found")

            no_show_record = self.repository.get_no_show_by_booking_id(booking.id)
            if no_show_record is None or no_show_record.no_show_reported_at is None:
                raise BusinessRuleException("No no-show report exists")

            if no_show_record.no_show_resolved_at is not None:
                raise BusinessRuleException("No-show already resolved")

            no_show_type = no_show_record.no_show_type
            resolve_pd = booking.payment_detail
            payment_status = (resolve_pd.payment_status if resolve_pd is not None else None) or ""
            raw_resolve_pi = resolve_pd.payment_intent_id if resolve_pd is not None else None
            payment_intent_id = (
                raw_resolve_pi
                if isinstance(raw_resolve_pi, str) and raw_resolve_pi.startswith("pi_")
                else None
            )
            has_locked_funds = (
                getattr(booking, "has_locked_funds", False) is True
                and booking.rescheduled_from_booking_id is not None
            )
            locked_booking_id = booking.rescheduled_from_booking_id if has_locked_funds else None

            payment_repo = PaymentRepository(self.db)
            if payment_status == PaymentStatus.MANUAL_REVIEW.value:
                payment_record = payment_repo.get_payment_by_booking_id(booking.id)
                if payment_record and isinstance(payment_record.status, str):
                    payment_status = payment_record.status
            else:
                payment_record = payment_repo.get_payment_by_booking_id(booking.id)

            lesson_price_cents = int(
                float(booking.hourly_rate) * booking.duration_minutes * 100 / 60
            )
            instructor_payout_cents = None
            student_pay_cents = None
            if payment_record:
                if payment_record.amount is not None:
                    try:
                        student_pay_cents = int(payment_record.amount)
                    except (TypeError, ValueError):
                        student_pay_cents = None
                payout_value = getattr(payment_record, "instructor_payout_cents", None)
                if payout_value is not None:
                    try:
                        instructor_payout_cents = int(payout_value)
                    except (TypeError, ValueError):
                        instructor_payout_cents = None
                if instructor_payout_cents is None:
                    amount_value = getattr(payment_record, "amount", None)
                    fee_value = getattr(payment_record, "application_fee", None)
                    if amount_value is not None and fee_value is not None:
                        try:
                            instructor_payout_cents = max(0, int(amount_value) - int(fee_value))
                        except (TypeError, ValueError):
                            instructor_payout_cents = None
                if instructor_payout_cents is None:
                    base_price_value = getattr(payment_record, "base_price_cents", None)
                    tier_value = getattr(payment_record, "instructor_tier_pct", None)
                    if base_price_value is not None and tier_value is not None:
                        try:
                            instructor_payout_cents = int(
                                Decimal(base_price_value)
                                * (Decimal("1") - Decimal(str(tier_value)))
                            )
                        except (TypeError, ValueError, ArithmeticError):
                            instructor_payout_cents = None

            if instructor_payout_cents is None:
                try:
                    default_tier = max(
                        Decimal(str(tier["pct"]))
                        for tier in PRICING_DEFAULTS.get("instructor_tiers", [])
                        if "pct" in tier
                    )
                except (ValueError, TypeError):
                    default_tier = Decimal("0")
                instructor_payout_cents = int(
                    Decimal(lesson_price_cents) * (Decimal("1") - default_tier)
                )

            if student_pay_cents is None:
                try:
                    student_fee_pct = Decimal(str(PRICING_DEFAULTS.get("student_fee_pct", 0)))
                except (TypeError, ValueError):
                    student_fee_pct = Decimal("0")
                student_fee_cents = int(
                    (Decimal(lesson_price_cents) * student_fee_pct).quantize(
                        Decimal("1"), rounding=ROUND_HALF_UP
                    )
                )
                student_pay_cents = lesson_price_cents + student_fee_cents

            audit_before = self._snapshot_booking(booking)

        stripe_result: Dict[str, Any] = {}

        if resolution in {"confirmed_no_dispute", "confirmed_after_review"}:
            if no_show_type == "instructor":
                if locked_booking_id:
                    stripe_result = self.resolve_lock_for_booking(
                        locked_booking_id, "instructor_cancelled"
                    )
                else:
                    stripe_service = StripeService(
                        self.db,
                        config_service=self.config_service,
                        pricing_service=PricingService(self.db),
                    )
                    stripe_result = self._refund_for_instructor_no_show(
                        stripe_service=stripe_service,
                        booking_id=booking_id,
                        payment_intent_id=payment_intent_id,
                        payment_status=payment_status,
                    )
            elif no_show_type == "mutual":
                if locked_booking_id:
                    stripe_result = self.resolve_lock_for_booking(
                        locked_booking_id, "instructor_cancelled"
                    )
                else:
                    stripe_service = StripeService(
                        self.db,
                        config_service=self.config_service,
                        pricing_service=PricingService(self.db),
                    )
                    stripe_result = self._refund_for_instructor_no_show(
                        stripe_service=stripe_service,
                        booking_id=booking_id,
                        payment_intent_id=payment_intent_id,
                        payment_status=payment_status,
                    )
            elif no_show_type == "student":
                if locked_booking_id:
                    stripe_result = self.resolve_lock_for_booking(
                        locked_booking_id, "new_lesson_completed"
                    )
                else:
                    stripe_service = StripeService(
                        self.db,
                        config_service=self.config_service,
                        pricing_service=PricingService(self.db),
                    )
                    stripe_result = self._payout_for_student_no_show(
                        stripe_service=stripe_service,
                        booking_id=booking_id,
                        payment_intent_id=payment_intent_id,
                        payment_status=payment_status,
                    )
            else:
                raise BusinessRuleException("Invalid no-show type")

        elif resolution == "dispute_upheld":
            if locked_booking_id:
                stripe_result = self.resolve_lock_for_booking(
                    locked_booking_id, "new_lesson_completed"
                )
            else:
                stripe_service = StripeService(
                    self.db,
                    config_service=self.config_service,
                    pricing_service=PricingService(self.db),
                )
                stripe_result = self._payout_for_student_no_show(
                    stripe_service=stripe_service,
                    booking_id=booking_id,
                    payment_intent_id=payment_intent_id,
                    payment_status=payment_status,
                )

        elif resolution == "cancelled":
            stripe_result = {"skipped": True}
        else:
            raise ValidationException("Invalid no-show resolution")

        with self.transaction():
            booking = self.repository.get_booking_with_details(booking_id)
            if not booking:
                raise NotFoundException("Booking not found after resolution")

            payment_repo = PaymentRepository(self.db)
            credit_service = CreditService(self.db)

            no_show_record = self.repository.ensure_no_show(booking.id)
            no_show_record.no_show_resolved_at = now
            no_show_record.no_show_resolution = resolution

            if resolution in {"confirmed_no_dispute", "confirmed_after_review"}:
                booking.status = BookingStatus.NO_SHOW
                if no_show_type in {"instructor", "mutual"}:
                    self._finalize_instructor_no_show(
                        booking=booking,
                        stripe_result=stripe_result,
                        credit_service=credit_service,
                        refunded_cents=student_pay_cents,
                        locked_booking_id=locked_booking_id,
                    )
                    if no_show_type == "mutual":
                        mutual_bp = self.repository.ensure_payment(booking.id)
                        mutual_bp.settlement_outcome = "mutual_no_show_full_refund"
                else:
                    self._finalize_student_no_show(
                        booking=booking,
                        stripe_result=stripe_result,
                        credit_service=credit_service,
                        payout_cents=instructor_payout_cents,
                        locked_booking_id=locked_booking_id,
                    )

            elif resolution == "dispute_upheld":
                booking.status = BookingStatus.COMPLETED
                self._finalize_student_no_show(
                    booking=booking,
                    stripe_result=stripe_result,
                    credit_service=credit_service,
                    payout_cents=instructor_payout_cents,
                    locked_booking_id=locked_booking_id,
                )
                upheld_bp = self.repository.ensure_payment(booking.id)
                upheld_bp.settlement_outcome = "lesson_completed_full_payout"
                upheld_bp.payment_status = PaymentStatus.SETTLED.value

            elif resolution == "cancelled":
                self._cancel_no_show_report(booking)

            payment_repo.create_payment_event(
                booking_id=booking.id,
                event_type="no_show_resolved",
                event_data={
                    "resolution": resolution,
                    "resolved_by": resolved_by.id if resolved_by else "system",
                    "admin_notes": admin_notes,
                },
            )

            audit_after = self._snapshot_booking(booking)
            default_role = (
                RoleName.ADMIN.value
                if resolved_by and self._user_has_role(resolved_by, RoleName.ADMIN)
                else "system"
            )
            self._write_booking_audit(
                booking,
                "no_show_resolved",
                actor=resolved_by,
                before=audit_before,
                after=audit_after,
                default_role=default_role,
            )

        self._invalidate_booking_caches(booking)

        return {
            "success": True,
            "booking_id": booking_id,
            "resolution": resolution,
            "settlement_outcome": getattr(booking.payment_detail, "settlement_outcome", None),
        }

    def _refund_for_instructor_no_show(
        self,
        *,
        stripe_service: Any,
        booking_id: str,
        payment_intent_id: Optional[str],
        payment_status: str,
    ) -> Dict[str, Any]:
        """Refund full amount for instructor no-show or release authorization."""
        result: Dict[str, Any] = {"refund_success": False, "cancel_success": False, "error": None}
        already_captured = payment_status in {
            PaymentStatus.SETTLED.value,
            PaymentStatus.LOCKED.value,
        }
        if not payment_intent_id:
            result["error"] = "missing_payment_intent"
            return result

        if already_captured:
            try:
                refund = stripe_service.refund_payment(
                    payment_intent_id,
                    reverse_transfer=True,
                    refund_application_fee=True,
                    idempotency_key=f"refund_instructor_noshow_{booking_id}",
                )
                result["refund_success"] = True
                result["refund_data"] = refund
            except Exception as exc:
                result["error"] = str(exc)
        else:
            try:
                stripe_service.cancel_payment_intent(
                    payment_intent_id,
                    idempotency_key=f"cancel_instructor_noshow_{booking_id}",
                )
                result["cancel_success"] = True
            except Exception as exc:
                result["error"] = str(exc)

        return result

    def _payout_for_student_no_show(
        self,
        *,
        stripe_service: Any,
        booking_id: str,
        payment_intent_id: Optional[str],
        payment_status: str,
    ) -> Dict[str, Any]:
        """Capture payment if needed for student no-show."""
        result: Dict[str, Any] = {
            "capture_success": False,
            "already_captured": False,
            "error": None,
        }
        already_captured = payment_status in {
            PaymentStatus.SETTLED.value,
            PaymentStatus.LOCKED.value,
        }
        if already_captured:
            result["already_captured"] = True
            return result
        if not payment_intent_id:
            result["error"] = "missing_payment_intent"
            return result

        try:
            capture = stripe_service.capture_payment_intent(
                payment_intent_id,
                idempotency_key=f"capture_student_noshow_{booking_id}",
            )
            result["capture_success"] = True
            result["capture_data"] = capture
        except Exception as exc:
            result["error"] = str(exc)

        return result

    def _finalize_instructor_no_show(
        self,
        *,
        booking: Booking,
        stripe_result: Dict[str, Any],
        credit_service: Any,
        refunded_cents: int,
        locked_booking_id: Optional[str],
    ) -> None:
        """Persist instructor no-show settlement."""
        credit_service.release_credits_for_booking(booking_id=booking.id, use_transaction=False)
        bp = self.repository.ensure_payment(booking.id)
        bp.settlement_outcome = "instructor_no_show_full_refund"
        booking.student_credit_amount = 0
        bp.instructor_payout_amount = 0

        if locked_booking_id:
            booking.refunded_to_card_amount = 0
            bp.payment_status = (
                PaymentStatus.SETTLED.value
                if stripe_result.get("skipped") or stripe_result.get("success")
                else PaymentStatus.MANUAL_REVIEW.value
            )
            return

        refund_data = stripe_result.get("refund_data") or {}
        refund_amount = refund_data.get("amount_refunded")
        if refund_amount is not None:
            try:
                refund_amount = int(refund_amount)
            except (TypeError, ValueError):
                refund_amount = None
        booking.refunded_to_card_amount = (
            refund_amount if refund_amount is not None else refunded_cents
        )

        if stripe_result.get("refund_success") or stripe_result.get("cancel_success"):
            if stripe_result.get("refund_success"):
                transfer_record = self._ensure_transfer_record(booking.id)
                transfer_record.refund_id = refund_data.get("refund_id")
            bp.payment_status = PaymentStatus.SETTLED.value
        else:
            transfer_record = self._ensure_transfer_record(booking.id)
            transfer_record.refund_failed_at = datetime.now(timezone.utc)
            transfer_record.refund_error = stripe_result.get("error")
            transfer_record.refund_retry_count = (
                int(getattr(transfer_record, "refund_retry_count", 0) or 0) + 1
            )
            bp.payment_status = PaymentStatus.MANUAL_REVIEW.value

    def _finalize_student_no_show(
        self,
        *,
        booking: Booking,
        stripe_result: Dict[str, Any],
        credit_service: Any,
        payout_cents: int,
        locked_booking_id: Optional[str],
    ) -> None:
        """Persist student no-show settlement."""
        credit_service.forfeit_credits_for_booking(booking_id=booking.id, use_transaction=False)
        bp = self.repository.ensure_payment(booking.id)
        bp.settlement_outcome = "student_no_show_full_payout"
        booking.student_credit_amount = 0
        booking.refunded_to_card_amount = 0

        if locked_booking_id:
            bp.instructor_payout_amount = 0
            bp.payment_status = (
                PaymentStatus.SETTLED.value
                if stripe_result.get("skipped") or stripe_result.get("success")
                else PaymentStatus.MANUAL_REVIEW.value
            )
            return

        bp.instructor_payout_amount = payout_cents
        if stripe_result.get("capture_success") or stripe_result.get("already_captured"):
            capture_data = stripe_result.get("capture_data") or {}
            if capture_data.get("transfer_id"):
                transfer_record = self._ensure_transfer_record(booking.id)
                transfer_record.stripe_transfer_id = capture_data.get("transfer_id")
            bp.payment_status = PaymentStatus.SETTLED.value
        else:
            bp.payment_status = PaymentStatus.PAYMENT_METHOD_REQUIRED.value
            bp.capture_failed_at = datetime.now(timezone.utc)
            bp.capture_retry_count = int(bp.capture_retry_count or 0) + 1
            bp.capture_error = stripe_result.get("error")

    def _cancel_no_show_report(self, booking: Booking) -> None:
        """Cancel a no-show report and restore payment status."""
        from ..repositories.payment_repository import PaymentRepository

        payment_repo = PaymentRepository(self.db)
        bp = self.repository.ensure_payment(booking.id)
        payment_record = payment_repo.get_payment_by_booking_id(booking.id)
        if payment_record and isinstance(payment_record.status, str):
            status = payment_record.status
            if status == "succeeded":
                bp.payment_status = PaymentStatus.SETTLED.value
            elif status in {"requires_capture", "authorized"}:
                bp.payment_status = PaymentStatus.AUTHORIZED.value
            else:
                bp.payment_status = PaymentStatus.PAYMENT_METHOD_REQUIRED.value
        else:
            bp.payment_status = PaymentStatus.AUTHORIZED.value if bp.payment_intent_id else None

        bp.settlement_outcome = None
        booking.student_credit_amount = None
        bp.instructor_payout_amount = None
        booking.refunded_to_card_amount = None

    @BaseService.measure_operation("mark_no_show")
    def mark_no_show(self, booking_id: str, instructor: User) -> Booking:
        """
        Mark a booking as no-show (instructor only).

        A no-show indicates the student did not attend the scheduled lesson.

        Args:
            booking_id: ID of booking to mark as no-show
            instructor: Instructor marking as no-show

        Returns:
            Booking marked as no-show

        Raises:
            NotFoundException: If booking not found
            ValidationException: If user is not instructor
            BusinessRuleException: If booking cannot be marked as no-show
        """
        instructor_roles = cast(list[Any], getattr(instructor, "roles", []) or [])
        is_instructor = any(
            cast(str, getattr(role, "name", "")) == RoleName.INSTRUCTOR for role in instructor_roles
        )
        if not is_instructor:
            raise ValidationException("Only instructors can mark bookings as no-show")

        with self.transaction():
            # Load and validate booking
            booking = self.repository.get_booking_with_details(booking_id)

            if not booking:
                raise NotFoundException("Booking not found")

            if booking.instructor_id != instructor.id:
                raise ValidationException("You can only mark your own bookings as no-show")

            if booking.status != BookingStatus.CONFIRMED:
                raise BusinessRuleException(
                    f"Only confirmed bookings can be marked as no-show - current status: {booking.status}"
                )

            audit_before = self._snapshot_booking(booking)

            # Mark as no-show using model method
            booking.mark_no_show()

            # Flush to persist status change
            self.repository.flush()

            self._enqueue_booking_outbox_event(booking, "booking.no_show")
            audit_after = self._snapshot_booking(booking)
            self._write_booking_audit(
                booking,
                "no_show",
                actor=instructor,
                before=audit_before,
                after=audit_after,
                default_role=RoleName.INSTRUCTOR.value,
            )

        # External operations outside transaction
        # Reload booking with details for cache invalidation
        refreshed_booking = self.repository.get_booking_with_details(booking_id)
        if refreshed_booking is None:
            raise NotFoundException("Booking not found")
        self._invalidate_booking_caches(refreshed_booking)

        return refreshed_booking

    # Private helper methods for create_booking refactoring

    def _validate_booking_prerequisites(
        self, student: User, booking_data: BookingCreate
    ) -> Tuple[InstructorService, InstructorProfile]:
        """
        Validate student role and load required data.

        Args:
            student: The student creating the booking
            booking_data: Booking creation data

        Returns:
            Tuple of (service, instructor_profile)

        Raises:
            ValidationException: If validation fails
            NotFoundException: If resources not found
        """
        # Validate student role
        if not any(role.name == RoleName.STUDENT for role in student.roles):
            raise ValidationException("Only students can create bookings")
        if getattr(student, "account_locked", False):
            raise BusinessRuleException(
                "Your account is locked due to payment issues. Please contact support."
            )
        if getattr(student, "account_restricted", False):
            raise BusinessRuleException(
                "Your account is restricted due to a payment dispute. Please contact support."
            )
        if getattr(student, "credit_balance_frozen", False) or (
            int(getattr(student, "credit_balance_cents", 0) or 0) < 0
        ):
            raise BusinessRuleException(
                "Your account has a negative credit balance. Please contact support."
            )

        # Use repositories instead of direct queries
        service = self.conflict_checker_repository.get_active_service(
            booking_data.instructor_service_id
        )
        if not service:
            raise NotFoundException("Service not found or no longer available")

        # Get instructor profile
        instructor_profile = self.conflict_checker_repository.get_instructor_profile(
            booking_data.instructor_id
        )
        if not instructor_profile:
            raise NotFoundException("Instructor profile not found")

        # Verify service belongs to instructor
        if service.instructor_profile_id != instructor_profile.id:
            raise ValidationException("Service does not belong to this instructor")

        # Check instructor account status - only active instructors can receive bookings
        # Use repository to get user data
        user_repository = RepositoryFactory.create_base_repository(self.db, User)
        instructor_user = user_repository.get_by_id(booking_data.instructor_id)
        if instructor_user and instructor_user.account_status != "active":
            if instructor_user.account_status == "suspended":
                raise BusinessRuleException(
                    "This instructor is temporarily suspended and cannot receive new bookings"
                )
            elif instructor_user.account_status == "deactivated":
                raise BusinessRuleException(
                    "This instructor account has been deactivated and cannot receive bookings"
                )
            else:
                raise BusinessRuleException("This instructor cannot receive bookings at this time")

        if must_be_verified_for_public() and not is_verified(
            getattr(instructor_profile, "bgc_status", None)
        ):
            raise BusinessRuleException(
                "This instructor is pending verification and cannot be booked at this time"
            )

        return service, instructor_profile

    def _create_booking_record(
        self,
        student: User,
        booking_data: BookingCreate,
        service: InstructorService,
        instructor_profile: InstructorProfile,
        selected_duration: int,
    ) -> Booking:
        """
        Create the booking record with pricing calculation.

        Args:
            student: Student creating the booking
            booking_data: Booking data
            service: Service being booked
            instructor_profile: Instructor's profile
            selected_duration: Selected duration in minutes

        Returns:
            Created booking instance
        """
        if booking_data.end_time is None:
            raise ValidationException("End time must be calculated before creating a booking")
        end_time_value = booking_data.end_time

        instructor_tz = self._resolve_instructor_timezone(instructor_profile)
        student_tz = self._resolve_student_timezone(student)
        lesson_tz = TimezoneService.get_lesson_timezone(
            instructor_tz, self._is_online_lesson(booking_data)
        )
        booking_start_utc, booking_end_utc = self._resolve_booking_times_utc(
            booking_data.booking_date,
            booking_data.start_time,
            end_time_value,
            lesson_tz,
        )

        # Calculate pricing based on selected duration and requested booking format
        total_price = service.price_for_booking(selected_duration, booking_data.location_type)
        hourly_rate = service.hourly_rate_for_location_type(booking_data.location_type)

        # Derive service area summary for booking record
        service_area_summary = self._determine_service_area_summary(instructor_profile.user_id)

        # Create the booking
        booking = self.repository.create(
            student_id=student.id,
            instructor_id=booking_data.instructor_id,
            instructor_service_id=service.id,
            booking_date=booking_data.booking_date,
            start_time=booking_data.start_time,
            end_time=end_time_value,
            booking_start_utc=booking_start_utc,
            booking_end_utc=booking_end_utc,
            lesson_timezone=lesson_tz,
            instructor_tz_at_booking=instructor_tz,
            student_tz_at_booking=student_tz,
            service_name=service.catalog_entry.name if service.catalog_entry else "Unknown Service",
            hourly_rate=hourly_rate,
            total_price=total_price,
            duration_minutes=selected_duration,
            status=BookingStatus.CONFIRMED,
            service_area=service_area_summary,
            meeting_location=booking_data.location_address or booking_data.meeting_location,
            location_type=booking_data.location_type,
            location_address=booking_data.location_address,
            location_lat=booking_data.location_lat,
            location_lng=booking_data.location_lng,
            location_place_id=booking_data.location_place_id,
            student_note=booking_data.student_note,
        )

        # Load relationships for response
        detailed_booking = self.repository.get_booking_with_details(booking.id)

        pricing_service = PricingService(self.db)
        pricing_service.compute_booking_pricing(booking.id, applied_credit_cents=0)

        if detailed_booking is not None:
            return detailed_booking

        return booking

    def _determine_service_area_summary(self, instructor_id: str) -> str:
        """Summarize instructor service areas for booking metadata."""
        areas = self.service_area_repository.list_for_instructor(instructor_id)
        boroughs: set[str] = set()

        for area in areas:
            region = getattr(area, "neighborhood", None)
            borough = getattr(region, "parent_region", None)
            region_meta = getattr(region, "region_metadata", None)
            if isinstance(region_meta, dict):
                meta_borough = region_meta.get("borough")
                if isinstance(meta_borough, str) and meta_borough:
                    borough = meta_borough
            if isinstance(borough, str) and borough:
                boroughs.add(borough)

        sorted_boroughs = sorted(boroughs)
        if not sorted_boroughs:
            return ""
        if len(sorted_boroughs) <= 2:
            return ", ".join(sorted_boroughs)
        return f"{sorted_boroughs[0]} + {len(sorted_boroughs) - 1} more"

    def _calculate_pricing(
        self,
        service: InstructorService,
        start_time: time,
        end_time: time,
        location_type: str = "online",
    ) -> Dict[str, Any]:
        """Calculate booking pricing based on time range."""
        # Calculate duration
        # Use a reference date for duration calculations
        # This is just for calculating the duration, not timezone-specific
        reference_date = date(2024, 1, 1)
        start = datetime.combine(  # tz-pattern-ok: duration math only
            reference_date, start_time, tzinfo=timezone.utc
        )
        end = datetime.combine(  # tz-pattern-ok: duration math only
            reference_date, end_time, tzinfo=timezone.utc
        )
        duration = end - start
        duration_minutes = int(duration.total_seconds() / 60)

        # Calculate price based on actual booking duration
        resolved_rate = service.hourly_rate_for_location_type(location_type)
        total_price = float(service.price_for_booking(duration_minutes, location_type))

        return {
            "duration_minutes": duration_minutes,
            "total_price": total_price,
            "hourly_rate": resolved_rate,
        }

    # =========================================================================
    # Methods for route layer (no direct DB/repo access needed in routes)
    # =========================================================================

    @BaseService.measure_operation("validate_reschedule_allowed")
    def validate_reschedule_allowed(self, booking: "Booking") -> None:
        """
        Validate that a booking can be rescheduled (v2.1.1 rules).

        Rules:
        - Reschedule blocked when <12h before lesson
        - Exactly one late reschedule allowed in 12-24h window (late_reschedule_used)
        - Unlimited reschedules when >=24h
        - Locked bookings cannot be rescheduled

        Args:
            booking: The booking to validate

        Raises:
            BusinessRuleException: If booking has already been rescheduled once
        """
        if getattr(booking.payment_detail, "payment_status", None) == PaymentStatus.LOCKED.value:
            raise BusinessRuleException(
                message="This booking has locked funds and cannot be rescheduled.",
                code="reschedule_locked",
            )

        hours_until_start = self.get_hours_until_start(booking)
        if hours_until_start < 12:
            raise BusinessRuleException(
                message=(
                    "Cannot reschedule within 12 hours of lesson start. "
                    "Please cancel if you cannot attend."
                ),
                code="reschedule_window_closed",
            )

        reschedule_record = self.repository.get_reschedule_by_booking_id(booking.id)
        if bool(reschedule_record and reschedule_record.late_reschedule_used):
            raise BusinessRuleException(
                message=(
                    "You've already used your late reschedule for this booking. "
                    "Please cancel and book a new lesson."
                ),
                code="reschedule_limit_reached",
            )

    @BaseService.measure_operation("validate_reschedule_payment_method")
    def validate_reschedule_payment_method(
        self,
        user_id: str,
    ) -> tuple[bool, Optional[str]]:
        """
        Validate that user has a valid payment method for rescheduling.

        Args:
            user_id: User ULID

        Returns:
            Tuple of (has_valid_method, stripe_payment_method_id)
        """
        pricing_service = PricingService(self.db)
        stripe_service = StripeService(
            self.db,
            config_service=self.config_service,
            pricing_service=pricing_service,
        )

        default_pm = stripe_service.payment_repository.get_default_payment_method(user_id)
        if not default_pm or not default_pm.stripe_payment_method_id:
            return False, None

        return True, default_pm.stripe_payment_method_id

    @BaseService.measure_operation("abort_pending_booking")
    def abort_pending_booking(self, booking_id: str) -> bool:
        """
        Abort a pending booking (used when reschedule payment confirmation fails).

        Only aborts bookings in pending_payment status.

        Args:
            booking_id: Booking ULID to abort

        Returns:
            True if aborted, False otherwise
        """
        try:
            booking = self.repository.get_by_id(booking_id)
            if not booking:
                return False

            # Only abort pending bookings
            if booking.status != BookingStatus.PENDING:
                logger.warning(
                    "Cannot abort booking %s - status is %s, not pending_payment",
                    booking_id,
                    booking.status,
                )
                return False

            with self.transaction():
                self.repository.delete(booking.id)

            logger.info("Aborted pending booking %s", booking_id)
            return True
        except Exception as e:
            logger.error("Failed to abort pending booking %s: %s", booking_id, e)
            return False
