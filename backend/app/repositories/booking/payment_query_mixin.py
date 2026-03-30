"""Payment pipeline queries for bookings."""

from datetime import date, datetime
from decimal import Decimal
from typing import List, cast

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import joinedload

from ...core.exceptions import RepositoryException
from ...models.booking import Booking, BookingStatus, PaymentStatus
from ...models.booking_payment import BookingPayment
from .mixin_base import BookingRepositoryMixinBase


class BookingPaymentQueryMixin(BookingRepositoryMixinBase):
    """Payment pipeline queries — authorization, capture, retry, expiration."""

    def get_instructor_completed_authorized_bookings(self, instructor_id: str) -> List[Booking]:
        """Return completed bookings with authorized payments for an instructor."""
        try:
            return cast(
                List[Booking],
                self.db.query(Booking)
                .join(BookingPayment, BookingPayment.booking_id == Booking.id)
                .options(
                    joinedload(Booking.payment_intent),
                    joinedload(Booking.payment_detail),
                )
                .filter(
                    Booking.instructor_id == instructor_id,
                    Booking.status == BookingStatus.COMPLETED,
                    BookingPayment.payment_status == PaymentStatus.AUTHORIZED.value,
                )
                .all(),
            )
        except Exception as exc:
            self.logger.error(
                "Error getting completed authorized bookings for instructor %s: %s",
                instructor_id,
                str(exc),
            )
            raise RepositoryException("Failed to get completed authorized bookings") from exc

    def sum_instructor_completed_total_price_since(
        self, instructor_id: str, window_start: datetime
    ) -> Decimal:
        """Sum total_price for completed bookings since the given timestamp."""
        try:
            total = (
                self.db.query(func.coalesce(func.sum(Booking.total_price), 0))
                .filter(
                    Booking.instructor_id == instructor_id,
                    Booking.status == BookingStatus.COMPLETED,
                    Booking.completed_at.isnot(None),
                    Booking.completed_at >= window_start,
                )
                .scalar()
            )
            return cast(Decimal, total)
        except Exception as exc:
            self.logger.error(
                "Error summing completed booking totals for instructor %s: %s",
                instructor_id,
                str(exc),
            )
            raise RepositoryException("Failed to sum completed booking totals") from exc

    def get_bookings_for_payment_authorization(self) -> List[Booking]:
        """Get bookings that need payment authorization."""
        try:
            return cast(
                List[Booking],
                self.db.query(Booking)
                .join(BookingPayment, BookingPayment.booking_id == Booking.id)
                .options(joinedload(Booking.payment_detail))
                .filter(
                    and_(
                        Booking.status == BookingStatus.CONFIRMED,
                        BookingPayment.payment_status == PaymentStatus.SCHEDULED.value,
                        BookingPayment.payment_method_id.isnot(None),
                    )
                )
                .all(),
            )
        except Exception as e:
            self.logger.error("Error getting bookings for payment authorization: %s", str(e))
            raise RepositoryException(f"Failed to get bookings for payment authorization: {str(e)}")

    def get_bookings_for_payment_retry(self) -> List[Booking]:
        """Get bookings that need payment retry."""
        try:
            return cast(
                List[Booking],
                self.db.query(Booking)
                .join(BookingPayment, BookingPayment.booking_id == Booking.id)
                .options(joinedload(Booking.payment_detail))
                .filter(
                    and_(
                        Booking.status == BookingStatus.CONFIRMED,
                        BookingPayment.payment_status
                        == PaymentStatus.PAYMENT_METHOD_REQUIRED.value,
                        BookingPayment.capture_failed_at.is_(None),
                        BookingPayment.payment_method_id.isnot(None),
                    )
                )
                .all(),
            )
        except Exception as e:
            self.logger.error("Error getting bookings for payment retry: %s", str(e))
            raise RepositoryException(f"Failed to get bookings for payment retry: {str(e)}")

    def get_bookings_for_payment_capture(self) -> List[Booking]:
        """Get bookings that are ready for payment capture."""
        try:
            return cast(
                List[Booking],
                self.db.query(Booking)
                .outerjoin(BookingPayment, BookingPayment.booking_id == Booking.id)
                .options(joinedload(Booking.payment_detail))
                .filter(
                    and_(
                        Booking.status == BookingStatus.COMPLETED,
                        or_(
                            and_(
                                BookingPayment.payment_status == PaymentStatus.AUTHORIZED.value,
                                BookingPayment.payment_intent_id.isnot(None),
                            ),
                            and_(
                                Booking.has_locked_funds.is_(True),
                                Booking.rescheduled_from_booking_id.isnot(None),
                            ),
                        ),
                        Booking.completed_at.isnot(None),
                    )
                )
                .all(),
            )
        except Exception as e:
            self.logger.error("Error getting bookings for payment capture: %s", str(e))
            raise RepositoryException(f"Failed to get bookings for payment capture: {str(e)}")

    def get_bookings_for_auto_completion(self) -> List[Booking]:
        """Get bookings that need auto-completion."""
        try:
            return cast(
                List[Booking],
                self.db.query(Booking)
                .outerjoin(BookingPayment, BookingPayment.booking_id == Booking.id)
                .options(joinedload(Booking.payment_detail))
                .filter(
                    and_(
                        Booking.status == BookingStatus.CONFIRMED,
                        or_(
                            and_(
                                BookingPayment.payment_status == PaymentStatus.AUTHORIZED.value,
                                BookingPayment.payment_intent_id.isnot(None),
                            ),
                            and_(
                                Booking.has_locked_funds.is_(True),
                                Booking.rescheduled_from_booking_id.isnot(None),
                            ),
                        ),
                    )
                )
                .all(),
            )
        except Exception as e:
            self.logger.error("Error getting bookings for auto completion: %s", str(e))
            raise RepositoryException(f"Failed to get bookings for auto completion: {str(e)}")

    def get_bookings_with_expired_auth(self) -> List[Booking]:
        """Get bookings with potentially expired authorization."""
        try:
            return cast(
                List[Booking],
                self.db.query(Booking)
                .join(BookingPayment, BookingPayment.booking_id == Booking.id)
                .options(joinedload(Booking.payment_detail))
                .filter(
                    and_(
                        BookingPayment.payment_status == PaymentStatus.AUTHORIZED.value,
                        BookingPayment.payment_intent_id.isnot(None),
                    )
                )
                .all(),
            )
        except Exception as e:
            self.logger.error("Error getting bookings with expired auth: %s", str(e))
            raise RepositoryException(f"Failed to get bookings with expired auth: {str(e)}")

    def get_failed_capture_booking_ids(self) -> List[str]:
        """Get booking IDs with failed captures needing retry."""
        try:
            rows = (
                self.db.query(Booking.id)
                .join(BookingPayment, BookingPayment.booking_id == Booking.id)
                .filter(
                    BookingPayment.payment_status == PaymentStatus.PAYMENT_METHOD_REQUIRED.value,
                    BookingPayment.capture_failed_at.isnot(None),
                )
                .all()
            )
            return [row[0] for row in rows]
        except Exception as e:
            self.logger.error("Error getting failed capture booking IDs: %s", str(e))
            raise RepositoryException(f"Failed to get failed capture booking IDs: {str(e)}")

    def count_overdue_authorizations(self, current_date: date) -> int:
        """Count bookings that are overdue for authorization."""
        try:
            return int(
                self.db.query(Booking)
                .join(BookingPayment, BookingPayment.booking_id == Booking.id)
                .filter(
                    and_(
                        Booking.status == BookingStatus.CONFIRMED,
                        BookingPayment.payment_status == PaymentStatus.SCHEDULED.value,
                        Booking.booking_date <= current_date,
                    )
                )
                .count()
            )
        except Exception as e:
            self.logger.error("Error counting overdue authorizations: %s", str(e))
            raise RepositoryException(f"Failed to count overdue authorizations: {str(e)}")
