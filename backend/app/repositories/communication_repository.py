"""Repository for admin communication targeting and history queries."""

from __future__ import annotations

from datetime import datetime
from typing import Iterable, Sequence

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.address import InstructorServiceArea, RegionBoundary
from app.models.booking import Booking
from app.models.event_outbox import NotificationDelivery
from app.models.instructor import InstructorProfile
from app.models.notification import PushSubscription
from app.models.rbac import Role, UserRole
from app.models.service_catalog import InstructorService, ServiceCatalog, ServiceCategory
from app.models.user import User


class CommunicationRepository:
    """Data access for admin communication workflows."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def list_users_by_ids(self, user_ids: Sequence[str]) -> list[User]:
        if not user_ids:
            return []
        return list(self.db.query(User).filter(User.id.in_(list(user_ids))).all())

    def list_user_ids_by_role(self, role_name: str) -> list[str]:
        rows = (
            self.db.query(User.id)
            .join(UserRole, UserRole.user_id == User.id)
            .join(Role, Role.id == UserRole.role_id)
            .filter(Role.name == role_name)
            .all()
        )
        return [row[0] for row in rows]

    def list_active_user_ids(self, since: datetime, role_name: str) -> list[str]:
        if role_name == "student":
            query = self.db.query(Booking.student_id)
            query = query.join(User, User.id == Booking.student_id)
        else:
            query = self.db.query(Booking.instructor_id)
            query = query.join(User, User.id == Booking.instructor_id)
        query = (
            query.join(UserRole, UserRole.user_id == User.id)
            .join(Role, Role.id == UserRole.role_id)
            .filter(Role.name == role_name)
            .filter(Booking.created_at >= since)
            .distinct()
        )
        rows = query.all()
        return [row[0] for row in rows]

    def list_founding_instructor_ids(self) -> list[str]:
        rows = (
            self.db.query(User.id)
            .join(InstructorProfile, InstructorProfile.user_id == User.id)
            .filter(InstructorProfile.is_founding_instructor.is_(True))
            .all()
        )
        return [row[0] for row in rows]

    def list_push_subscription_user_ids(self, user_ids: Sequence[str]) -> set[str]:
        if not user_ids:
            return set()
        rows = (
            self.db.query(PushSubscription.user_id)
            .filter(PushSubscription.user_id.in_(list(user_ids)))
            .distinct()
            .all()
        )
        return {row[0] for row in rows}

    def resolve_category_ids(self, categories: Iterable[str]) -> list[str]:
        values = [value for value in categories if value]
        if not values:
            return []
        conditions = [
            ServiceCategory.id.in_(values),
            ServiceCategory.slug.in_(values),
            *[ServiceCategory.name.ilike(f"%{value}%") for value in values],
        ]
        rows = self.db.query(ServiceCategory.id).filter(or_(*conditions)).all()
        return [row[0] for row in rows]

    def resolve_region_ids(self, locations: Iterable[str]) -> list[str]:
        values = [value for value in locations if value]
        if not values:
            return []
        conditions = [
            RegionBoundary.id.in_(values),
            *[RegionBoundary.region_name.ilike(f"%{value}%") for value in values],
            *[RegionBoundary.parent_region.ilike(f"%{value}%") for value in values],
            *[RegionBoundary.region_code.ilike(f"%{value}%") for value in values],
        ]
        rows = self.db.query(RegionBoundary.id).filter(or_(*conditions)).all()
        return [row[0] for row in rows]

    def list_instructor_ids_by_categories(self, category_ids: Sequence[str]) -> list[str]:
        if not category_ids:
            return []
        rows = (
            self.db.query(User.id)
            .join(InstructorProfile, InstructorProfile.user_id == User.id)
            .join(
                InstructorService, InstructorService.instructor_profile_id == InstructorProfile.id
            )
            .join(ServiceCatalog, ServiceCatalog.id == InstructorService.service_catalog_id)
            .filter(ServiceCatalog.category_id.in_(list(category_ids)))
            .distinct()
            .all()
        )
        return [row[0] for row in rows]

    def list_student_ids_by_categories(self, category_ids: Sequence[str]) -> list[str]:
        if not category_ids:
            return []
        rows = (
            self.db.query(Booking.student_id)
            .join(InstructorService, InstructorService.id == Booking.instructor_service_id)
            .join(ServiceCatalog, ServiceCatalog.id == InstructorService.service_catalog_id)
            .filter(ServiceCatalog.category_id.in_(list(category_ids)))
            .distinct()
            .all()
        )
        return [row[0] for row in rows]

    def list_instructor_ids_by_regions(self, region_ids: Sequence[str]) -> list[str]:
        if not region_ids:
            return []
        rows = (
            self.db.query(User.id)
            .join(InstructorServiceArea, InstructorServiceArea.instructor_id == User.id)
            .filter(InstructorServiceArea.neighborhood_id.in_(list(region_ids)))
            .distinct()
            .all()
        )
        return [row[0] for row in rows]

    def list_student_ids_by_zip(self, zip_codes: Sequence[str]) -> list[str]:
        if not zip_codes:
            return []
        rows = self.db.query(User.id).filter(User.zip_code.in_(list(zip_codes))).distinct().all()
        return [row[0] for row in rows]

    def list_notification_deliveries(
        self,
        *,
        event_types: Sequence[str] | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 100,
    ) -> list[NotificationDelivery]:
        query = self.db.query(NotificationDelivery)
        if event_types:
            query = query.filter(NotificationDelivery.event_type.in_(list(event_types)))
        if start is not None:
            query = query.filter(NotificationDelivery.delivered_at >= start)
        if end is not None:
            query = query.filter(NotificationDelivery.delivered_at <= end)
        query = query.order_by(NotificationDelivery.delivered_at.desc())
        if limit:
            query = query.limit(limit)
        return list(query.all())

    def count_notification_deliveries(self, event_type: str) -> int:
        return int(
            self.db.query(func.count(NotificationDelivery.id))
            .filter(NotificationDelivery.event_type == event_type)
            .scalar()
            or 0
        )
