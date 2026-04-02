from __future__ import annotations

import logging
from types import ModuleType
from typing import TYPE_CHECKING, Any, ContextManager, Optional, cast

from sqlalchemy.exc import IntegrityError, OperationalError

from ...core.enums import RoleName
from ...core.exceptions import (
    BookingConflictException,
    BusinessRuleException,
    NotFoundException,
    RepositoryException,
)
from ...models.booking import Booking, BookingStatus, PaymentStatus
from ...models.instructor import InstructorProfile
from ...models.service_catalog import InstructorService
from ...models.user import User
from ...schemas.booking import BookingCreate
from ..base import BaseService

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from ...repositories.booking_repository import BookingRepository
    from ..config_service import ConfigService

logger = logging.getLogger(__name__)


def _booking_service_module() -> ModuleType:
    from .. import booking_service as booking_service_module

    return booking_service_module


def _is_mock_like(value: object) -> bool:
    return type(value).__module__.startswith("unittest.mock")


def _stripe_service_class() -> Any:
    booking_service_module = _booking_service_module()
    from .. import stripe_service as stripe_service_module

    facade_cls = booking_service_module.StripeService
    source_cls = stripe_service_module.StripeService
    if _is_mock_like(facade_cls):
        return facade_cls
    if _is_mock_like(source_cls):
        return source_cls
    return facade_cls


class BookingCreationPaymentMixin:
    if TYPE_CHECKING:
        db: Session
        repository: BookingRepository
        config_service: ConfigService

        def transaction(self) -> ContextManager[None]:
            ...

        def log_operation(self, operation: str, **kwargs: Any) -> None:
            ...

        def _validate_min_session_duration_floor(self, selected_duration: int) -> None:
            ...

        def _calculate_and_validate_end_time(
            self,
            booking_date: Any,
            start_time: Any,
            selected_duration: int,
        ) -> Any:
            ...

        def _validate_against_availability_bits(
            self,
            booking_data: BookingCreate,
            instructor_profile: InstructorProfile,
        ) -> None:
            ...

        def _validate_booking_prerequisites(
            self,
            student: User,
            booking_data: BookingCreate,
        ) -> tuple[InstructorService, InstructorProfile]:
            ...

        def _acquire_booking_create_advisory_lock(
            self,
            instructor_id: str,
            booking_date: Any,
        ) -> None:
            ...

        def _check_conflicts_and_rules(
            self,
            booking_data: BookingCreate,
            service: InstructorService,
            instructor_profile: InstructorProfile,
            student: User,
        ) -> None:
            ...

        def _create_booking_record(
            self,
            student: User,
            booking_data: BookingCreate,
            service: InstructorService,
            instructor_profile: InstructorProfile,
            selected_duration: int,
            *,
            initial_status: BookingStatus = BookingStatus.CONFIRMED,
        ) -> Booking:
            ...

        def _enqueue_booking_outbox_event(self, booking: Booking, event_type: str) -> None:
            ...

        def _snapshot_booking(self, booking: Booking) -> dict[str, Any]:
            ...

        def _write_booking_audit(
            self,
            booking: Booking,
            action: str,
            *,
            actor: Any | None,
            before: dict[str, Any] | None,
            after: dict[str, Any] | None,
            default_role: str = "system",
        ) -> None:
            ...

        def _resolve_integrity_conflict_message(
            self,
            exc: IntegrityError,
        ) -> tuple[str, str | None]:
            ...

        def _build_conflict_details(
            self,
            booking_data: BookingCreate,
            student_id: str,
        ) -> dict[str, Any]:
            ...

        def _is_deadlock_error(self, exc: OperationalError) -> bool:
            ...

        def _raise_conflict_from_repo_error(
            self,
            exc: RepositoryException,
            booking_data: BookingCreate,
            student_id: str,
        ) -> None:
            ...

        def _get_booking_start_utc(self, booking: Booking) -> Any:
            ...

        def _invalidate_booking_caches(self, booking: Booking) -> None:
            ...

    @BaseService.measure_operation("create_booking_with_payment_setup")
    def create_booking_with_payment_setup(
        self,
        student: User,
        booking_data: BookingCreate,
        selected_duration: int,
        rescheduled_from_booking_id: Optional[str] = None,
    ) -> Booking:
        """Create a booking with payment setup (Phase 2.1)."""
        booking_service_module = _booking_service_module()

        self.log_operation(
            "create_booking_with_payment_setup",
            student_id=student.id,
            instructor_id=booking_data.instructor_id,
            date=booking_data.booking_date,
        )
        self._validate_min_session_duration_floor(selected_duration)
        service, instructor_profile = self._prepare_booking_with_payment_setup(
            student,
            booking_data,
            selected_duration,
        )
        booking = self._create_pending_booking_with_payment_setup(
            student=student,
            booking_data=booking_data,
            service=service,
            instructor_profile=instructor_profile,
            selected_duration=selected_duration,
            rescheduled_from_booking_id=rescheduled_from_booking_id,
        )
        setup_intent = self._create_booking_setup_intent(
            booking=booking,
            student=student,
            booking_data=booking_data,
            pricing_service=booking_service_module.PricingService(self.db),
        )
        booking = self._persist_booking_setup_intent(booking.id, setup_intent)
        self._finalize_booking_with_payment_setup(booking)
        return booking

    def _prepare_booking_with_payment_setup(
        self,
        student: User,
        booking_data: BookingCreate,
        selected_duration: int,
    ) -> tuple[InstructorService, InstructorProfile]:
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
        return service, instructor_profile

    def _create_pending_booking_with_payment_setup(
        self,
        *,
        student: User,
        booking_data: BookingCreate,
        service: InstructorService,
        instructor_profile: InstructorProfile,
        selected_duration: int,
        rescheduled_from_booking_id: Optional[str],
    ) -> Booking:
        booking_service_module = _booking_service_module()
        transactional_repo = cast(Any, self.repository)
        try:
            with transactional_repo.transaction():
                self._acquire_booking_create_advisory_lock(
                    booking_data.instructor_id,
                    booking_data.booking_date,
                )
                self._check_conflicts_and_rules(booking_data, service, instructor_profile, student)
                booking = self._create_booking_record(
                    student,
                    booking_data,
                    service,
                    instructor_profile,
                    selected_duration,
                    initial_status=BookingStatus.PENDING,
                )
                if rescheduled_from_booking_id:
                    booking = self._persist_payment_setup_reschedule_linkage(
                        booking, rescheduled_from_booking_id
                    )
                bp = self.repository.ensure_payment(booking.id)
                bp.payment_status = PaymentStatus.PAYMENT_METHOD_REQUIRED.value
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
                return booking
        except IntegrityError as exc:
            message, scope = self._resolve_integrity_conflict_message(exc)
            conflict_details = self._build_conflict_details(booking_data, student.id)
            if scope:
                conflict_details["conflict_scope"] = scope
            raise BookingConflictException(message=message, details=conflict_details) from exc
        except OperationalError as exc:
            if self._is_deadlock_error(exc):
                conflict_details = self._build_conflict_details(booking_data, student.id)
                raise BookingConflictException(
                    message=booking_service_module.GENERIC_CONFLICT_MESSAGE,
                    details=conflict_details,
                ) from exc
            raise
        except RepositoryException as exc:
            self._raise_conflict_from_repo_error(exc, booking_data, student.id)
        raise NotFoundException("Booking creation failed")

    def _persist_payment_setup_reschedule_linkage(
        self,
        booking: Booking,
        rescheduled_from_booking_id: str,
    ) -> Booking:
        previous_booking = self.repository.get_by_id(rescheduled_from_booking_id)
        original_lesson_dt = (
            self._get_booking_start_utc(previous_booking) if previous_booking else None
        )
        updated_booking = self.repository.update(
            booking.id,
            rescheduled_from_booking_id=rescheduled_from_booking_id,
        )
        if updated_booking is not None:
            booking = updated_booking
        if previous_booking:
            previous_reschedule = self.repository.ensure_reschedule(previous_booking.id)
            current_reschedule = self.repository.ensure_reschedule(booking.id)
            current_reschedule.original_lesson_datetime = original_lesson_dt
            previous_reschedule.rescheduled_to_booking_id = booking.id
            if bool(previous_reschedule.late_reschedule_used):
                current_reschedule.late_reschedule_used = True
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
        return booking

    def _create_booking_setup_intent(
        self,
        *,
        booking: Booking,
        student: User,
        booking_data: BookingCreate,
        pricing_service: Any,
    ) -> Any:
        booking_service_module = _booking_service_module()
        stripe_service = _stripe_service_class()(
            self.db,
            config_service=self.config_service,
            pricing_service=pricing_service,
        )
        stripe_customer = stripe_service.get_or_create_customer(student.id)
        try:
            return booking_service_module.stripe.SetupIntent.create(
                customer=stripe_customer.stripe_customer_id,
                automatic_payment_methods={"enabled": True, "allow_redirects": "never"},
                usage="off_session",
                metadata={
                    "booking_id": booking.id,
                    "student_id": student.id,
                    "instructor_id": booking_data.instructor_id,
                    "amount_cents": int(booking.total_price * 100),
                },
            )
        except Exception as exc:
            site_mode = (
                booking_service_module.os.getenv("SITE_MODE", "")
                or booking_service_module.settings.site_mode
            ).lower()
            is_test_or_ci = booking_service_module._is_test_or_ci()
            if site_mode == "prod" or not is_test_or_ci:
                logger.error(
                    "SetupIntent creation failed for booking %s (site_mode=%s, test_or_ci=%s)",
                    booking.id,
                    site_mode,
                    is_test_or_ci,
                    exc_info=True,
                )
                raise
            logger.warning(
                "SetupIntent creation failed for booking %s in test/CI: %s. Falling back to mock.",
                booking.id,
                exc,
            )
            return booking_service_module.SimpleNamespace(
                id=f"seti_mock_{booking.id}",
                client_secret=f"seti_mock_secret_{booking.id}",
                status="requires_payment_method",
            )

    def _persist_booking_setup_intent(self, booking_id: str, setup_intent: Any) -> Booking:
        from ...repositories.payment_repository import PaymentRepository

        with self.transaction():
            refreshed_booking = self.repository.get_by_id(booking_id)
            if not refreshed_booking:
                raise NotFoundException("Booking not found after setup intent creation")
            setattr(
                refreshed_booking,
                "setup_intent_client_secret",
                getattr(setup_intent, "client_secret", None),
            )
            payment_repo = PaymentRepository(self.db)
            payment_repo.create_payment_event(
                booking_id=refreshed_booking.id,
                event_type="setup_intent_created",
                event_data={
                    "setup_intent_id": setup_intent.id,
                    "status": setup_intent.status,
                },
            )
            return refreshed_booking

    def _finalize_booking_with_payment_setup(self, booking: Booking) -> None:
        try:
            self._invalidate_booking_caches(booking)
        except Exception:
            logger.debug(
                "Failed to invalidate booking caches after payment setup for booking %s",
                booking.id,
                exc_info=True,
            )
        self.log_operation("create_booking_with_payment_setup_completed", booking_id=booking.id)
