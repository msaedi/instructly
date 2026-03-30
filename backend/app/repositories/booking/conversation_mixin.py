"""Booking queries for conversation and messaging context."""

from typing import Dict, List, Tuple, cast

from sqlalchemy import and_, or_
from sqlalchemy.orm import joinedload

from ...core.exceptions import RepositoryException
from ...models.booking import Booking, BookingStatus
from .mixin_base import BookingRepositoryMixinBase


class BookingConversationMixin(BookingRepositoryMixinBase):
    """Booking queries for conversation and messaging context."""

    def find_upcoming_for_pair(
        self,
        student_id: str,
        instructor_id: str,
        limit: int = 5,
    ) -> List[Booking]:
        """Find upcoming bookings for a student-instructor pair."""
        try:
            user_now = self._get_user_now(student_id)
            return cast(
                List[Booking],
                self.db.query(Booking)
                .options(joinedload(Booking.instructor_service))
                .filter(
                    Booking.student_id == student_id,
                    Booking.instructor_id == instructor_id,
                    Booking.status == BookingStatus.CONFIRMED,
                    or_(
                        Booking.booking_date > user_now.date(),
                        and_(
                            Booking.booking_date == user_now.date(),
                            Booking.start_time > user_now.time(),
                        ),
                    ),
                )
                .order_by(Booking.booking_date.asc(), Booking.start_time.asc())
                .limit(limit)
                .all(),
            )
        except Exception as e:
            self.logger.error("Error finding upcoming bookings for pair: %s", str(e))
            raise RepositoryException(f"Failed to find upcoming bookings for pair: {str(e)}")

    def batch_find_upcoming_for_pairs(
        self,
        pairs: List[Tuple[str, str]],
        user_id: str,
        limit_per_pair: int = 5,
    ) -> Dict[Tuple[str, str], List[Booking]]:
        """Find upcoming bookings for multiple student-instructor pairs in a single query."""
        if not pairs:
            return {}

        try:
            user_now = self._get_user_now(user_id)
            today = user_now.date()
            now_time = user_now.time()

            pair_conditions = [
                and_(Booking.student_id == student_id, Booking.instructor_id == instructor_id)
                for student_id, instructor_id in pairs
            ]

            all_bookings = cast(
                List[Booking],
                self.db.query(Booking)
                .options(joinedload(Booking.instructor_service))
                .filter(
                    or_(*pair_conditions),
                    Booking.status == BookingStatus.CONFIRMED,
                    or_(
                        Booking.booking_date > today,
                        and_(
                            Booking.booking_date == today,
                            Booking.start_time > now_time,
                        ),
                    ),
                )
                .order_by(Booking.booking_date.asc(), Booking.start_time.asc())
                .all(),
            )

            result: Dict[Tuple[str, str], List[Booking]] = {pair: [] for pair in pairs}
            for booking in all_bookings:
                pair_key = (booking.student_id, booking.instructor_id)
                if pair_key in result and len(result[pair_key]) < limit_per_pair:
                    result[pair_key].append(booking)

            return result
        except Exception as e:
            self.logger.error("Error in batch_find_upcoming_for_pairs: %s", str(e))
            return {pair: [] for pair in pairs}
