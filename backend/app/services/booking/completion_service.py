from __future__ import annotations

from datetime import timedelta
import logging
from types import ModuleType
from typing import TYPE_CHECKING, Any, ContextManager, Optional, cast

from ...core.enums import RoleName
from ...core.exceptions import BusinessRuleException, NotFoundException, ValidationException
from ...models.booking import Booking, BookingStatus, PaymentStatus
from ...models.user import User
from ...schemas.booking import BookingUpdate
from ..base import BaseService
from ..student_credit_service import StudentCreditService

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from ...repositories.booking_repository import BookingRepository
    from ..system_message_service import SystemMessageService

logger = logging.getLogger(__name__)


def _booking_service_module() -> ModuleType:
    from .. import booking_service as booking_service_module

    return booking_service_module


class BookingCompletionMixin:
    if TYPE_CHECKING:
        db: Session
        repository: BookingRepository
        system_message_service: SystemMessageService

        def transaction(self) -> ContextManager[None]:
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

        def _enqueue_booking_outbox_event(self, booking: Booking, event_type: str) -> None:
            ...

        def _invalidate_booking_caches(self, booking: Booking) -> None:
            ...

        def _maybe_refresh_instructor_tier(self, instructor_user_id: str, booking_id: str) -> None:
            ...

        def _get_booking_end_utc(self, booking: Booking) -> Any:
            ...

    @BaseService.measure_operation("update_booking")
    def update_booking(self, booking_id: str, user: User, update_data: BookingUpdate) -> Booking:
        """
        Update booking details (instructor only).

        Args:
            booking_id: ID of booking to update
            user: User performing update
            update_data: Fields to update

        Returns:
            Updated booking

        Raises:
            NotFoundException: If booking not found
            ValidationException: If user cannot update
        """
        with self.transaction():
            booking = self.repository.get_booking_with_details(booking_id)

            if not booking:
                raise NotFoundException("Booking not found")

            # Only instructors can update bookings
            if user.id != booking.instructor_id:
                raise ValidationException("Only the instructor can update booking details")

            audit_before = self._snapshot_booking(booking)

            # Update allowed fields using repository
            update_dict = {}
            if update_data.instructor_note is not None:
                update_dict["instructor_note"] = update_data.instructor_note
            if update_data.meeting_location is not None:
                update_dict["meeting_location"] = update_data.meeting_location

            if update_dict:
                updated_booking = self.repository.update(booking_id, **update_dict)
                if updated_booking is not None:
                    booking = updated_booking

            # Reload with relationships
            refreshed_booking = self.repository.get_booking_with_details(booking_id)
            if not refreshed_booking:
                raise NotFoundException("Booking not found")
            audit_after = self._snapshot_booking(refreshed_booking)
            self._write_booking_audit(
                refreshed_booking,
                "update",
                actor=user,
                before=audit_before,
                after=audit_after,
                default_role=RoleName.INSTRUCTOR.value,
            )
            booking = refreshed_booking

        # Cache invalidation outside transaction
        self._invalidate_booking_caches(booking)

        return booking

    @BaseService.measure_operation("complete_booking")
    def complete_booking(self, booking_id: str, instructor: User) -> Booking:
        """
        Mark a booking as completed (instructor only).

        Args:
            booking_id: ID of booking to complete
            instructor: Instructor marking as complete

        Returns:
            Completed booking

        Raises:
            NotFoundException: If booking not found
            ValidationException: If user is not instructor
            BusinessRuleException: If booking cannot be completed
        """
        instructor_roles = cast(list[Any], getattr(instructor, "roles", []) or [])
        is_instructor = any(
            cast(str, getattr(role, "name", "")) == RoleName.INSTRUCTOR for role in instructor_roles
        )
        if not is_instructor:
            raise ValidationException("Only instructors can mark bookings as complete")

        with self.transaction():
            # Load and validate booking
            booking = self.repository.get_booking_with_details(booking_id)

            if not booking:
                raise NotFoundException("Booking not found")

            if booking.instructor_id != instructor.id:
                raise ValidationException("You can only complete your own bookings")

            if booking.status != BookingStatus.CONFIRMED:
                raise BusinessRuleException(
                    f"Only confirmed bookings can be completed - current status: {booking.status}"
                )

            audit_before = self._snapshot_booking(booking)

            # Mark as complete using repository method
            completed_booking = self.repository.complete_booking(booking_id)
            if completed_booking is None:
                raise NotFoundException("Booking not found")
            booking = completed_booking
            self._enqueue_booking_outbox_event(booking, "booking.completed")
            audit_after = self._snapshot_booking(booking)
            self._write_booking_audit(
                booking,
                "complete",
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

        try:
            credit_service = StudentCreditService(self.db)
            credit_service.maybe_issue_milestone_credit(
                student_id=refreshed_booking.student_id,
                booking_id=refreshed_booking.id,
            )
        except Exception as exc:
            logger.error(
                "Failed issuing milestone credit for booking completion %s: %s",
                booking_id,
                exc,
            )

        # Create system message in conversation
        try:
            service_name = None
            if refreshed_booking.instructor_service and refreshed_booking.instructor_service.name:
                service_name = refreshed_booking.instructor_service.name

            self.system_message_service.create_booking_completed_message(
                student_id=refreshed_booking.student_id,
                instructor_id=refreshed_booking.instructor_id,
                booking_id=refreshed_booking.id,
                booking_date=refreshed_booking.booking_date,
                service_name=service_name,
            )
        except Exception as e:
            logger.error(
                "Failed to create completion system message for booking %s: %s", booking_id, str(e)
            )

        booking_service_module = _booking_service_module()

        try:
            from app.services.referral_service import ReferralService

            referral_service = ReferralService(self.db)
            referral_service.on_instructor_lesson_completed(
                instructor_user_id=refreshed_booking.instructor_id,
                booking_id=refreshed_booking.id,
                completed_at=refreshed_booking.completed_at
                or booking_service_module.datetime.now(booking_service_module.timezone.utc),
            )
        except Exception as exc:
            logger.error(
                "Failed to process instructor referral payout for booking %s: %s",
                booking_id,
                exc,
                exc_info=True,
            )

        self._maybe_refresh_instructor_tier(refreshed_booking.instructor_id, refreshed_booking.id)

        return refreshed_booking

    @BaseService.measure_operation("instructor_mark_complete")
    def instructor_mark_complete(
        self,
        booking_id: str,
        instructor: User,
        notes: Optional[str] = None,
    ) -> Booking:
        """
        Mark a lesson as completed by the instructor with payment tracking.

        This triggers the 24-hour payment capture timer. The payment will be
        captured 24 hours after lesson end, giving the student time to dispute.

        Args:
            booking_id: ID of the booking to complete
            instructor: The instructor marking completion
            notes: Optional completion notes

        Returns:
            Updated booking

        Raises:
            NotFoundException: If booking not found
            ValidationException: If not the instructor's booking
            BusinessRuleException: If booking cannot be completed
        """
        from ...repositories.payment_repository import PaymentRepository
        from ..badge_award_service import BadgeAwardService

        booking_service_module = _booking_service_module()
        payment_repo = PaymentRepository(self.db)

        with self.transaction():
            # Defense-in-depth: filter by instructor at DB level (AUTHZ-VULN-01)
            booking = self.repository.get_booking_for_instructor(booking_id, instructor.id)
            if not booking:
                raise NotFoundException("Booking not found")

            if booking.status != BookingStatus.CONFIRMED:
                raise BusinessRuleException(
                    f"Cannot mark booking as complete. Current status: {booking.status}"
                )

            # Verify lesson has ended
            now = booking_service_module.datetime.now(booking_service_module.timezone.utc)
            lesson_end_utc = self._get_booking_end_utc(booking)
            if lesson_end_utc > now:
                raise BusinessRuleException("Cannot mark lesson as complete before it ends")

            # Mark as completed
            booking.status = BookingStatus.COMPLETED
            booking.completed_at = now
            if notes:
                booking.instructor_note = notes

            capture_at = lesson_end_utc + timedelta(hours=24)

            # Record payment completion event
            payment_repo.create_payment_event(
                booking_id=booking.id,
                event_type="instructor_marked_complete",
                event_data={
                    "instructor_id": instructor.id,
                    "completed_at": now.isoformat(),
                    "notes": notes,
                    "payment_capture_scheduled_for": capture_at.isoformat(),
                },
            )

            # Trigger badge checks
            badge_service = BadgeAwardService(self.db)
            booked_at = booking.confirmed_at or booking.created_at or now
            category_name = None
            try:
                instructor_service = booking.instructor_service
                if instructor_service and instructor_service.catalog_entry:
                    category = instructor_service.catalog_entry.category
                    category_name = category.name if category else None
            except Exception as exc:
                logger.warning(
                    "booking_category_chain_failed",
                    extra={"booking_id": booking.id, "error": str(exc)},
                )

            badge_service.check_and_award_on_lesson_completed(
                student_id=booking.student_id,
                lesson_id=booking.id,
                instructor_id=booking.instructor_id,
                category_name=category_name,
                booked_at_utc=booked_at,
                completed_at_utc=now,
            )

        # Reload for fresh state after commit
        refreshed = self.repository.get_by_id(booking_id)
        if refreshed is None:
            raise NotFoundException("Booking not found after completion")

        try:
            from app.services.referral_service import ReferralService

            referral_service = ReferralService(self.db)
            referral_service.on_instructor_lesson_completed(
                instructor_user_id=refreshed.instructor_id,
                booking_id=refreshed.id,
                completed_at=refreshed.completed_at
                or booking_service_module.datetime.now(booking_service_module.timezone.utc),
            )
        except Exception as exc:
            logger.error(
                "Failed to process instructor referral payout for booking %s: %s",
                booking_id,
                exc,
                exc_info=True,
            )

        self._maybe_refresh_instructor_tier(refreshed.instructor_id, refreshed.id)

        return refreshed

    @BaseService.measure_operation("instructor_dispute_completion")
    def instructor_dispute_completion(
        self,
        booking_id: str,
        instructor: User,
        reason: str,
    ) -> Booking:
        """
        Dispute a lesson completion as an instructor.

        Used when a student marks a lesson as complete but the instructor disagrees.
        This pauses payment capture pending resolution.

        Args:
            booking_id: ID of the booking to dispute
            instructor: The instructor disputing
            reason: Reason for the dispute

        Returns:
            Updated booking

        Raises:
            NotFoundException: If booking not found
            ValidationException: If not the instructor's booking
        """
        from ...repositories.payment_repository import PaymentRepository

        booking_service_module = _booking_service_module()
        payment_repo = PaymentRepository(self.db)

        with self.transaction():
            # Defense-in-depth: filter by instructor at DB level (AUTHZ-VULN-01)
            booking = self.repository.get_booking_for_instructor(booking_id, instructor.id)
            if not booking:
                raise NotFoundException("Booking not found")

            # Record dispute event
            payment_repo.create_payment_event(
                booking_id=booking.id,
                event_type="completion_disputed",
                event_data={
                    "disputed_by": instructor.id,
                    "reason": reason,
                    "disputed_at": booking_service_module.datetime.now(
                        booking_service_module.timezone.utc
                    ).isoformat(),
                    "payment_capture_paused": True,
                },
            )

            # Update payment status to prevent capture
            dispute_bp = self.repository.ensure_payment(booking.id)
            if dispute_bp.payment_status == PaymentStatus.AUTHORIZED.value:
                dispute_bp.payment_status = PaymentStatus.MANUAL_REVIEW.value

        # Reload for fresh state after commit
        refreshed = self.repository.get_by_id(booking_id)
        if refreshed is None:
            raise NotFoundException("Booking not found after dispute")
        return refreshed
