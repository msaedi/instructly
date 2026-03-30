"""Detailed booking fetches, participant authorization, and pricing context."""

from typing import List, Optional, Sequence, cast

from sqlalchemy import or_
from sqlalchemy.orm import Query, joinedload, selectinload

from ...core.exceptions import RepositoryException
from ...models.booking import Booking
from ...models.user import User
from .mixin_base import BookingRepositoryMixinBase


class BookingDetailQueryMixin(BookingRepositoryMixinBase):
    """Detailed booking fetches, participant authorization, and pricing context."""

    def get_by_ids(
        self, booking_ids: Sequence[str], load_relationships: bool = True
    ) -> List[Booking]:
        """Fetch multiple bookings in a single query."""
        ids = [booking_id for booking_id in booking_ids if booking_id]
        if not ids:
            return []

        try:
            query = self.db.query(Booking).filter(Booking.id.in_(ids))
            if load_relationships:
                query = self._apply_eager_loading(query)
            return cast(List[Booking], query.all())
        except Exception as e:
            self.logger.error("Error getting bookings by ids %s: %s", ids, str(e))
            raise RepositoryException(f"Failed to retrieve Booking list: {str(e)}")

    def get_with_pricing_context(self, booking_id: str) -> Optional[Booking]:
        """Return booking hydrated with relationships required for pricing calculations."""
        try:
            return cast(
                Optional[Booking],
                self.db.query(Booking)
                .options(
                    joinedload(Booking.student),
                    joinedload(Booking.instructor).joinedload(User.instructor_profile),
                    joinedload(Booking.instructor_service),
                )
                .filter(Booking.id == booking_id)
                .first(),
            )
        except Exception as exc:
            self.logger.error(
                "Error fetching booking %s with pricing context: %s", booking_id, str(exc)
            )
            raise RepositoryException("Failed to load booking pricing context")

    def get_booking_with_details(self, booking_id: str) -> Optional[Booking]:
        """Get a booking with all relationships loaded."""
        try:
            booking: Booking | None = (
                self.db.query(Booking)
                .options(
                    joinedload(Booking.student),
                    joinedload(Booking.instructor),
                    joinedload(Booking.instructor_service),
                    joinedload(Booking.rescheduled_from),
                    joinedload(Booking.cancelled_by),
                    selectinload(Booking.payment_detail),
                    selectinload(Booking.no_show_detail),
                    selectinload(Booking.lock_detail),
                    selectinload(Booking.reschedule_detail),
                    selectinload(Booking.dispute),
                    selectinload(Booking.transfer),
                    selectinload(Booking.video_session),
                )
                .filter(Booking.id == booking_id)
                .first()
            )
            return booking
        except Exception as e:
            self.logger.error("Error getting booking details: %s", str(e))
            raise RepositoryException(f"Failed to get booking details: {str(e)}")

    def _apply_full_eager_loading(self, query: Query) -> Query:
        """Apply comprehensive eager loading for detailed booking views."""
        return query.options(
            joinedload(Booking.student),
            joinedload(Booking.instructor),
            joinedload(Booking.instructor_service),
            joinedload(Booking.rescheduled_from),
            joinedload(Booking.cancelled_by),
            selectinload(Booking.payment_detail),
            selectinload(Booking.no_show_detail),
            selectinload(Booking.lock_detail),
            selectinload(Booking.reschedule_detail),
            selectinload(Booking.dispute),
            selectinload(Booking.transfer),
            selectinload(Booking.video_session),
        )

    def get_booking_for_participant(self, booking_id: str, user_id: str) -> Optional[Booking]:
        """Get booking only if user is student or instructor on it."""
        try:
            query = self.db.query(Booking).filter(
                Booking.id == booking_id,
                or_(
                    Booking.student_id == user_id,
                    Booking.instructor_id == user_id,
                ),
            )
            query = self._apply_full_eager_loading(query)
            return cast(Optional[Booking], query.first())
        except Exception as e:
            self.logger.error("Error getting booking for participant: %s", str(e))
            raise RepositoryException(f"Failed to get booking for participant: {str(e)}")

    def get_booking_for_student(self, booking_id: str, student_id: str) -> Optional[Booking]:
        """Get booking only if user is the student on it."""
        try:
            query = self.db.query(Booking).filter(
                Booking.id == booking_id,
                Booking.student_id == student_id,
            )
            query = self._apply_full_eager_loading(query)
            return cast(Optional[Booking], query.first())
        except Exception as e:
            self.logger.error("Error getting booking for student: %s", str(e))
            raise RepositoryException(f"Failed to get booking for student: {str(e)}")

    def get_booking_for_instructor(self, booking_id: str, instructor_id: str) -> Optional[Booking]:
        """Get booking only if user is the instructor on it."""
        try:
            query = self.db.query(Booking).filter(
                Booking.id == booking_id,
                Booking.instructor_id == instructor_id,
            )
            query = self._apply_full_eager_loading(query)
            return cast(Optional[Booking], query.first())
        except Exception as e:
            self.logger.error("Error getting booking for instructor: %s", str(e))
            raise RepositoryException(f"Failed to get booking for instructor: {str(e)}")

    def get_booking_for_participant_for_update(
        self,
        booking_id: str,
        user_id: str,
        *,
        load_relationships: bool = True,
        populate_existing: bool = True,
        lock_scope_for_external_call: bool = False,
    ) -> Optional[Booking]:
        """Get booking with row-level lock, only if user is a participant."""
        try:
            if lock_scope_for_external_call:
                existing_savepoint = self._external_call_lock_savepoint
                if existing_savepoint is not None and getattr(
                    existing_savepoint, "is_active", True
                ):
                    existing_savepoint.rollback()
                self._external_call_lock_savepoint = self.db.begin_nested()

            query = (
                self.db.query(Booking)
                .filter(
                    Booking.id == booking_id,
                    or_(
                        Booking.student_id == user_id,
                        Booking.instructor_id == user_id,
                    ),
                )
                .with_for_update(of=Booking)
            )
            if load_relationships:
                query = self._apply_eager_loading(query)
            if populate_existing:
                query = query.populate_existing()
            return cast(Optional[Booking], query.first())
        except Exception as e:
            if lock_scope_for_external_call:
                savepoint = self._external_call_lock_savepoint
                self._external_call_lock_savepoint = None
                if savepoint is not None and getattr(savepoint, "is_active", True):
                    savepoint.rollback()
            self.logger.error("Error getting booking for participant (for update): %s", str(e))
            raise RepositoryException(
                f"Failed to get booking for participant (for update): {str(e)}"
            )

    def get_by_id_for_update(
        self,
        booking_id: str,
        *,
        load_relationships: bool = True,
        populate_existing: bool = True,
    ) -> Optional[Booking]:
        """Get a booking by ID with row-level lock (SELECT FOR UPDATE)."""
        try:
            query = (
                self.db.query(Booking).filter(Booking.id == booking_id).with_for_update(of=Booking)
            )
            if load_relationships:
                query = self._apply_eager_loading(query)
            if populate_existing:
                query = query.populate_existing()
            return cast(Optional[Booking], query.first())
        except Exception as e:
            self.logger.error("Error getting booking by id (for update): %s", str(e))
            raise RepositoryException(f"Failed to get booking by id (for update): {str(e)}")

    def filter_owned_booking_ids(self, booking_ids: List[str], student_id: str) -> List[str]:
        """Return subset of booking_ids that are owned by the given student."""
        if not booking_ids:
            return []
        try:
            rows = (
                self.db.query(Booking.id)
                .filter(Booking.id.in_(booking_ids), Booking.student_id == student_id)
                .all()
            )
            return [row[0] if isinstance(row, tuple) else row.id for row in rows]
        except Exception as e:
            self.logger.error("Error filtering owned booking ids: %s", e)
            return []
