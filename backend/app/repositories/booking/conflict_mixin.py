"""Conflict detection, time-range queries, and booking opportunity search."""

from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple, cast

from sqlalchemy import or_
from sqlalchemy.orm import aliased

from ...core.exceptions import RepositoryException
from ...models.booking import Booking, BookingStatus
from ...models.booking_no_show import BookingNoShow
from ...models.booking_video_session import BookingVideoSession
from .mixin_base import BookingRepositoryMixinBase


class BookingConflictMixin(BookingRepositoryMixinBase):
    """Conflict detection, time-range queries, and booking opportunity search."""

    def get_video_no_show_candidates(
        self, sql_cutoff: datetime
    ) -> List[Tuple[Booking, Optional[BookingVideoSession]]]:
        """Find online CONFIRMED bookings whose scheduled end has passed."""
        try:
            no_show_alias = aliased(BookingNoShow)
            rows = (
                self.db.query(Booking, BookingVideoSession)
                .outerjoin(
                    BookingVideoSession,
                    BookingVideoSession.booking_id == Booking.id,
                )
                .outerjoin(no_show_alias, no_show_alias.booking_id == Booking.id)
                .filter(
                    Booking.status == BookingStatus.CONFIRMED.value,
                    Booking.location_type == "online",
                    Booking.booking_end_utc.isnot(None),
                    Booking.booking_end_utc <= sql_cutoff,
                    or_(
                        BookingVideoSession.id.is_(None),
                        BookingVideoSession.instructor_joined_at.is_(None),
                        BookingVideoSession.student_joined_at.is_(None),
                    ),
                    or_(
                        no_show_alias.no_show_reported_at.is_(None),
                        no_show_alias.id.is_(None),
                    ),
                )
                .order_by(Booking.booking_end_utc.asc())
                .all()
            )
            return cast(List[Tuple[Booking, Optional[BookingVideoSession]]], rows)
        except Exception as exc:
            self.logger.error("Failed to load video no-show candidates: %s", str(exc))
            raise RepositoryException(f"Failed to load video no-show candidates: {exc}")

    def get_bookings_by_time_range(
        self,
        instructor_id: str,
        booking_date: date,
        start_time: time,
        end_time: time,
        exclude_booking_id: Optional[str] = None,
    ) -> List[Booking]:
        """Get bookings within a time range for conflict checking."""
        try:
            query = self.db.query(Booking).filter(
                Booking.instructor_id == instructor_id,
                Booking.booking_date == booking_date,
                Booking.status.in_(
                    [
                        BookingStatus.PENDING,
                        BookingStatus.CONFIRMED,
                        BookingStatus.COMPLETED,
                    ]
                ),
                Booking.start_time < end_time,
                Booking.end_time > start_time,
            )

            if exclude_booking_id:
                query = query.filter(Booking.id != exclude_booking_id)

            return cast(List[Booking], query.all())

        except Exception as e:
            self.logger.error("Error getting bookings by time range: %s", str(e))
            raise RepositoryException(f"Failed to get bookings by time: {str(e)}")

    def check_time_conflict(
        self,
        instructor_id: str,
        booking_date: date,
        start_time: time,
        end_time: time,
        exclude_booking_id: Optional[str] = None,
    ) -> bool:
        """Check if a time range has any booking conflicts."""
        try:
            query = self.db.query(Booking).filter(
                Booking.instructor_id == instructor_id,
                Booking.booking_date == booking_date,
                Booking.status.in_(
                    [BookingStatus.CONFIRMED, BookingStatus.COMPLETED, BookingStatus.NO_SHOW]
                ),
                Booking.start_time < end_time,
                Booking.end_time > start_time,
            )

            if exclude_booking_id:
                query = query.filter(Booking.id != exclude_booking_id)

            return query.first() is not None

        except Exception as e:
            self.logger.error("Error checking time conflict: %s", str(e))
            raise RepositoryException(f"Failed to check conflict: {str(e)}")

    def check_student_time_conflict(
        self,
        student_id: str,
        booking_date: date,
        start_time: time,
        end_time: time,
        exclude_booking_id: Optional[str] = None,
    ) -> List[Booking]:
        """Check if a student has any conflicting bookings at the given time."""
        try:
            query = self.db.query(Booking).filter(
                Booking.student_id == student_id,
                Booking.booking_date == booking_date,
                Booking.status.in_(
                    [BookingStatus.CONFIRMED, BookingStatus.COMPLETED, BookingStatus.NO_SHOW]
                ),
                Booking.start_time < end_time,
                Booking.end_time > start_time,
            )

            if exclude_booking_id:
                query = query.filter(Booking.id != exclude_booking_id)

            return cast(List[Booking], query.all())

        except Exception as e:
            self.logger.error("Error checking student time conflict: %s", str(e))
            raise RepositoryException(f"Failed to check student conflict: {str(e)}")

    def get_instructor_bookings_for_date(
        self,
        instructor_id: str,
        target_date: date,
        status_filter: Optional[List[BookingStatus]] = None,
    ) -> List[Booking]:
        """Get all bookings for an instructor on a specific date."""
        try:
            query = self.db.query(Booking).filter(
                Booking.instructor_id == instructor_id,
                Booking.booking_date == target_date,
            )

            if status_filter:
                query = query.filter(Booking.status.in_(status_filter))

            return cast(List[Booking], query.order_by(Booking.start_time).all())

        except Exception as e:
            self.logger.error("Error getting bookings for date: %s", str(e))
            raise RepositoryException(f"Failed to get bookings: {str(e)}")

    def get_bookings_for_week(
        self,
        instructor_id: str,
        week_dates: List[date],
        status_filter: Optional[List[BookingStatus]] = None,
    ) -> List[Booking]:
        """Get all bookings for an instructor for a week."""
        try:
            query = self.db.query(Booking).filter(
                Booking.instructor_id == instructor_id,
                Booking.booking_date.in_(week_dates),
            )

            if status_filter:
                query = query.filter(Booking.status.in_(status_filter))

            return cast(
                List[Booking], query.order_by(Booking.booking_date, Booking.start_time).all()
            )

        except Exception as e:
            self.logger.error("Error getting bookings for week: %s", str(e))
            raise RepositoryException(f"Failed to get weekly bookings: {str(e)}")

    def get_distinct_booking_dates(self, instructor_id: str) -> List[date]:
        """Return distinct booking dates for the instructor."""
        try:
            rows = (
                self.db.query(Booking.booking_date)
                .filter(Booking.instructor_id == instructor_id, Booking.booking_date.isnot(None))
                .distinct()
                .all()
            )
            return [cast(date, row[0]) for row in rows if row[0] is not None]
        except Exception as exc:
            self.logger.error(
                "Error loading distinct booking dates for instructor %s: %s", instructor_id, exc
            )
            raise RepositoryException("Failed to load booking dates") from exc

    def find_booking_opportunities(
        self,
        available_slots: List[Dict[str, Any]],
        instructor_id: str,
        target_date: date,
        duration_minutes: int,
    ) -> List[Dict[str, Any]]:
        """Find booking opportunities within available time slots."""
        try:
            existing_bookings = self.get_bookings_by_time_range(
                instructor_id=instructor_id,
                booking_date=target_date,
                start_time=time(0, 0),
                end_time=time(23, 59),
            )

            opportunities: List[Dict[str, Any]] = []
            reference_date = date(2000, 1, 1)

            for slot in available_slots:
                slot_start = cast(time, slot["start_time"])
                slot_end = cast(time, slot["end_time"])
                current_time = slot_start

                while current_time < slot_end:
                    start_dt = datetime.combine(  # tz-pattern-ok: duration math only
                        reference_date, current_time, tzinfo=timezone.utc
                    )
                    end_dt = start_dt + timedelta(minutes=duration_minutes)
                    potential_end = end_dt.time()

                    if potential_end > slot_end:
                        break

                    has_conflict = False
                    for booking in existing_bookings:
                        if current_time < booking.end_time and potential_end > booking.start_time:
                            current_time = booking.end_time
                            has_conflict = True
                            break

                    if not has_conflict:
                        opportunities.append(
                            {
                                "start_time": current_time.isoformat(),
                                "end_time": potential_end.isoformat(),
                                "duration_minutes": duration_minutes,
                                "available": True,
                            }
                        )
                        current_time = potential_end

            return opportunities

        except Exception as e:
            self.logger.error("Error finding opportunities: %s", str(e))
            raise RepositoryException(f"Failed to find opportunities: {str(e)}")
