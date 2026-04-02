"""Student/instructor booking lists, pagination, and service catalog queries."""

from datetime import date, datetime, timezone
from typing import Dict, List, Optional, Tuple, cast

from sqlalchemy import and_, or_
from sqlalchemy.orm import Query, joinedload, selectinload

from ...core.exceptions import RepositoryException
from ...models.booking import Booking, BookingStatus
from ...models.service_catalog import InstructorService
from .mixin_base import BookingRepositoryMixinBase


class BookingListQueryMixin(BookingRepositoryMixinBase):
    """Student/instructor booking lists, pagination, and service catalog queries."""

    def _booking_list_query(self) -> Query:
        """Base booking list query with the related objects needed by API responses."""
        return self.db.query(Booking).options(
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

    def _build_student_bookings_query(
        self,
        student_id: str,
        status: Optional[BookingStatus] = None,
        upcoming_only: bool = False,
        exclude_future_confirmed: bool = False,
        include_past_confirmed: bool = False,
    ) -> Query:
        """Build the filtered student-bookings query used by list endpoints."""
        query = self._booking_list_query().filter(Booking.student_id == student_id)

        status_filter = status
        if include_past_confirmed and status == BookingStatus.COMPLETED:
            status_filter = None

        if status_filter:
            query = query.filter(Booking.status == status_filter)

        if upcoming_only:
            user_now = self._get_user_now(student_id)
            now_utc = user_now.astimezone(timezone.utc)

            query = query.filter(
                Booking.booking_end_utc > now_utc,
                Booking.status == BookingStatus.CONFIRMED,
            )
        elif exclude_future_confirmed:
            user_now = self._get_user_now(student_id)
            now_utc = user_now.astimezone(timezone.utc)

            query = query.filter(
                or_(
                    Booking.booking_end_utc <= now_utc,
                    and_(
                        Booking.booking_end_utc > now_utc,
                        Booking.status.in_(
                            [
                                BookingStatus.CANCELLED,
                                BookingStatus.PAYMENT_FAILED,
                                BookingStatus.NO_SHOW,
                            ]
                        ),
                        Booking.cancellation_reason != "Rescheduled",
                    ),
                )
            )
        elif include_past_confirmed:
            user_now = self._get_user_now(student_id)
            now_utc = user_now.astimezone(timezone.utc)

            query = query.filter(
                Booking.booking_start_utc <= now_utc,
                Booking.status == BookingStatus.COMPLETED,
            )

        if upcoming_only:
            return query.order_by(Booking.booking_date.asc(), Booking.start_time.asc())
        return query.order_by(Booking.booking_date.desc(), Booking.start_time.desc())

    def _build_instructor_bookings_query(
        self,
        instructor_id: str,
        status: Optional[BookingStatus] = None,
        upcoming_only: bool = False,
        exclude_future_confirmed: bool = False,
        include_past_confirmed: bool = False,
        ended_before_utc: Optional[datetime] = None,
    ) -> Query:
        """Build the filtered instructor-bookings query used by list endpoints."""
        query = self._booking_list_query().filter(Booking.instructor_id == instructor_id)
        query = query.filter(Booking.status != BookingStatus.PAYMENT_FAILED)

        include_past_confirmed_mode = include_past_confirmed and status == BookingStatus.COMPLETED
        status_filter = None if include_past_confirmed_mode else status

        if include_past_confirmed_mode:
            self.logger.debug(
                "Including chronologically past confirmed lessons for instructor",
                extra={
                    "instructor_id": instructor_id,
                    "upcoming_only": upcoming_only,
                    "exclude_future_confirmed": exclude_future_confirmed,
                    "status": getattr(status, "value", status),
                },
            )

        if upcoming_only:
            user_now = self._get_user_now(instructor_id)
            now_utc = user_now.astimezone(timezone.utc)

            query = query.filter(
                Booking.booking_end_utc > now_utc,
                Booking.status == BookingStatus.CONFIRMED,
            )
        elif exclude_future_confirmed:
            user_now = self._get_user_now(instructor_id)
            now_utc = user_now.astimezone(timezone.utc)

            query = query.filter(
                or_(
                    Booking.booking_end_utc <= now_utc,
                    and_(
                        Booking.booking_end_utc > now_utc,
                        Booking.status.in_([BookingStatus.CANCELLED, BookingStatus.NO_SHOW]),
                    ),
                )
            )
        elif include_past_confirmed_mode:
            user_now = self._get_user_now(instructor_id)
            now_utc = user_now.astimezone(timezone.utc)

            query = query.filter(
                Booking.booking_end_utc <= now_utc,
                Booking.status.in_(
                    [
                        BookingStatus.CONFIRMED,
                        BookingStatus.COMPLETED,
                        BookingStatus.NO_SHOW,
                    ]
                ),
            )

        if ended_before_utc is not None:
            query = query.filter(
                Booking.booking_end_utc.isnot(None), Booking.booking_end_utc <= ended_before_utc
            )

        if status_filter:
            query = query.filter(Booking.status == status_filter)

        if upcoming_only:
            return query.order_by(Booking.booking_date.asc(), Booking.start_time.asc())
        return query.order_by(Booking.booking_date.desc(), Booking.start_time.desc())

    def get_student_bookings(
        self,
        student_id: str,
        status: Optional[BookingStatus] = None,
        upcoming_only: bool = False,
        exclude_future_confirmed: bool = False,
        include_past_confirmed: bool = False,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> List[Booking]:
        """Get bookings for a specific student with advanced filtering."""
        try:
            query = self._build_student_bookings_query(
                student_id=student_id,
                status=status,
                upcoming_only=upcoming_only,
                exclude_future_confirmed=exclude_future_confirmed,
                include_past_confirmed=include_past_confirmed,
            )

            if offset:
                query = query.offset(offset)
            if limit:
                query = query.limit(limit)

            return cast(List[Booking], query.all())

        except Exception as e:
            self.logger.error("Error getting student bookings: %s", str(e))
            raise RepositoryException(f"Failed to get student bookings: {str(e)}")

    def get_student_bookings_page(
        self,
        student_id: str,
        *,
        status: Optional[BookingStatus] = None,
        upcoming_only: bool = False,
        exclude_future_confirmed: bool = False,
        include_past_confirmed: bool = False,
        page: int = 1,
        per_page: int = 20,
    ) -> Tuple[List[Booking], int]:
        """Return one page of student bookings plus the filtered total count."""
        try:
            offset = max(0, (page - 1) * per_page)
            query = self._build_student_bookings_query(
                student_id=student_id,
                status=status,
                upcoming_only=upcoming_only,
                exclude_future_confirmed=exclude_future_confirmed,
                include_past_confirmed=include_past_confirmed,
            )
            total = int(query.order_by(None).count())
            items = cast(List[Booking], query.offset(offset).limit(per_page).all())
            return items, total
        except Exception as exc:
            self.logger.error("Error paginating student bookings: %s", str(exc))
            raise RepositoryException(f"Failed to paginate student bookings: {str(exc)}")

    def get_instructor_bookings(
        self,
        instructor_id: str,
        status: Optional[BookingStatus] = None,
        upcoming_only: bool = False,
        exclude_future_confirmed: bool = False,
        include_past_confirmed: bool = False,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        ended_before_utc: Optional[datetime] = None,
    ) -> List[Booking]:
        """Get bookings for a specific instructor with advanced filtering."""
        try:
            query = self._build_instructor_bookings_query(
                instructor_id=instructor_id,
                status=status,
                upcoming_only=upcoming_only,
                exclude_future_confirmed=exclude_future_confirmed,
                include_past_confirmed=include_past_confirmed,
                ended_before_utc=ended_before_utc,
            )
            if offset:
                query = query.offset(offset)
            if limit:
                query = query.limit(limit)

            return cast(List[Booking], query.all())

        except Exception as e:
            self.logger.error("Error getting instructor bookings: %s", str(e))
            raise RepositoryException(f"Failed to get instructor bookings: {str(e)}")

    def get_instructor_bookings_page(
        self,
        instructor_id: str,
        *,
        status: Optional[BookingStatus] = None,
        upcoming_only: bool = False,
        exclude_future_confirmed: bool = False,
        include_past_confirmed: bool = False,
        page: int = 1,
        per_page: int = 20,
        ended_before_utc: Optional[datetime] = None,
    ) -> Tuple[List[Booking], int]:
        """Return one page of instructor bookings plus the filtered total count."""
        try:
            offset = max(0, (page - 1) * per_page)
            query = self._build_instructor_bookings_query(
                instructor_id=instructor_id,
                status=status,
                upcoming_only=upcoming_only,
                exclude_future_confirmed=exclude_future_confirmed,
                include_past_confirmed=include_past_confirmed,
                ended_before_utc=ended_before_utc,
            )
            total = int(query.order_by(None).count())
            items = cast(List[Booking], query.offset(offset).limit(per_page).all())
            return items, total
        except Exception as exc:
            self.logger.error("Error paginating instructor bookings: %s", str(exc))
            raise RepositoryException(f"Failed to paginate instructor bookings: {str(exc)}")

    def get_instructor_future_bookings(
        self,
        instructor_id: str,
        from_date: Optional[date] = None,
        exclude_cancelled: bool = True,
    ) -> List[Booking]:
        """Get all future bookings for an instructor, excluding cancelled ones by default."""
        try:
            if from_date is None:
                from_date = self._get_user_today(instructor_id)

            query = self.db.query(Booking).filter(
                Booking.instructor_id == instructor_id, Booking.booking_date >= from_date
            )

            if exclude_cancelled:
                query = query.filter(
                    Booking.status.notin_([BookingStatus.CANCELLED, BookingStatus.PAYMENT_FAILED])
                )

            return cast(
                List[Booking], query.order_by(Booking.booking_date, Booking.start_time).all()
            )

        except Exception as e:
            self.logger.error("Error getting instructor future bookings: %s", str(e))
            raise RepositoryException(f"Failed to get future bookings: {str(e)}")

    def get_bookings_for_service_catalog(
        self,
        service_catalog_id: str,
        from_date: date,
        to_date: Optional[date] = None,
    ) -> List[Booking]:
        """Get all bookings for a specific service catalog type within a date range."""
        try:
            query = (
                self.db.query(Booking)
                .join(InstructorService, Booking.instructor_service_id == InstructorService.id)
                .filter(
                    InstructorService.service_catalog_id == service_catalog_id,
                    Booking.booking_date >= from_date,
                )
            )

            if to_date:
                query = query.filter(Booking.booking_date <= to_date)

            return cast(List[Booking], query.all())

        except Exception as e:
            self.logger.error("Error getting bookings for service catalog: %s", str(e))
            raise RepositoryException(f"Failed to get service catalog bookings: {str(e)}")

    def get_all_bookings_by_service_catalog(
        self,
        from_date: date,
        to_date: Optional[date] = None,
    ) -> Dict[str, List[Booking]]:
        """Get all bookings grouped by service_catalog_id in a single query."""
        try:
            from collections import defaultdict

            query = (
                self.db.query(Booking, InstructorService.service_catalog_id)
                .join(InstructorService, Booking.instructor_service_id == InstructorService.id)
                .filter(Booking.booking_date >= from_date)
            )

            if to_date:
                query = query.filter(Booking.booking_date <= to_date)

            results = query.all()

            grouped: Dict[str, List[Booking]] = defaultdict(list)
            for booking, service_catalog_id in results:
                grouped[str(service_catalog_id)].append(booking)

            return dict(grouped)

        except Exception as e:
            self.logger.error("Error getting all bookings by service catalog: %s", str(e))
            raise RepositoryException(f"Failed to get bookings by service catalog: {str(e)}")
