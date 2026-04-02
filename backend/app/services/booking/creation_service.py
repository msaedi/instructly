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
    ValidationException,
)
from ...models.booking import Booking, BookingStatus
from ...models.instructor import InstructorProfile
from ...models.service_catalog import InstructorService
from ...models.user import User
from ...schemas.booking import BookingCreate
from ..base import BaseService

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from ...repositories.address_repository import InstructorServiceAreaRepository
    from ...repositories.booking_repository import BookingRepository
    from ...repositories.conflict_checker_repository import ConflictCheckerRepository
    from ..config_service import ConfigService

logger = logging.getLogger(__name__)


def _booking_service_module() -> ModuleType:
    from .. import booking_service as booking_service_module

    return booking_service_module


class BookingCreationMixin:
    if TYPE_CHECKING:
        db: Session
        repository: BookingRepository
        conflict_checker_repository: ConflictCheckerRepository
        service_area_repository: InstructorServiceAreaRepository
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

        def _handle_post_booking_tasks(
            self,
            booking: Booking,
            is_reschedule: bool = False,
            old_booking: Optional[Booking] = None,
        ) -> None:
            ...

        def _get_booking_start_utc(self, booking: Booking) -> Any:
            ...

        def _invalidate_booking_caches(self, booking: Booking) -> None:
            ...

        @staticmethod
        def _is_online_lesson(booking_data: BookingCreate) -> bool:
            ...

        @staticmethod
        def _resolve_instructor_timezone(instructor_profile: InstructorProfile) -> str:
            ...

        @staticmethod
        def _resolve_student_timezone(student: User) -> str:
            ...

        def _resolve_booking_times_utc(
            self,
            booking_date: Any,
            start_time: Any,
            end_time: Any,
            lesson_tz: str,
        ) -> tuple[Any, Any]:
            ...

    @BaseService.measure_operation("create_booking")
    def create_booking(
        self, student: User, booking_data: BookingCreate, selected_duration: int
    ) -> Booking:
        """Create an instant booking using selected duration."""
        booking_service_module = _booking_service_module()

        self.log_operation(
            "create_booking",
            student_id=student.id,
            instructor_id=booking_data.instructor_id,
            date=booking_data.booking_date,
            selected_duration=selected_duration,
        )
        self._validate_min_session_duration_floor(selected_duration)

        service, instructor_profile = self._validate_booking_prerequisites(student, booking_data)

        if selected_duration not in service.duration_options:
            raise BusinessRuleException(
                f"Invalid duration {selected_duration}. Available options: {service.duration_options}"
            )

        calculated_end_time = self._calculate_and_validate_end_time(
            booking_data.booking_date,
            booking_data.start_time,
            selected_duration,
        )
        booking_data.end_time = calculated_end_time
        self._validate_against_availability_bits(booking_data, instructor_profile)

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
                    message=booking_service_module.GENERIC_CONFLICT_MESSAGE,
                    details=conflict_details,
                ) from exc
            raise
        except RepositoryException as exc:
            self._raise_conflict_from_repo_error(exc, booking_data, student.id)

        self._handle_post_booking_tasks(booking)
        return booking

    def _validate_booking_prerequisites(
        self, student: User, booking_data: BookingCreate
    ) -> tuple[InstructorService, InstructorProfile]:
        """Validate student role and load required data."""
        booking_service_module = _booking_service_module()

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

        service = self.conflict_checker_repository.get_active_service(
            booking_data.instructor_service_id
        )
        if not service:
            raise NotFoundException("Service not found or no longer available")

        instructor_profile = self.conflict_checker_repository.get_instructor_profile(
            booking_data.instructor_id
        )
        if not instructor_profile:
            raise NotFoundException("Instructor profile not found")

        if service.instructor_profile_id != instructor_profile.id:
            raise ValidationException("Service does not belong to this instructor")

        user_repository = booking_service_module.RepositoryFactory.create_base_repository(
            self.db, User
        )
        instructor_user = user_repository.get_by_id(booking_data.instructor_id)
        if instructor_user and instructor_user.account_status != "active":
            if instructor_user.account_status == "suspended":
                raise BusinessRuleException(
                    "This instructor is temporarily suspended and cannot receive new bookings"
                )
            if instructor_user.account_status == "deactivated":
                raise BusinessRuleException(
                    "This instructor account has been deactivated and cannot receive bookings"
                )
            raise BusinessRuleException("This instructor cannot receive bookings at this time")

        if (
            booking_service_module.must_be_verified_for_public()
            and not booking_service_module.is_verified(
                getattr(instructor_profile, "bgc_status", None)
            )
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
        *,
        initial_status: BookingStatus = BookingStatus.CONFIRMED,
    ) -> Booking:
        """Create the booking record with pricing calculation."""
        booking_service_module = _booking_service_module()

        if booking_data.end_time is None:
            raise ValidationException("End time must be calculated before creating a booking")
        end_time_value = booking_data.end_time

        instructor_tz = self._resolve_instructor_timezone(instructor_profile)
        student_tz = self._resolve_student_timezone(student)
        lesson_tz = booking_service_module.TimezoneService.get_lesson_timezone(
            instructor_tz, self._is_online_lesson(booking_data)
        )
        booking_start_utc, booking_end_utc = self._resolve_booking_times_utc(
            booking_data.booking_date,
            booking_data.start_time,
            end_time_value,
            lesson_tz,
        )

        total_price = service.price_for_booking(selected_duration, booking_data.location_type)
        hourly_rate = service.hourly_rate_for_location_type(booking_data.location_type)
        service_area_summary = self._determine_service_area_summary(instructor_profile.user_id)

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
            status=initial_status,
            service_area=service_area_summary,
            meeting_location=booking_data.location_address or booking_data.meeting_location,
            location_type=booking_data.location_type,
            location_address=booking_data.location_address,
            location_lat=booking_data.location_lat,
            location_lng=booking_data.location_lng,
            location_place_id=booking_data.location_place_id,
            student_note=booking_data.student_note,
            confirmed_at=(
                booking_service_module.datetime.now(booking_service_module.timezone.utc)
                if initial_status == BookingStatus.CONFIRMED
                else None
            ),
        )

        detailed_booking = self.repository.get_booking_with_details(booking.id)
        pricing_service = booking_service_module.PricingService(self.db)
        pricing_service.compute_booking_pricing(booking.id, applied_credit_cents=0)
        return detailed_booking if detailed_booking is not None else booking

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
        start_time: Any,
        end_time: Any,
        location_type: str = "online",
    ) -> dict[str, Any]:
        """Calculate booking pricing based on time range."""
        booking_service_module = _booking_service_module()

        reference_date = booking_service_module.date(2024, 1, 1)
        start = booking_service_module.datetime.combine(
            reference_date, start_time, tzinfo=booking_service_module.timezone.utc
        )
        end = booking_service_module.datetime.combine(
            reference_date, end_time, tzinfo=booking_service_module.timezone.utc
        )
        duration = end - start
        duration_minutes = int(duration.total_seconds() / 60)
        resolved_rate = service.hourly_rate_for_location_type(location_type)
        total_price = float(service.price_for_booking(duration_minutes, location_type))

        return {
            "duration_minutes": duration_minutes,
            "total_price": total_price,
            "hourly_rate": resolved_rate,
        }
