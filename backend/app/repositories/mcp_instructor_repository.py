# backend/app/repositories/mcp_instructor_repository.py
"""Repository for MCP instructor analytics and listings."""

from __future__ import annotations

from typing import Any, Iterable, cast

from sqlalchemy import and_, case, func, or_
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models.booking import Booking, BookingStatus
from app.models.instructor import InstructorProfile
from app.models.review import Review, ReviewStatus
from app.models.service_catalog import InstructorService, ServiceCatalog, ServiceCategory
from app.models.user import User


class MCPInstructorRepository:
    """Data access for MCP instructor operations."""

    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def _escape_like_pattern(value: str) -> str:
        """Escape special LIKE pattern characters to prevent pattern injection."""
        return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

    def list_instructors(
        self,
        *,
        status: str | None,
        is_founding: bool | None,
        service_slug: str | None,
        category_slug: str | None,
        limit: int,
        cursor: str | None,
    ) -> tuple[list[InstructorProfile], str | None]:
        """Return instructor profiles with filters and cursor pagination."""
        query = (
            self.db.query(InstructorProfile)
            .join(User, User.id == InstructorProfile.user_id)
            .options(joinedload(InstructorProfile.user))
        )

        status_filters = _build_status_filters(status)
        if status_filters:
            query = query.filter(and_(*status_filters))

        if is_founding is not None:
            query = query.filter(InstructorProfile.is_founding_instructor.is_(is_founding))

        if service_slug:
            service_exists = (
                self.db.query(InstructorService.id)
                .join(ServiceCatalog, ServiceCatalog.id == InstructorService.service_catalog_id)
                .filter(
                    InstructorService.instructor_profile_id == InstructorProfile.id,
                    InstructorService.is_active.is_(True),
                    ServiceCatalog.slug == service_slug,
                )
                .exists()
            )
            query = query.filter(service_exists)

        if category_slug:
            category_exists = (
                self.db.query(InstructorService.id)
                .join(ServiceCatalog, ServiceCatalog.id == InstructorService.service_catalog_id)
                .join(ServiceCategory, ServiceCategory.id == ServiceCatalog.category_id)
                .filter(
                    InstructorService.instructor_profile_id == InstructorProfile.id,
                    InstructorService.is_active.is_(True),
                    ServiceCategory.slug == category_slug,
                )
                .exists()
            )
            query = query.filter(category_exists)

        if cursor:
            query = query.filter(User.id > cursor)

        query = query.order_by(User.id.asc())

        rows = cast(list[InstructorProfile], query.limit(limit + 1).all())
        next_cursor = None
        if len(rows) > limit:
            rows = rows[:limit]
            next_cursor = rows[-1].user_id

        return rows, next_cursor

    def get_service_lists_for_profiles(
        self, profile_ids: Iterable[str]
    ) -> dict[str, dict[str, list[str]]]:
        """Return service and category names keyed by user_id."""
        ids = list(profile_ids)
        if not ids:
            return {}

        rows = (
            self.db.query(
                InstructorProfile.user_id.label("user_id"),
                ServiceCatalog.name.label("service_name"),
                ServiceCategory.name.label("category_name"),
            )
            .join(
                InstructorService, InstructorService.instructor_profile_id == InstructorProfile.id
            )
            .join(ServiceCatalog, ServiceCatalog.id == InstructorService.service_catalog_id)
            .join(ServiceCategory, ServiceCategory.id == ServiceCatalog.category_id)
            .filter(
                InstructorProfile.id.in_(ids),
                InstructorService.is_active.is_(True),
            )
            .all()
        )

        mapping: dict[str, dict[str, set[str]]] = {}
        for row in rows:
            entry = mapping.setdefault(row.user_id, {"services": set(), "categories": set()})
            if row.service_name:
                entry["services"].add(row.service_name)
            if row.category_name:
                entry["categories"].add(row.category_name)

        return {
            user_id: {
                "services": sorted(list(values["services"])),
                "categories": sorted(list(values["categories"])),
            }
            for user_id, values in mapping.items()
        }

    def get_booking_completed_counts(self, user_ids: Iterable[str]) -> dict[str, int]:
        """Return completed booking counts per instructor user_id."""
        ids = list(user_ids)
        if not ids:
            return {}

        rows = (
            self.db.query(Booking.instructor_id, func.count(Booking.id))
            .filter(
                Booking.instructor_id.in_(ids),
                Booking.status == BookingStatus.COMPLETED.value,
            )
            .group_by(Booking.instructor_id)
            .all()
        )
        return {row[0]: int(row[1] or 0) for row in rows}

    def get_review_stats(self, user_ids: Iterable[str]) -> dict[str, dict[str, float | int]]:
        """Return rating averages and counts per instructor user_id."""
        ids = list(user_ids)
        if not ids:
            return {}

        rows = (
            self.db.query(
                Review.instructor_id,
                func.avg(Review.rating),
                func.count(Review.id),
            )
            .filter(
                Review.instructor_id.in_(ids),
                Review.status == ReviewStatus.PUBLISHED,
            )
            .group_by(Review.instructor_id)
            .all()
        )

        stats: dict[str, dict[str, float | int]] = {}
        for instructor_id, avg_rating, count in rows:
            stats[instructor_id] = {
                "rating_avg": float(avg_rating) if avg_rating is not None else 0.0,
                "rating_count": int(count or 0),
            }
        return stats

    def get_service_coverage(
        self,
        *,
        status: str,
        group_by: str,
        top: int,
    ) -> dict[str, Any]:
        """Return coverage aggregation data by category or service."""
        status_filters = _build_status_filters(status)

        label_column = ServiceCategory.name if group_by == "category" else ServiceCatalog.name

        grouped = (
            self.db.query(
                label_column.label("label"),
                func.count(func.distinct(InstructorProfile.id)).label("count"),
            )
            .select_from(InstructorProfile)
            .join(
                InstructorService, InstructorService.instructor_profile_id == InstructorProfile.id
            )
            .join(ServiceCatalog, ServiceCatalog.id == InstructorService.service_catalog_id)
            .join(ServiceCategory, ServiceCategory.id == ServiceCatalog.category_id)
            .filter(InstructorService.is_active.is_(True))
        )

        if status_filters:
            grouped = grouped.filter(and_(*status_filters))

        grouped_rows = (
            grouped.group_by(label_column)
            .order_by(func.count(func.distinct(InstructorProfile.id)).desc())
            .limit(top)
            .all()
        )

        labels = [row.label for row in grouped_rows]
        values = [int(row.count or 0) for row in grouped_rows]

        total_instructors = (
            self.db.query(func.count(func.distinct(InstructorProfile.id)))
            .join(
                InstructorService, InstructorService.instructor_profile_id == InstructorProfile.id
            )
            .filter(InstructorService.is_active.is_(True))
        )
        if status_filters:
            total_instructors = total_instructors.filter(and_(*status_filters))
        total_instructors_value = int(total_instructors.scalar() or 0)

        total_services_offered = (
            self.db.query(func.count(InstructorService.id))
            .join(
                InstructorProfile, InstructorProfile.id == InstructorService.instructor_profile_id
            )
            .filter(InstructorService.is_active.is_(True))
        )
        if status_filters:
            total_services_offered = total_services_offered.filter(and_(*status_filters))
        total_services_value = int(total_services_offered.scalar() or 0)

        return {
            "labels": labels,
            "values": values,
            "total_instructors": total_instructors_value,
            "total_services_offered": total_services_value,
        }

    def get_instructor_by_identifier(self, identifier: str) -> InstructorProfile | None:
        """Lookup instructor profile by user_id, email, or name."""
        query = (
            self.db.query(InstructorProfile)
            .join(User, User.id == InstructorProfile.user_id)
            .options(
                joinedload(InstructorProfile.user),
                selectinload(InstructorProfile.instructor_services)
                .joinedload(InstructorService.catalog_entry)
                .joinedload(ServiceCatalog.category),
            )
        )

        identifier = (identifier or "").strip()
        if not identifier:
            return None

        if _looks_like_ulid(identifier):
            profile = query.filter(User.id == identifier).first()
            if profile:
                return cast(InstructorProfile, profile)
            profile = query.filter(InstructorProfile.id == identifier).first()
            if profile:
                return cast(InstructorProfile, profile)

        if "@" in identifier:
            lowered = identifier.lower()
            profile = query.filter(func.lower(User.email) == lowered).first()
            if profile:
                return cast(InstructorProfile, profile)

        parts = identifier.split()
        if len(parts) >= 2:
            first = parts[0].strip().lower()
            last = " ".join(parts[1:]).strip().lower()
            profile = query.filter(
                func.trim(func.lower(User.first_name)) == first,
                func.trim(func.lower(User.last_name)) == last,
            ).first()
            if profile:
                return cast(InstructorProfile, profile)

        needle = self._escape_like_pattern(identifier.lower())
        full_name = func.lower(func.trim(User.first_name) + " " + func.trim(User.last_name))
        return cast(
            InstructorProfile | None,
            query.filter(full_name.like(f"%{needle}%", escape="\\")).first(),
        )

    def get_booking_stats(self, user_id: str) -> dict[str, int]:
        """Return booking stats for a single instructor."""
        row = (
            self.db.query(
                func.count(case((Booking.status == BookingStatus.COMPLETED.value, 1))).label(
                    "completed"
                ),
                func.count(case((Booking.status == BookingStatus.CANCELLED.value, 1))).label(
                    "cancelled"
                ),
                func.count(case((Booking.status == BookingStatus.NO_SHOW.value, 1))).label(
                    "no_show"
                ),
            )
            .filter(Booking.instructor_id == user_id)
            .first()
        )
        if not row:
            return {"completed": 0, "cancelled": 0, "no_show": 0}
        return {
            "completed": int(row.completed or 0),
            "cancelled": int(row.cancelled or 0),
            "no_show": int(row.no_show or 0),
        }

    def get_review_stats_for_user(self, user_id: str) -> dict[str, float | int]:
        """Return review stats for a single instructor."""
        row = (
            self.db.query(func.avg(Review.rating), func.count(Review.id))
            .filter(
                Review.instructor_id == user_id,
                Review.status == ReviewStatus.PUBLISHED,
            )
            .first()
        )
        if not row:
            return {"rating_avg": 0.0, "rating_count": 0}
        return {
            "rating_avg": float(row[0]) if row[0] is not None else 0.0,
            "rating_count": int(row[1] or 0),
        }


def _build_status_filters(status: str | None) -> list[Any]:
    if not status:
        return []

    normalized = status.lower().strip()
    if normalized == "live":
        return [InstructorProfile.is_live.is_(True)]
    if normalized == "paused":
        return [
            InstructorProfile.is_live.is_(False),
            InstructorProfile.onboarding_completed_at.isnot(None),
        ]
    if normalized == "onboarding":
        return [
            InstructorProfile.is_live.is_(False),
            InstructorProfile.onboarding_completed_at.is_(None),
            or_(
                InstructorProfile.skills_configured.is_(True),
                InstructorProfile.bgc_status.isnot(None),
            ),
        ]
    if normalized == "registered":
        return [
            InstructorProfile.is_live.is_(False),
            InstructorProfile.onboarding_completed_at.is_(None),
            InstructorProfile.skills_configured.is_(False),
            InstructorProfile.bgc_status.is_(None),
        ]

    return []


def _looks_like_ulid(value: str) -> bool:
    if len(value) != 26:
        return False
    return value.isalnum()
