"""Admin booking listing with search, filters, and pagination."""

from datetime import date, datetime, timezone
from typing import List, Optional, Sequence, Tuple, cast

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Query, aliased, joinedload, selectinload

from ...core.exceptions import RepositoryException
from ...models.booking import Booking, BookingStatus, PaymentStatus
from ...models.booking_payment import BookingPayment
from ...models.user import User
from .mixin_base import BookingRepositoryMixinBase


class BookingAdminQueryMixin(BookingRepositoryMixinBase):
    """Admin booking listing with search, filters, and pagination."""

    def _build_admin_base_query(self) -> Query:
        """Build the base admin booking query with eager loading."""
        return (
            self.db.query(Booking)
            .outerjoin(BookingPayment, BookingPayment.booking_id == Booking.id)
            .options(
                joinedload(Booking.student),
                joinedload(Booking.instructor),
                joinedload(Booking.instructor_service),
                selectinload(Booking.payment_detail),
                selectinload(Booking.no_show_detail),
                selectinload(Booking.lock_detail),
                selectinload(Booking.reschedule_detail),
                selectinload(Booking.dispute),
                selectinload(Booking.transfer),
                selectinload(Booking.video_session),
            )
        )

    def _apply_admin_search_filter(self, query: Query, search: Optional[str]) -> Query:
        """Apply student, instructor, service, and payment search filters."""
        if not search:
            return query

        student_alias = aliased(User)
        instructor_alias = aliased(User)
        term = f"%{search.strip()}%"
        return (
            query.join(student_alias, Booking.student_id == student_alias.id)
            .join(instructor_alias, Booking.instructor_id == instructor_alias.id)
            .filter(
                or_(
                    Booking.id.ilike(term),
                    Booking.service_name.ilike(term),
                    BookingPayment.payment_intent_id.ilike(term),
                    student_alias.first_name.ilike(term),
                    student_alias.last_name.ilike(term),
                    student_alias.email.ilike(term),
                    instructor_alias.first_name.ilike(term),
                    instructor_alias.last_name.ilike(term),
                    instructor_alias.email.ilike(term),
                )
            )
        )

    def _apply_admin_status_filters(
        self,
        query: Query,
        statuses: Optional[Sequence[str]],
        payment_statuses: Optional[Sequence[str]],
    ) -> Query:
        """Apply booking and payment status filters."""
        if statuses:
            cleaned_statuses = [status.upper() for status in statuses if status]
            if cleaned_statuses:
                query = query.filter(Booking.status.in_(cleaned_statuses))

        if payment_statuses:
            cleaned_payments = [status.lower() for status in payment_statuses if status]
            if cleaned_payments:
                filters = []
                if "pending" in cleaned_payments:
                    filters.append(BookingPayment.payment_status.is_(None))
                    filters.append(
                        func.lower(BookingPayment.payment_status)
                        == PaymentStatus.PAYMENT_METHOD_REQUIRED.value
                    )
                    cleaned_payments = [
                        status for status in cleaned_payments if status != "pending"
                    ]
                if "refunded" in cleaned_payments:
                    refund_outcomes = {
                        "admin_refund",
                        "instructor_cancel_full_refund",
                        "instructor_no_show_full_refund",
                        "student_wins_dispute_full_refund",
                    }
                    filters.append(
                        and_(
                            func.lower(BookingPayment.payment_status)
                            == PaymentStatus.SETTLED.value,
                            BookingPayment.settlement_outcome.in_(refund_outcomes),
                        )
                    )
                    cleaned_payments = [
                        status for status in cleaned_payments if status != "refunded"
                    ]
                if cleaned_payments:
                    filters.append(func.lower(BookingPayment.payment_status).in_(cleaned_payments))
                query = query.filter(or_(*filters))

        return query

    def _apply_admin_date_filters(
        self,
        query: Query,
        date_from: Optional[date],
        date_to: Optional[date],
        needs_action: Optional[bool],
        now: Optional[datetime],
    ) -> Query:
        """Apply booking date range and needs-action filters."""
        if date_from:
            query = query.filter(Booking.booking_date >= date_from)
        if date_to:
            query = query.filter(Booking.booking_date <= date_to)
        if needs_action:
            effective_now = now or datetime.now(timezone.utc)
            query = query.filter(Booking.status == BookingStatus.CONFIRMED)
            query = query.filter(Booking.booking_end_utc <= effective_now)
        return query

    def list_admin_bookings(
        self,
        *,
        search: Optional[str],
        statuses: Optional[Sequence[str]],
        payment_statuses: Optional[Sequence[str]],
        date_from: Optional[date],
        date_to: Optional[date],
        needs_action: Optional[bool],
        now: Optional[datetime],
        page: int,
        per_page: int,
    ) -> Tuple[List[Booking], int]:
        """Return admin booking list with filters and pagination."""
        try:
            query = self._build_admin_base_query()
            query = self._apply_admin_search_filter(query, search)
            query = self._apply_admin_status_filters(query, statuses, payment_statuses)
            query = self._apply_admin_date_filters(
                query,
                date_from=date_from,
                date_to=date_to,
                needs_action=needs_action,
                now=now,
            )

            total = int(query.count())
            offset = max(0, (page - 1) * per_page)
            bookings = (
                query.order_by(Booking.created_at.desc()).offset(offset).limit(per_page).all()
            )
            return cast(List[Booking], bookings), total
        except Exception as e:
            self.logger.error("Error listing admin bookings: %s", str(e))
            raise RepositoryException(f"Failed to list admin bookings: {str(e)}")

    def get_bookings_for_date(
        self,
        booking_date: date,
        status: Optional[BookingStatus] = None,
        with_relationships: bool = False,
    ) -> List[Booking]:
        """Get bookings for a specific date (system-wide)."""
        try:
            query = self.db.query(Booking).filter(Booking.booking_date == booking_date)

            if status:
                query = query.filter(Booking.status == status)

            if with_relationships:
                query = query.options(
                    selectinload(Booking.student), selectinload(Booking.instructor)
                )

            return cast(List[Booking], query.all())

        except Exception as e:
            self.logger.error("Error getting bookings for date: %s", str(e))
            raise RepositoryException(f"Failed to get bookings for date: {str(e)}")

    def count_old_bookings(self, cutoff_date: datetime) -> int:
        """Count bookings created before a cutoff date."""
        return int(
            self.db.query(func.count(Booking.id)).filter(Booking.created_at < cutoff_date).scalar()
            or 0
        )

    def get_bookings_by_date_and_status(self, booking_date: date, status: str) -> List[Booking]:
        """Get all bookings for a specific date and status."""
        try:
            return cast(
                List[Booking],
                self.db.query(Booking)
                .filter(Booking.booking_date == booking_date, Booking.status == status)
                .options(selectinload(Booking.student), selectinload(Booking.instructor))
                .all(),
            )
        except Exception as e:
            self.logger.warning(
                "Failed to load bookings for date %s and status %s: %s",
                booking_date,
                status,
                str(e),
                exc_info=True,
            )
            return []

    def get_bookings_by_date_range_and_status(
        self, start_date: date, end_date: date, status: str
    ) -> List[Booking]:
        """Get all bookings within a date range for a specific status."""
        try:
            return cast(
                List[Booking],
                self.db.query(Booking)
                .filter(
                    Booking.booking_date >= start_date,
                    Booking.booking_date <= end_date,
                    Booking.status == status,
                )
                .options(selectinload(Booking.student), selectinload(Booking.instructor))
                .all(),
            )
        except Exception as e:
            self.logger.warning(
                "Failed to load bookings from %s to %s for status %s: %s",
                start_date,
                end_date,
                status,
                str(e),
                exc_info=True,
            )
            return []
