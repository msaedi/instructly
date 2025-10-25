# backend/app/repositories/badge_repository.py
"""
Repository utilities for student badges.

All functions in this module are database-only and free of business logic.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, TypedDict

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from ..models.badge import BadgeDefinition, BadgeProgress, StudentBadge
from ..models.booking import Booking, BookingStatus
from ..models.review import Review, ReviewStatus
from ..models.service_catalog import InstructorService, ServiceCatalog, ServiceCategory
from ..models.user import User


class StudentBadgeAwardRow(TypedDict, total=False):
    badge_id: str
    slug: str
    name: str
    description: Optional[str]
    criteria_config: Optional[dict]
    status: str
    awarded_at: Any
    confirmed_at: Optional[Any]
    progress_snapshot: Optional[dict]


class StudentBadgeProgressRow(TypedDict, total=False):
    badge_id: str
    slug: str
    name: str
    description: Optional[str]
    criteria_config: Optional[dict]
    current_progress: Optional[dict]
    last_updated: Any


class BadgeRepository:
    """Data access helpers for badge definitions, awards, and progress."""

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # Definition + student lookups
    # ------------------------------------------------------------------

    def list_active_badge_definitions(self) -> List[BadgeDefinition]:
        """Return active badge definitions ordered for display."""

        return (
            self.db.query(BadgeDefinition)
            .filter(BadgeDefinition.is_active.is_(True))
            .order_by(
                BadgeDefinition.display_order.asc().nullslast(),
                BadgeDefinition.name.asc(),
            )
            .all()
        )

    def get_badge_definition_by_slug(self, slug: str) -> Optional[BadgeDefinition]:
        return self.db.query(BadgeDefinition).filter(BadgeDefinition.slug == slug).first()

    def list_student_badge_awards(self, student_id: str) -> List[StudentBadgeAwardRow]:
        """Return badge award rows joined with definitions for a student."""

        rows = (
            self.db.query(StudentBadge, BadgeDefinition)
            .join(BadgeDefinition, StudentBadge.badge_id == BadgeDefinition.id)
            .filter(StudentBadge.student_id == student_id)
            .all()
        )

        awards: List[StudentBadgeAwardRow] = []
        for award, definition in rows:
            awards.append(
                StudentBadgeAwardRow(
                    badge_id=award.badge_id,
                    slug=definition.slug,
                    name=definition.name,
                    description=definition.description,
                    criteria_config=definition.criteria_config,
                    status=award.status,
                    awarded_at=award.awarded_at,
                    confirmed_at=award.confirmed_at,
                    progress_snapshot=award.progress_snapshot,
                )
            )
        return awards

    def list_student_badge_progress(self, student_id: str) -> List[StudentBadgeProgressRow]:
        """Return badge progress rows joined with definitions for a student."""

        rows = (
            self.db.query(BadgeProgress, BadgeDefinition)
            .join(BadgeDefinition, BadgeProgress.badge_id == BadgeDefinition.id)
            .filter(BadgeProgress.student_id == student_id)
            .all()
        )

        progress_rows: List[StudentBadgeProgressRow] = []
        for progress, definition in rows:
            progress_rows.append(
                StudentBadgeProgressRow(
                    badge_id=progress.badge_id,
                    slug=definition.slug,
                    name=definition.name,
                    description=definition.description,
                    criteria_config=definition.criteria_config,
                    current_progress=progress.current_progress,
                    last_updated=progress.last_updated,
                )
            )
        return progress_rows

    # ------------------------------------------------------------------
    # Booking-driven helpers
    # ------------------------------------------------------------------

    def count_completed_lessons(self, student_id: str) -> int:
        """Count lessons with status COMPLETED for the student."""

        count = (
            self.db.query(func.count(Booking.id))
            .filter(
                Booking.student_id == student_id,
                Booking.status == BookingStatus.COMPLETED,
                Booking.completed_at.isnot(None),
            )
            .scalar()
        )
        return int(count or 0)

    def list_completed_lessons(self, student_id: str) -> List[Dict[str, Any]]:
        """Return completed lessons ordered by completion time."""

        rows = (
            self.db.query(Booking)
            .filter(
                Booking.student_id == student_id,
                Booking.status == BookingStatus.COMPLETED,
                Booking.completed_at.isnot(None),
            )
            .order_by(Booking.completed_at.asc())
            .all()
        )

        result: List[Dict[str, Any]] = []
        for booking in rows:
            result.append(
                {
                    "booking_id": booking.id,
                    "instructor_id": booking.instructor_id,
                    "completed_at": booking.completed_at,
                    "booked_at": booking.confirmed_at or booking.created_at,
                }
            )
        return result

    def get_latest_completed_lesson(
        self,
        student_id: str,
        *,
        before: Optional[datetime] = None,
        exclude_booking_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Return the most recent completed lesson prior to the provided time."""

        query = self.db.query(Booking).filter(
            Booking.student_id == student_id,
            Booking.status == BookingStatus.COMPLETED,
            Booking.completed_at.isnot(None),
        )

        if before is not None:
            query = query.filter(Booking.completed_at < before)
        if exclude_booking_id:
            query = query.filter(Booking.id != exclude_booking_id)

        booking = query.order_by(Booking.completed_at.desc()).first()
        if not booking:
            return None
        return {
            "booking_id": booking.id,
            "instructor_id": booking.instructor_id,
            "completed_at": booking.completed_at,
            "booked_at": booking.confirmed_at or booking.created_at,
        }

    # ------------------------------------------------------------------
    # Badge award helpers
    # ------------------------------------------------------------------

    def student_has_badge(self, student_id: str, badge_id: str) -> bool:
        """Return True if a pending or confirmed award already exists."""

        record = (
            self.db.query(StudentBadge)
            .filter(
                StudentBadge.student_id == student_id,
                StudentBadge.badge_id == badge_id,
            )
            .first()
        )
        if not record:
            return False
        return record.status in {"pending", "confirmed"}

    def upsert_progress(
        self,
        student_id: str,
        badge_id: str,
        progress_json: Dict[str, Any],
        *,
        now_utc: Optional[datetime] = None,
    ) -> None:
        """Insert or update badge progress for the student."""

        now = now_utc or datetime.now(timezone.utc)
        existing = (
            self.db.query(BadgeProgress)
            .filter(
                BadgeProgress.student_id == student_id,
                BadgeProgress.badge_id == badge_id,
            )
            .first()
        )

        if existing:
            existing.current_progress = progress_json
            existing.last_updated = now
        else:
            progress = BadgeProgress(
                student_id=student_id,
                badge_id=badge_id,
                current_progress=progress_json,
                last_updated=now,
            )
            self.db.add(progress)

    def insert_award_pending_or_confirmed(
        self,
        student_id: str,
        badge_id: str,
        *,
        hold_hours: int,
        progress_snapshot: Dict[str, Any],
        now_utc: datetime,
    ) -> Optional[str]:
        """Insert (or revive) a badge award obeying the unique constraint."""

        existing = (
            self.db.query(StudentBadge)
            .filter(
                StudentBadge.student_id == student_id,
                StudentBadge.badge_id == badge_id,
            )
            .with_for_update(of=StudentBadge)
            .first()
        )

        hold_delta = timedelta(hours=max(hold_hours, 0))
        hold_until = now_utc + hold_delta if hold_hours > 0 else None

        if existing:
            if existing.status in {"pending", "confirmed"}:
                return existing.id

            existing.status = "pending" if hold_hours > 0 else "confirmed"
            existing.awarded_at = now_utc
            existing.hold_until = hold_until
            existing.confirmed_at = now_utc if hold_hours <= 0 else None
            existing.revoked_at = None
            existing.progress_snapshot = progress_snapshot
            return existing.id

        award = StudentBadge(
            student_id=student_id,
            badge_id=badge_id,
            status="pending" if hold_hours > 0 else "confirmed",
            awarded_at=now_utc,
            hold_until=hold_until,
            confirmed_at=now_utc if hold_hours <= 0 else None,
            progress_snapshot=progress_snapshot,
        )
        self.db.add(award)
        self.db.flush()
        return award.id

    def get_pending_awards_due(
        self, now_utc: datetime
    ) -> List[tuple[StudentBadge, BadgeDefinition]]:
        """Return (award, definition) pairs for pending awards whose holds elapsed."""

        rows = (
            self.db.query(StudentBadge, BadgeDefinition)
            .join(BadgeDefinition, StudentBadge.badge_id == BadgeDefinition.id)
            .filter(
                StudentBadge.status == "pending",
                StudentBadge.hold_until.isnot(None),
                StudentBadge.hold_until <= now_utc,
            )
            .all()
        )
        return rows

    def mark_award_confirmed(self, award: StudentBadge, *, confirmed_at: datetime) -> None:
        award.status = "confirmed"
        award.confirmed_at = confirmed_at
        award.revoked_at = None

    def mark_award_revoked(self, award: StudentBadge, *, revoked_at: datetime) -> None:
        award.status = "revoked"
        award.revoked_at = revoked_at
        award.confirmed_at = None

    def list_completed_lesson_times(self, student_id: str) -> List[datetime]:
        """Return all completion timestamps (UTC) for the student ordered descending."""
        rows = (
            self.db.query(Booking.completed_at)
            .filter(
                Booking.student_id == student_id,
                Booking.status == BookingStatus.COMPLETED,
                Booking.completed_at.isnot(None),
            )
            .order_by(Booking.completed_at.desc())
            .all()
        )
        return [row[0] for row in rows if row[0] is not None]

    def get_review_stats(self, student_id: str) -> Dict[str, float]:
        rows = (
            self.db.query(
                func.count(Review.id),
                func.avg(Review.rating * 1.0),
            )
            .filter(
                Review.student_id == student_id,
                Review.status.in_([ReviewStatus.PUBLISHED.value, ReviewStatus.FLAGGED.value]),
            )
            .first()
        )
        total = int(rows[0] or 0) if rows else 0
        avg_rating = float(rows[1]) if rows and rows[1] is not None else 0.0
        return {"count": total, "avg_rating": avg_rating}

    def get_review_stats_since(self, student_id: str, since_utc: datetime) -> Dict[str, float]:
        """Return review count/avg rating for reviews created on/after since_utc."""

        rows = (
            self.db.query(
                func.count(Review.id),
                func.avg(Review.rating * 1.0),
            )
            .filter(
                Review.student_id == student_id,
                Review.status.in_([ReviewStatus.PUBLISHED.value, ReviewStatus.FLAGGED.value]),
                Review.created_at >= since_utc,
            )
            .first()
        )
        total = int(rows[0] or 0) if rows else 0
        avg_rating = float(rows[1]) if rows and rows[1] is not None else 0.0
        return {"count": total, "avg_rating": avg_rating}

    def count_distinct_instructors_for_student(self, student_id: str) -> int:
        result = (
            self.db.query(func.count(func.distinct(Booking.instructor_id)))
            .filter(
                Booking.student_id == student_id,
                Booking.status == BookingStatus.COMPLETED,
                Booking.completed_at.isnot(None),
            )
            .scalar()
        )
        return int(result or 0)

    def get_max_lessons_with_single_instructor(self, student_id: str) -> int:
        row = (
            self.db.query(func.count(Booking.id))
            .filter(
                Booking.student_id == student_id,
                Booking.status == BookingStatus.COMPLETED,
                Booking.completed_at.isnot(None),
            )
            .group_by(Booking.instructor_id)
            .order_by(func.count(Booking.id).desc())
            .first()
        )
        return int(row[0]) if row else 0

    def get_cancel_noshow_rate_pct_60d(self, student_id: str, now_utc: datetime) -> float:
        return self.get_cancel_noshow_rate_pct_window(student_id, now_utc, 60)

    def get_cancel_noshow_rate_pct_window(
        self,
        student_id: str,
        now_utc: datetime,
        window_days: int,
    ) -> float:
        """Return cancel/no-show rate (percent) inside the requested rolling window."""

        window_days = int(window_days or 0)
        if window_days <= 0:
            return 0.0

        window_start = now_utc - timedelta(days=window_days)
        relevant_statuses = [
            BookingStatus.COMPLETED,
            BookingStatus.CANCELLED,
            BookingStatus.NO_SHOW,
        ]

        rows = (
            self.db.query(Booking.status, func.count(Booking.id))
            .filter(
                Booking.student_id == student_id,
                Booking.created_at >= window_start,
                Booking.status.in_(relevant_statuses),
            )
            .group_by(Booking.status)
            .all()
        )

        totals = {status: count for status, count in rows}
        total = sum(totals.values())
        if total == 0:
            return 0.0

        issues = totals.get(BookingStatus.CANCELLED, 0) + totals.get(BookingStatus.NO_SHOW, 0)
        return (issues / total) * 100.0

    def count_distinct_completed_categories(self, student_id: str) -> int:
        rows = (
            self.db.query(func.count(func.distinct(ServiceCategory.slug)))
            .select_from(Booking)
            .join(InstructorService, Booking.instructor_service_id == InstructorService.id)
            .join(ServiceCatalog, InstructorService.service_catalog_id == ServiceCatalog.id)
            .join(ServiceCategory, ServiceCatalog.category_id == ServiceCategory.id)
            .filter(
                Booking.student_id == student_id,
                Booking.status == BookingStatus.COMPLETED,
                Booking.completed_at.isnot(None),
            )
            .scalar()
        )
        return int(rows or 0)

    def has_rebook_in_any_category(self, student_id: str) -> bool:
        row = (
            self.db.query(ServiceCategory.slug)
            .select_from(Booking)
            .join(InstructorService, Booking.instructor_service_id == InstructorService.id)
            .join(ServiceCatalog, InstructorService.service_catalog_id == ServiceCatalog.id)
            .join(ServiceCategory, ServiceCatalog.category_id == ServiceCategory.id)
            .filter(
                Booking.student_id == student_id,
                Booking.status == BookingStatus.COMPLETED,
                Booking.completed_at.isnot(None),
            )
            .group_by(ServiceCategory.slug)
            .having(func.count(Booking.id) >= 2)
            .first()
        )
        return row is not None

    def get_overall_student_avg_rating(self, student_id: str) -> float:
        stats = self.get_review_stats(student_id)
        return stats["avg_rating"]

    # ------------------------------------------------------------------
    # Admin award helpers
    # ------------------------------------------------------------------

    def list_awards(
        self,
        *,
        status: Optional[str],
        before: datetime,
        limit: int,
        offset: int,
    ) -> tuple[List[tuple[StudentBadge, BadgeDefinition, User]], int]:
        status_filter = status or "pending"
        base = (
            self.db.query(StudentBadge, BadgeDefinition, User)
            .join(BadgeDefinition, StudentBadge.badge_id == BadgeDefinition.id)
            .join(User, StudentBadge.student_id == User.id)
        )
        if status_filter:
            base = base.filter(StudentBadge.status == status_filter)

        if status_filter == "pending":
            base = base.filter(
                or_(
                    StudentBadge.hold_until.is_(None),
                    StudentBadge.hold_until <= before,
                )
            )
        else:
            base = base.filter(StudentBadge.awarded_at <= before)

        total = base.order_by(None).with_entities(func.count()).scalar() or 0

        rows = (
            base.order_by(StudentBadge.awarded_at.desc(), StudentBadge.id.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return rows, int(total)

    def get_award_with_details(
        self, award_id: str
    ) -> Optional[tuple[StudentBadge, BadgeDefinition, User]]:
        return (
            self.db.query(StudentBadge, BadgeDefinition, User)
            .join(BadgeDefinition, StudentBadge.badge_id == BadgeDefinition.id)
            .join(User, StudentBadge.student_id == User.id)
            .filter(StudentBadge.id == award_id)
            .first()
        )

    def update_award_status(
        self,
        award_id: str,
        new_status: str,
        now_utc: datetime,
    ) -> int:
        query = self.db.query(StudentBadge).filter(
            StudentBadge.id == award_id, StudentBadge.status == "pending"
        )
        if new_status == "confirmed":
            updated = query.update(
                {
                    StudentBadge.status: "confirmed",
                    StudentBadge.confirmed_at: now_utc,
                    StudentBadge.revoked_at: None,
                }
            )
        elif new_status == "revoked":
            updated = query.update(
                {
                    StudentBadge.status: "revoked",
                    StudentBadge.revoked_at: now_utc,
                    StudentBadge.confirmed_at: None,
                }
            )
        else:
            updated = 0
        if updated:
            self.db.flush()
        return int(updated)


__all__ = [
    "BadgeRepository",
    "StudentBadgeAwardRow",
    "StudentBadgeProgressRow",
]
