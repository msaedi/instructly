"""Booking status changes — complete, cancel, refund, and no-show."""

from datetime import datetime
from typing import List, cast

from sqlalchemy import or_
from sqlalchemy.orm import joinedload

from ...core.exceptions import NotFoundException, RepositoryException
from ...models.booking import Booking, BookingStatus, PaymentStatus
from ...models.booking_no_show import BookingNoShow
from ...models.booking_payment import BookingPayment
from .mixin_base import BookingRepositoryMixinBase


class BookingStatusMutationMixin(BookingRepositoryMixinBase):
    """Booking status changes — complete, cancel, refund, and no-show."""

    def complete_booking(self, booking_id: str) -> Booking:
        """Mark booking as completed with timestamp."""
        try:
            booking = self.get_by_id(booking_id)
            if not booking:
                raise NotFoundException(f"Booking with id {booking_id} not found")

            booking.complete()

            self.db.flush()
            self.logger.info("Marked booking %s as completed", booking_id)

            self.invalidate_entity_cache(booking_id)
            self.invalidate_entity_cache(booking.student_id)
            self.invalidate_entity_cache(booking.instructor_id)

            return booking

        except NotFoundException:
            raise
        except Exception as e:
            self.logger.error("Error completing booking %s: %s", booking_id, str(e))
            raise RepositoryException(f"Failed to complete booking: {str(e)}")

    def cancel_booking(
        self, booking_id: str, cancelled_by_id: str, reason: str | None = None
    ) -> Booking:
        """Cancel booking with audit trail."""
        try:
            booking = self.get_by_id(booking_id)
            if not booking:
                raise NotFoundException(f"Booking with id {booking_id} not found")

            booking.cancel(cancelled_by_id, reason)

            self.db.flush()
            self.logger.info("Cancelled booking %s by user %s", booking_id, cancelled_by_id)

            self.invalidate_entity_cache(booking_id)
            self.invalidate_entity_cache(booking.student_id)
            self.invalidate_entity_cache(booking.instructor_id)

            return booking

        except NotFoundException:
            raise
        except Exception as e:
            self.logger.error("Error cancelling booking %s: %s", booking_id, str(e))
            raise RepositoryException(f"Failed to cancel booking: {str(e)}")

    def apply_refund_updates(
        self,
        booking: Booking,
        *,
        status: BookingStatus,
        cancelled_at: datetime,
        cancellation_reason: str | None,
        settlement_outcome: str | None,
        refunded_to_card_amount: int,
        student_credit_amount: int,
        instructor_payout_amount: int,
        updated_at: datetime,
    ) -> Booking:
        """Apply refund-related updates to a booking and flush changes."""
        try:
            if status != BookingStatus.CANCELLED:
                raise RepositoryException(
                    f"Refund updates only support cancelled bookings, got {status.value}"
                )
            booking.mark_cancelled(
                cancelled_at=booking.cancelled_at or cancelled_at,
                reason=cancellation_reason,
            )
            payment = self.ensure_payment(booking.id)
            if settlement_outcome:
                payment.settlement_outcome = settlement_outcome
            booking.refunded_to_card_amount = refunded_to_card_amount
            booking.student_credit_amount = student_credit_amount
            payment.instructor_payout_amount = instructor_payout_amount
            booking.updated_at = updated_at

            self.db.flush()
            self.logger.info("Applied refund updates for booking %s", booking.id)

            self.invalidate_entity_cache(booking.id)
            self.invalidate_entity_cache(booking.student_id)
            self.invalidate_entity_cache(booking.instructor_id)
            return booking
        except Exception as e:
            self.logger.error(
                "Error applying refund updates for booking %s: %s",
                booking.id,
                str(e),
            )
            raise RepositoryException(f"Failed to apply refund updates: {str(e)}")

    def mark_no_show(self, booking_id: str) -> Booking:
        """Mark booking as no-show."""
        try:
            booking = self.get_by_id(booking_id)
            if not booking:
                raise NotFoundException(f"Booking with id {booking_id} not found")

            booking.mark_no_show()

            self.db.flush()
            self.logger.info("Marked booking %s as no-show", booking_id)

            return booking

        except NotFoundException:
            raise
        except Exception as e:
            self.logger.error("Error marking booking %s as no-show: %s", booking_id, str(e))
            raise RepositoryException(f"Failed to mark booking as no-show: {str(e)}")

    def mark_payment_failed(self, booking_id: str) -> Booking:
        """Mark a pending booking as payment failed."""
        try:
            booking = self.get_by_id(booking_id)
            if not booking:
                raise NotFoundException(f"Booking with id {booking_id} not found")

            booking.mark_payment_failed()

            self.db.flush()
            self.logger.info("Marked booking %s as payment failed", booking_id)

            self.invalidate_entity_cache(booking_id)
            self.invalidate_entity_cache(booking.student_id)
            self.invalidate_entity_cache(booking.instructor_id)

            return booking

        except NotFoundException:
            raise
        except Exception as e:
            self.logger.error("Error marking booking %s as payment failed: %s", booking_id, str(e))
            raise RepositoryException(f"Failed to mark booking as payment failed: {str(e)}")

    def get_no_show_reports_due_for_resolution(self, *, reported_before: datetime) -> List[Booking]:
        """Return no-show reports older than cutoff, undisputed and unresolved."""
        try:
            query = (
                self.db.query(Booking)
                .join(BookingNoShow, BookingNoShow.booking_id == Booking.id)
                .join(BookingPayment, BookingPayment.booking_id == Booking.id)
                .filter(
                    BookingNoShow.no_show_reported_at.is_not(None),
                    BookingNoShow.no_show_reported_at <= reported_before,
                    or_(
                        BookingNoShow.no_show_disputed.is_(False),
                        BookingNoShow.no_show_disputed.is_(None),
                    ),
                    BookingNoShow.no_show_resolved_at.is_(None),
                    BookingPayment.payment_status == PaymentStatus.MANUAL_REVIEW.value,
                )
                .options(
                    joinedload(Booking.no_show_detail),
                    joinedload(Booking.payment_detail),
                )
                .order_by(BookingNoShow.no_show_reported_at.asc())
            )
            return cast(List[Booking], query.all())
        except Exception as exc:
            self.logger.error("Failed to load no-show reports due for resolution: %s", str(exc))
            raise RepositoryException("Failed to load no-show reports due for resolution") from exc
