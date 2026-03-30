"""Booking counts, completion stats, and aggregation queries."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Sequence, Tuple, cast

from sqlalchemy import case, func, or_
from sqlalchemy.orm import selectinload

from ...core.enums import RoleName
from ...core.exceptions import RepositoryException
from ...models.booking import Booking, BookingStatus
from .mixin_base import BookingRepositoryMixinBase


class BookingStatsMixin(BookingRepositoryMixinBase):
    """Booking counts, completion stats, and aggregation queries."""

    def count_instructor_completed_in_window(self, instructor_id: str, window_days: int) -> int:
        """Return the number of completed bookings for an instructor in the activity window."""
        try:
            now = datetime.now(timezone.utc)
            window_start = now - timedelta(days=window_days)
            query = (
                self.db.query(func.count(Booking.id))
                .filter(Booking.instructor_id == instructor_id)
                .filter(Booking.status == BookingStatus.COMPLETED)
                .filter(Booking.completed_at.isnot(None))
                .filter(Booking.completed_at >= window_start)
            )
            result = query.scalar()
            return int(result or 0)
        except Exception as exc:
            self.logger.error(
                "Error counting instructor completed bookings in activity window: %s",
                str(exc),
            )
            raise RepositoryException("Failed to count instructor completions")

    def get_instructor_completion_stats_in_window(
        self,
        instructor_ids: Sequence[str],
        window_days: int,
    ) -> Dict[str, Tuple[int, Optional[datetime]]]:
        """Return completion counts-in-window and latest completion timestamps for instructors."""
        if not instructor_ids:
            return {}

        try:
            now = datetime.now(timezone.utc)
            window_start = now - timedelta(days=window_days)
            completion_count = func.coalesce(
                func.sum(case((Booking.completed_at >= window_start, 1), else_=0)),
                0,
            )
            rows = (
                self.db.query(
                    Booking.instructor_id,
                    completion_count.label("completed_count"),
                    func.max(Booking.completed_at).label("last_completed_at"),
                )
                .filter(Booking.instructor_id.in_(list(instructor_ids)))
                .filter(Booking.status == BookingStatus.COMPLETED)
                .filter(Booking.completed_at.isnot(None))
                .group_by(Booking.instructor_id)
                .all()
            )
            stats: Dict[str, Tuple[int, Optional[datetime]]] = {
                instructor_id: (0, None) for instructor_id in instructor_ids
            }
            for instructor_id, completed_count, last_completed_at in rows:
                stats[str(instructor_id)] = (
                    int(completed_count or 0),
                    cast(Optional[datetime], last_completed_at),
                )
            return stats
        except Exception as exc:
            self.logger.error(
                "Error fetching instructor completion stats in activity window: %s",
                str(exc),
            )
            raise RepositoryException("Failed to fetch instructor completion stats")

    def get_instructor_last_completed_at(self, instructor_id: str) -> Optional[datetime]:
        """Return the timestamp of the most recent completed booking for an instructor."""
        try:
            query = (
                self.db.query(func.max(Booking.completed_at))
                .filter(Booking.instructor_id == instructor_id)
                .filter(Booking.status == BookingStatus.COMPLETED)
            )
            result = cast(Optional[datetime], query.scalar())
            return result
        except Exception as exc:
            self.logger.error(
                "Error fetching instructor last completed booking timestamp: %s", str(exc)
            )
            raise RepositoryException("Failed to fetch last completion timestamp")

    def count_bookings_in_date_range(self, start: date, end: date) -> int:
        """Count bookings between two dates."""
        try:
            count = (
                self.db.query(func.count())
                .select_from(Booking)
                .filter(Booking.booking_date >= start, Booking.booking_date <= end)
                .scalar()
            )
            return int(count or 0)
        except Exception as e:
            self.logger.error("Error counting bookings in range: %s", str(e))
            raise RepositoryException(f"Failed to count bookings: {str(e)}")

    def sum_total_price_in_date_range(self, start: date, end: date) -> Decimal:
        """Sum total_price between two dates."""
        try:
            total = (
                self.db.query(func.coalesce(func.sum(Booking.total_price), 0))
                .filter(Booking.booking_date >= start, Booking.booking_date <= end)
                .scalar()
            )
            return cast(Decimal, total)
        except Exception as e:
            self.logger.error("Error summing total_price in range: %s", str(e))
            raise RepositoryException(f"Failed to sum booking totals: {str(e)}")

    def count_pending_completion(self, now: datetime) -> int:
        """Count confirmed bookings that should be completed or no-show."""
        try:
            count = (
                self.db.query(func.count())
                .select_from(Booking)
                .filter(
                    Booking.status == BookingStatus.CONFIRMED,
                    Booking.booking_end_utc <= now,
                )
                .scalar()
            )
            return int(count or 0)
        except Exception as e:
            self.logger.error("Error counting pending completion bookings: %s", str(e))
            raise RepositoryException(f"Failed to count pending completion bookings: {str(e)}")

    def get_instructor_bookings_for_stats(self, instructor_id: str) -> List[Booking]:
        """Get all bookings for an instructor for statistics calculation."""
        try:
            return cast(
                List[Booking],
                self.db.query(Booking).filter(Booking.instructor_id == instructor_id).all(),
            )
        except Exception as e:
            self.logger.error("Error getting instructor stats: %s", str(e))
            raise RepositoryException(f"Failed to get instructor statistics: {str(e)}")

    def count_bookings_by_status(self, user_id: str, user_role: str) -> Dict[str, int]:
        """Count bookings grouped by status for a user."""
        try:
            if user_role == RoleName.STUDENT:
                filter_condition = Booking.student_id == user_id
            elif user_role == RoleName.INSTRUCTOR:
                filter_condition = Booking.instructor_id == user_id
            else:
                return {status.value: 0 for status in BookingStatus}

            status_counts_query = (
                self.db.query(Booking.status, func.count(Booking.id).label("count"))
                .filter(filter_condition)
                .group_by(Booking.status)
                .all()
            )

            status_counts = {status.value: 0 for status in BookingStatus}
            for row in status_counts_query:
                if row.status:
                    status_counts[row.status] = row.count

            return status_counts

        except Exception as e:
            self.logger.error("Error counting bookings by status: %s", str(e))
            raise RepositoryException(f"Failed to count bookings by status: {str(e)}")

    def count_completed_lessons(
        self,
        *,
        instructor_user_id: str,
        window_start: datetime,
        window_end: datetime,
    ) -> int:
        """Count completed lessons for an instructor in a time window."""
        try:
            return int(
                self.db.query(func.count(Booking.id))
                .filter(
                    Booking.instructor_id == instructor_user_id,
                    Booking.status == BookingStatus.COMPLETED,
                    Booking.completed_at.isnot(None),
                    Booking.completed_at >= window_start,
                    Booking.completed_at <= window_end,
                )
                .scalar()
                or 0
            )
        except Exception as exc:
            self.logger.error(
                "Error counting completed lessons for %s: %s", instructor_user_id, exc
            )
            raise RepositoryException(f"Failed to count completed lessons: {exc}")

    def count_instructor_total_completed(self, instructor_user_id: str) -> int:
        """Return the lifetime completed lesson count for an instructor."""
        try:
            result = (
                self.db.query(func.count(Booking.id))
                .filter(
                    Booking.instructor_id == instructor_user_id,
                    Booking.status == BookingStatus.COMPLETED,
                    Booking.completed_at.isnot(None),
                )
                .scalar()
            )
            return int(result or 0)
        except Exception as exc:
            self.logger.error(
                "Failed counting completed lessons for instructor %s: %s",
                instructor_user_id,
                str(exc),
            )
            raise RepositoryException("Failed to count instructor completed lessons") from exc

    def count_student_completed_lifetime(self, student_id: str) -> int:
        """Return the lifetime completed session count for a student."""
        try:
            result = (
                self.db.query(func.count(Booking.id))
                .filter(
                    Booking.student_id == student_id,
                    Booking.status == BookingStatus.COMPLETED,
                    Booking.completed_at.isnot(None),
                )
                .scalar()
            )
            return int(result or 0)
        except Exception as exc:
            self.logger.error(
                "Failed counting completed bookings for student %s: %s",
                student_id,
                str(exc),
            )
            raise RepositoryException("Failed to count student completed lessons")

    def count_student_bookings(self, student_id: str) -> int:
        """Return total booking count for a student."""
        try:
            total = (
                self.db.query(func.count(Booking.id))
                .filter(Booking.student_id == student_id)
                .scalar()
            )
            return int(total or 0)
        except Exception as exc:
            self.logger.error("Failed counting bookings for student %s: %s", student_id, exc)
            raise RepositoryException("Failed to count student bookings") from exc

    def list_student_refund_bookings(self, student_id: str) -> List[Booking]:
        """Return bookings for a student that have refund or credit adjustments."""
        try:
            return cast(
                List[Booking],
                self.db.query(Booking)
                .options(selectinload(Booking.payment_detail))
                .filter(Booking.student_id == student_id)
                .filter(
                    or_(
                        Booking.refunded_to_card_amount.isnot(None),
                        Booking.student_credit_amount.isnot(None),
                    )
                )
                .order_by(Booking.updated_at.desc().nullslast(), Booking.id.desc())
                .all(),
            )
        except Exception as exc:
            self.logger.error("Failed loading refund bookings for student %s: %s", student_id, exc)
            raise RepositoryException("Failed to load refund history") from exc

    def get_student_most_recent_completed_at(self, student_id: str) -> Optional[datetime]:
        """Return the most recent completion timestamp for a student, if any."""
        try:
            record = (
                self.db.query(Booking.completed_at)
                .filter(
                    Booking.student_id == student_id,
                    Booking.status == BookingStatus.COMPLETED,
                    Booking.completed_at.isnot(None),
                )
                .order_by(Booking.completed_at.desc())
                .first()
            )
            if not record:
                return None
            completed_at = record[0] if isinstance(record, tuple) else record
            return cast(Optional[datetime], completed_at)
        except Exception as exc:
            self.logger.error(
                "Failed getting latest completion for student %s: %s",
                student_id,
                str(exc),
            )
            raise RepositoryException("Failed to fetch student completion timestamp")
