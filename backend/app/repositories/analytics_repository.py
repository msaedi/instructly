"""Analytics repository for platform-level aggregations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import logging
from typing import Iterable, Optional, Sequence

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.address import InstructorServiceArea, RegionBoundary
from app.models.availability_day import AvailabilityDay
from app.models.booking import Booking
from app.models.instructor import InstructorProfile
from app.models.payment import PaymentEvent
from app.models.rbac import Role, UserRole
from app.models.review import Review, ReviewResponse, ReviewStatus
from app.models.search_event import SearchEvent
from app.models.search_interaction import SearchInteraction
from app.models.service_catalog import InstructorService, ServiceCatalog, ServiceCategory
from app.models.subcategory import ServiceSubcategory
from app.models.user import User


@dataclass
class CategoryBookingRow:
    booking_id: str
    category_id: str
    category_name: str
    status: str
    total_price: object
    instructor_payout_amount: Optional[int]
    student_id: str
    instructor_id: str


class AnalyticsRepository:
    """Repository for analytics-specific queries."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.logger = logging.getLogger(__name__)

    def list_bookings_by_start(
        self,
        *,
        start: datetime,
        end: datetime,
        statuses: Optional[Sequence[str]] = None,
        instructor_ids: Optional[Sequence[str]] = None,
    ) -> list[Booking]:
        query = self.db.query(Booking).filter(
            Booking.booking_start_utc >= start,
            Booking.booking_start_utc <= end,
        )
        if statuses:
            query = query.filter(Booking.status.in_(list(statuses)))
        if instructor_ids:
            query = query.filter(Booking.instructor_id.in_(list(instructor_ids)))
        return list(query.all())

    def list_bookings_by_created(
        self,
        *,
        start: datetime,
        end: datetime,
        statuses: Optional[Sequence[str]] = None,
        instructor_ids: Optional[Sequence[str]] = None,
    ) -> list[Booking]:
        query = self.db.query(Booking).filter(
            Booking.created_at >= start,
            Booking.created_at <= end,
        )
        if statuses:
            query = query.filter(Booking.status.in_(list(statuses)))
        if instructor_ids:
            query = query.filter(Booking.instructor_id.in_(list(instructor_ids)))
        return list(query.all())

    def count_bookings(
        self,
        *,
        start: datetime,
        end: datetime,
        date_field: str,
        statuses: Optional[Sequence[str]] = None,
        instructor_ids: Optional[Sequence[str]] = None,
        service_catalog_ids: Optional[Sequence[str]] = None,
    ) -> int:
        query = self.db.query(func.count(Booking.id))
        if date_field == "created_at":
            query = query.filter(Booking.created_at >= start, Booking.created_at <= end)
        else:
            query = query.filter(
                Booking.booking_start_utc >= start, Booking.booking_start_utc <= end
            )
        if statuses:
            query = query.filter(Booking.status.in_(list(statuses)))
        if instructor_ids:
            query = query.filter(Booking.instructor_id.in_(list(instructor_ids)))
        if service_catalog_ids:
            query = query.join(
                InstructorService, Booking.instructor_service_id == InstructorService.id
            ).filter(InstructorService.service_catalog_id.in_(list(service_catalog_ids)))
        return int(query.scalar() or 0)

    def sum_total_price(
        self,
        *,
        start: datetime,
        end: datetime,
        date_field: str,
        statuses: Optional[Sequence[str]] = None,
        instructor_ids: Optional[Sequence[str]] = None,
        service_catalog_ids: Optional[Sequence[str]] = None,
    ) -> object:
        query = self.db.query(func.coalesce(func.sum(Booking.total_price), 0))
        if date_field == "created_at":
            query = query.filter(Booking.created_at >= start, Booking.created_at <= end)
        else:
            query = query.filter(
                Booking.booking_start_utc >= start, Booking.booking_start_utc <= end
            )
        if statuses:
            query = query.filter(Booking.status.in_(list(statuses)))
        if instructor_ids:
            query = query.filter(Booking.instructor_id.in_(list(instructor_ids)))
        if service_catalog_ids:
            query = query.join(
                InstructorService, Booking.instructor_service_id == InstructorService.id
            ).filter(InstructorService.service_catalog_id.in_(list(service_catalog_ids)))
        return query.scalar() or 0

    def sum_instructor_payout_cents(
        self,
        *,
        start: datetime,
        end: datetime,
        date_field: str,
        statuses: Optional[Sequence[str]] = None,
        instructor_ids: Optional[Sequence[str]] = None,
    ) -> int:
        query = self.db.query(func.coalesce(func.sum(Booking.instructor_payout_amount), 0))
        if date_field == "created_at":
            query = query.filter(Booking.created_at >= start, Booking.created_at <= end)
        else:
            query = query.filter(
                Booking.booking_start_utc >= start, Booking.booking_start_utc <= end
            )
        if statuses:
            query = query.filter(Booking.status.in_(list(statuses)))
        if instructor_ids:
            query = query.filter(Booking.instructor_id.in_(list(instructor_ids)))
        return int(query.scalar() or 0)

    def sum_booking_duration_minutes(
        self,
        *,
        start: datetime,
        end: datetime,
        statuses: Optional[Sequence[str]] = None,
        instructor_ids: Optional[Sequence[str]] = None,
    ) -> int:
        query = self.db.query(func.coalesce(func.sum(Booking.duration_minutes), 0))
        query = query.filter(Booking.booking_start_utc >= start, Booking.booking_start_utc <= end)
        if statuses:
            query = query.filter(Booking.status.in_(list(statuses)))
        if instructor_ids:
            query = query.filter(Booking.instructor_id.in_(list(instructor_ids)))
        return int(query.scalar() or 0)

    def list_category_booking_rows(
        self,
        *,
        start: datetime,
        end: datetime,
        statuses: Optional[Sequence[str]] = None,
    ) -> list[CategoryBookingRow]:
        query = (
            self.db.query(
                Booking.id,
                ServiceCategory.id,
                ServiceCategory.name,
                Booking.status,
                Booking.total_price,
                Booking.instructor_payout_amount,
                Booking.student_id,
                Booking.instructor_id,
            )
            .join(InstructorService, Booking.instructor_service_id == InstructorService.id)
            .join(ServiceCatalog, InstructorService.service_catalog_id == ServiceCatalog.id)
            .join(ServiceSubcategory, ServiceCatalog.subcategory_id == ServiceSubcategory.id)
            .join(ServiceCategory, ServiceSubcategory.category_id == ServiceCategory.id)
            .filter(Booking.booking_start_utc >= start, Booking.booking_start_utc <= end)
        )
        if statuses:
            query = query.filter(Booking.status.in_(list(statuses)))
        return [
            CategoryBookingRow(
                booking_id=row[0],
                category_id=row[1],
                category_name=row[2],
                status=row[3],
                total_price=row[4],
                instructor_payout_amount=row[5],
                student_id=row[6],
                instructor_id=row[7],
            )
            for row in query.all()
        ]

    def resolve_category_ids(self, category: Optional[str]) -> list[str]:
        if not category:
            return []
        query = self.db.query(ServiceCategory.id).filter(
            or_(
                ServiceCategory.id == category,
                ServiceCategory.name.ilike(f"%{category}%"),
            )
        )
        return [row[0] for row in query.all()]

    def resolve_region_ids(self, location: Optional[str]) -> list[str]:
        if not location:
            return []
        query = self.db.query(RegionBoundary.id).filter(
            or_(
                RegionBoundary.region_name.ilike(f"%{location}%"),
                RegionBoundary.parent_region.ilike(f"%{location}%"),
                RegionBoundary.region_code.ilike(f"%{location}%"),
            )
        )
        return [row[0] for row in query.all()]

    def list_active_instructor_ids(
        self,
        *,
        category_ids: Optional[Sequence[str]] = None,
        region_ids: Optional[Sequence[str]] = None,
    ) -> list[str]:
        query = (
            self.db.query(User.id)
            .join(InstructorProfile, InstructorProfile.user_id == User.id)
            .join(UserRole, UserRole.user_id == User.id)
            .join(Role, Role.id == UserRole.role_id)
            .filter(
                Role.name == "instructor",
                User.account_status == "active",
                InstructorProfile.is_live.is_(True),
            )
        )
        if category_ids:
            query = query.join(
                InstructorService,
                InstructorService.instructor_profile_id == InstructorProfile.id,
            ).join(ServiceCatalog, InstructorService.service_catalog_id == ServiceCatalog.id)
            query = query.join(
                ServiceSubcategory, ServiceCatalog.subcategory_id == ServiceSubcategory.id
            )
            query = query.filter(ServiceSubcategory.category_id.in_(list(category_ids)))
        if region_ids:
            query = query.join(
                InstructorServiceArea, InstructorServiceArea.instructor_id == User.id
            ).filter(InstructorServiceArea.neighborhood_id.in_(list(region_ids)))
        rows = query.distinct().all()
        return [row[0] for row in rows]

    def count_instructors_created(
        self,
        *,
        start: datetime,
        end: datetime,
        category_ids: Optional[Sequence[str]] = None,
        region_ids: Optional[Sequence[str]] = None,
    ) -> int:
        query = (
            self.db.query(func.count(User.id))
            .join(UserRole, UserRole.user_id == User.id)
            .join(Role, Role.id == UserRole.role_id)
            .filter(Role.name == "instructor", User.created_at >= start, User.created_at <= end)
        )
        if category_ids:
            query = query.join(InstructorProfile, InstructorProfile.user_id == User.id)
            query = query.join(
                InstructorService,
                InstructorService.instructor_profile_id == InstructorProfile.id,
            ).join(ServiceCatalog, InstructorService.service_catalog_id == ServiceCatalog.id)
            query = query.join(
                ServiceSubcategory, ServiceCatalog.subcategory_id == ServiceSubcategory.id
            )
            query = query.filter(ServiceSubcategory.category_id.in_(list(category_ids)))
        if region_ids:
            query = query.join(
                InstructorServiceArea, InstructorServiceArea.instructor_id == User.id
            ).filter(InstructorServiceArea.neighborhood_id.in_(list(region_ids)))
        return int(query.scalar() or 0)

    def count_instructors_churned(
        self,
        *,
        start: datetime,
        end: datetime,
        category_ids: Optional[Sequence[str]] = None,
        region_ids: Optional[Sequence[str]] = None,
    ) -> int:
        query = self.db.query(func.count(User.id)).join(UserRole, UserRole.user_id == User.id)
        query = query.join(Role, Role.id == UserRole.role_id)
        query = query.filter(
            Role.name == "instructor",
            User.account_status != "active",
            User.updated_at.isnot(None),
            User.updated_at >= start,
            User.updated_at <= end,
        )
        if category_ids:
            query = query.join(InstructorProfile, InstructorProfile.user_id == User.id)
            query = query.join(
                InstructorService,
                InstructorService.instructor_profile_id == InstructorProfile.id,
            ).join(ServiceCatalog, InstructorService.service_catalog_id == ServiceCatalog.id)
            query = query.join(
                ServiceSubcategory, ServiceCatalog.subcategory_id == ServiceSubcategory.id
            )
            query = query.filter(ServiceSubcategory.category_id.in_(list(category_ids)))
        if region_ids:
            query = query.join(
                InstructorServiceArea, InstructorServiceArea.instructor_id == User.id
            ).filter(InstructorServiceArea.neighborhood_id.in_(list(region_ids)))
        return int(query.scalar() or 0)

    def list_availability_days(
        self,
        *,
        instructor_ids: Sequence[str],
        start_date: date,
        end_date: date,
    ) -> list[AvailabilityDay]:
        if not instructor_ids:
            return []
        return list(
            self.db.query(AvailabilityDay)
            .filter(
                AvailabilityDay.instructor_id.in_(list(instructor_ids)),
                AvailabilityDay.day_date >= start_date,
                AvailabilityDay.day_date <= end_date,
            )
            .all()
        )

    def count_search_events(
        self,
        *,
        start: datetime,
        end: datetime,
    ) -> int:
        return int(
            self.db.query(func.count(SearchEvent.id))
            .filter(SearchEvent.searched_at >= start, SearchEvent.searched_at <= end)
            .scalar()
            or 0
        )

    def count_search_events_zero_results(
        self,
        *,
        start: datetime,
        end: datetime,
    ) -> int:
        return int(
            self.db.query(func.count(SearchEvent.id))
            .filter(
                SearchEvent.searched_at >= start,
                SearchEvent.searched_at <= end,
                SearchEvent.results_count == 0,
            )
            .scalar()
            or 0
        )

    def count_unique_searchers(
        self,
        *,
        start: datetime,
        end: datetime,
    ) -> int:
        user_count = int(
            self.db.query(func.count(func.distinct(SearchEvent.user_id)))
            .filter(SearchEvent.user_id.isnot(None))
            .filter(SearchEvent.searched_at >= start, SearchEvent.searched_at <= end)
            .scalar()
            or 0
        )
        guest_count = int(
            self.db.query(func.count(func.distinct(SearchEvent.guest_session_id)))
            .filter(SearchEvent.guest_session_id.isnot(None))
            .filter(SearchEvent.searched_at >= start, SearchEvent.searched_at <= end)
            .scalar()
            or 0
        )
        return user_count + guest_count

    def count_users_created(
        self,
        *,
        start: datetime,
        end: datetime,
        role_name: Optional[str] = None,
        phone_verified: Optional[bool] = None,
    ) -> int:
        query = self.db.query(func.count(User.id))
        if role_name:
            query = query.join(UserRole, UserRole.user_id == User.id)
            query = query.join(Role, Role.id == UserRole.role_id)
            query = query.filter(Role.name == role_name)
        query = query.filter(User.created_at >= start, User.created_at <= end)
        if phone_verified is not None:
            query = query.filter(User.phone_verified.is_(phone_verified))
        return int(query.scalar() or 0)

    def list_top_unfulfilled_searches(
        self,
        *,
        start: datetime,
        end: datetime,
        limit: int = 5,
    ) -> list[tuple[str, int]]:
        rows = (
            self.db.query(SearchEvent.search_query, func.count(SearchEvent.id).label("count"))
            .filter(
                SearchEvent.searched_at >= start,
                SearchEvent.searched_at <= end,
                SearchEvent.results_count == 0,
            )
            .group_by(SearchEvent.search_query)
            .order_by(func.count(SearchEvent.id).desc())
            .limit(limit)
            .all()
        )
        return [(row[0], int(row[1])) for row in rows]

    def count_search_interactions(
        self,
        *,
        start: datetime,
        end: datetime,
        interaction_type: str,
    ) -> int:
        return int(
            self.db.query(func.count(SearchInteraction.id))
            .filter(
                SearchInteraction.created_at >= start,
                SearchInteraction.created_at <= end,
                SearchInteraction.interaction_type == interaction_type,
            )
            .scalar()
            or 0
        )

    def count_payment_events(
        self,
        *,
        start: datetime,
        end: datetime,
        event_types: Sequence[str],
    ) -> int:
        return int(
            self.db.query(func.count(PaymentEvent.id))
            .filter(
                PaymentEvent.created_at >= start,
                PaymentEvent.created_at <= end,
                PaymentEvent.event_type.in_(list(event_types)),
            )
            .scalar()
            or 0
        )

    def avg_review_rating(self, *, start: datetime, end: datetime) -> float:
        avg_rating = (
            self.db.query(func.avg(Review.rating))
            .filter(
                Review.created_at >= start,
                Review.created_at <= end,
                Review.status == ReviewStatus.PUBLISHED,
            )
            .scalar()
        )
        return float(avg_rating or 0)

    def count_reviews(self, *, start: datetime, end: datetime) -> int:
        return int(
            self.db.query(func.count(Review.id))
            .filter(
                Review.created_at >= start,
                Review.created_at <= end,
                Review.status == ReviewStatus.PUBLISHED,
            )
            .scalar()
            or 0
        )

    def count_review_responses(self, *, start: datetime, end: datetime) -> int:
        return int(
            self.db.query(func.count(ReviewResponse.id))
            .join(Review, ReviewResponse.review_id == Review.id)
            .filter(
                Review.created_at >= start,
                Review.created_at <= end,
                Review.status == ReviewStatus.PUBLISHED,
            )
            .scalar()
            or 0
        )

    def count_no_show_bookings(self, *, start: datetime, end: datetime) -> int:
        return int(
            self.db.query(func.count(Booking.id))
            .filter(
                Booking.booking_start_utc >= start,
                Booking.booking_start_utc <= end,
                Booking.status == "NO_SHOW",
            )
            .scalar()
            or 0
        )

    def count_refunded_bookings(self, *, start: datetime, end: datetime) -> int:
        return int(
            self.db.query(func.count(Booking.id))
            .filter(
                Booking.booking_start_utc >= start,
                Booking.booking_start_utc <= end,
                or_(
                    Booking.refunded_to_card_amount.isnot(None),
                    Booking.student_credit_amount.isnot(None),
                ),
            )
            .scalar()
            or 0
        )

    def get_search_event_segment_counts(
        self,
        *,
        start: datetime,
        end: datetime,
        segment_by: str,
    ) -> dict[str, int]:
        if segment_by == "device":
            field = SearchEvent.device_type
        elif segment_by == "source":
            field = SearchEvent.referrer
        else:
            field = SearchEvent.search_type

        rows = (
            self.db.query(field, func.count(SearchEvent.id))
            .filter(SearchEvent.searched_at >= start, SearchEvent.searched_at <= end)
            .group_by(field)
            .all()
        )
        result: dict[str, int] = {}
        for value, count in rows:
            key = value or "unknown"
            result[str(key)] = int(count)
        return result

    def list_user_ids_by_role(self, role_name: str) -> list[str]:
        rows = (
            self.db.query(User.id)
            .join(UserRole, UserRole.user_id == User.id)
            .join(Role, Role.id == UserRole.role_id)
            .filter(Role.name == role_name)
            .all()
        )
        return [row[0] for row in rows]

    def list_user_ids_by_role_in_range(
        self,
        *,
        role_name: str,
        start: datetime,
        end: datetime,
    ) -> list[str]:
        rows = (
            self.db.query(User.id)
            .join(UserRole, UserRole.user_id == User.id)
            .join(Role, Role.id == UserRole.role_id)
            .filter(Role.name == role_name, User.created_at >= start, User.created_at <= end)
            .all()
        )
        return [row[0] for row in rows]

    def list_users_created_between(
        self, *, role_name: str, start: datetime, end: datetime
    ) -> list[User]:
        return list(
            self.db.query(User)
            .join(UserRole, UserRole.user_id == User.id)
            .join(Role, Role.id == UserRole.role_id)
            .filter(Role.name == role_name, User.created_at >= start, User.created_at <= end)
            .all()
        )

    def list_users_by_role(self, role_name: str) -> list[User]:
        return list(
            self.db.query(User)
            .join(UserRole, UserRole.user_id == User.id)
            .join(Role, Role.id == UserRole.role_id)
            .filter(Role.name == role_name)
            .all()
        )

    def list_user_ids_with_bookings(
        self,
        *,
        user_ids: Iterable[str],
        role: str,
        start: datetime,
        end: datetime,
    ) -> set[str]:
        if not user_ids:
            return set()
        query = self.db.query(Booking)
        if role == "student":
            query = query.filter(Booking.student_id.in_(list(user_ids)))
        else:
            query = query.filter(Booking.instructor_id.in_(list(user_ids)))
        rows = query.filter(
            Booking.booking_start_utc >= start, Booking.booking_start_utc <= end
        ).all()
        if role == "student":
            return {row.student_id for row in rows}
        return {row.instructor_id for row in rows}

    def count_instructors_for_category(self, category_id: str) -> int:
        return int(
            self.db.query(func.count(func.distinct(InstructorService.instructor_profile_id)))
            .join(ServiceCatalog, InstructorService.service_catalog_id == ServiceCatalog.id)
            .join(ServiceSubcategory, ServiceCatalog.subcategory_id == ServiceSubcategory.id)
            .filter(InstructorService.is_active.is_(True))
            .filter(ServiceSubcategory.category_id == category_id)
            .scalar()
            or 0
        )

    def count_students_for_category(
        self, *, start: datetime, end: datetime, category_id: str
    ) -> int:
        rows = (
            self.db.query(func.count(func.distinct(Booking.student_id)))
            .join(InstructorService, Booking.instructor_service_id == InstructorService.id)
            .join(ServiceCatalog, InstructorService.service_catalog_id == ServiceCatalog.id)
            .join(ServiceSubcategory, ServiceCatalog.subcategory_id == ServiceSubcategory.id)
            .filter(
                Booking.booking_start_utc >= start,
                Booking.booking_start_utc <= end,
                ServiceSubcategory.category_id == category_id,
            )
            .scalar()
            or 0
        )
        return int(rows)

    def list_availability_instructor_ids(self, category_ids: Optional[Sequence[str]]) -> list[str]:
        query = self.db.query(func.distinct(InstructorProfile.user_id))
        query = query.join(
            InstructorService,
            InstructorService.instructor_profile_id == InstructorProfile.id,
        )
        if category_ids:
            query = query.join(
                ServiceCatalog, InstructorService.service_catalog_id == ServiceCatalog.id
            ).join(ServiceSubcategory, ServiceCatalog.subcategory_id == ServiceSubcategory.id)
            query = query.filter(ServiceSubcategory.category_id.in_(list(category_ids)))
        return [row[0] for row in query.all()]
