# backend/app/repositories/instructor_lifecycle_repository.py
"""
Repository for instructor lifecycle event tracking.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, cast

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..core.exceptions import RepositoryException
from ..models.instructor import InstructorProfile
from ..models.instructor_lifecycle_event import EVENT_TYPES, InstructorLifecycleEvent
from ..models.user import User
from .base_repository import BaseRepository

MILESTONE_EVENT_TYPES: tuple[str, ...] = tuple(
    event_type for event_type in EVENT_TYPES if event_type not in {"paused", "reactivated"}
)


class InstructorLifecycleRepository(BaseRepository[InstructorLifecycleEvent]):
    """Repository for instructor lifecycle event tracking."""

    def __init__(self, db: Session):
        super().__init__(db, InstructorLifecycleEvent)

    def record_event(
        self,
        user_id: str,
        event_type: str,
        metadata: dict[str, Any] | None = None,
    ) -> InstructorLifecycleEvent:
        """Record a new lifecycle event."""
        if event_type not in EVENT_TYPES:
            raise RepositoryException(f"Invalid lifecycle event_type: {event_type}")

        return self.create(
            user_id=user_id,
            event_type=event_type,
            metadata_json=metadata,
        )

    def get_latest_event_for_user(self, user_id: str) -> InstructorLifecycleEvent | None:
        """Get the most recent event for an instructor."""
        return cast(
            InstructorLifecycleEvent | None,
            self.db.query(InstructorLifecycleEvent)
            .filter(InstructorLifecycleEvent.user_id == user_id)
            .order_by(
                InstructorLifecycleEvent.occurred_at.desc(),
                InstructorLifecycleEvent.id.desc(),
            )
            .first(),
        )

    def get_events_for_user(
        self, user_id: str, event_types: list[str] | None = None
    ) -> list[InstructorLifecycleEvent]:
        """Get all events for an instructor, optionally filtered by type."""
        query = self.db.query(InstructorLifecycleEvent).filter(
            InstructorLifecycleEvent.user_id == user_id
        )
        if event_types:
            query = query.filter(InstructorLifecycleEvent.event_type.in_(event_types))
        return cast(
            list[InstructorLifecycleEvent],
            query.order_by(InstructorLifecycleEvent.occurred_at.asc()).all(),
        )

    def get_current_stage(self, user_id: str) -> str | None:
        """Derive current onboarding stage from latest event."""
        latest = (
            self.db.query(InstructorLifecycleEvent)
            .filter(
                InstructorLifecycleEvent.user_id == user_id,
                InstructorLifecycleEvent.event_type.in_(MILESTONE_EVENT_TYPES),
            )
            .order_by(
                InstructorLifecycleEvent.occurred_at.desc(),
                InstructorLifecycleEvent.id.desc(),
            )
            .first()
        )
        return latest.event_type if latest else None

    def count_by_stage(
        self,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        founding_only: bool = False,
    ) -> dict[str, int]:
        """Count distinct instructors with events at each stage."""
        query = self.db.query(
            InstructorLifecycleEvent.event_type,
            func.count(func.distinct(InstructorLifecycleEvent.user_id)).label("count"),
        )

        if founding_only:
            query = query.join(
                InstructorProfile,
                InstructorProfile.user_id == InstructorLifecycleEvent.user_id,
            ).filter(InstructorProfile.is_founding_instructor.is_(True))

        if start_date is not None:
            query = query.filter(InstructorLifecycleEvent.occurred_at >= start_date)
        if end_date is not None:
            query = query.filter(InstructorLifecycleEvent.occurred_at <= end_date)

        rows = query.group_by(InstructorLifecycleEvent.event_type).all()
        counts = {event_type: 0 for event_type in EVENT_TYPES}
        for row in rows:
            counts[str(row.event_type)] = int(row.count or 0)
        return counts

    def get_stuck_instructors(
        self,
        stuck_days: int = 7,
        stage: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Find instructors stuck at a stage for more than N days."""
        limit = max(1, limit)
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=stuck_days)

        latest_events = (
            self.db.query(
                InstructorLifecycleEvent.user_id.label("user_id"),
                InstructorLifecycleEvent.event_type.label("event_type"),
                InstructorLifecycleEvent.occurred_at.label("occurred_at"),
                func.row_number()
                .over(
                    partition_by=InstructorLifecycleEvent.user_id,
                    order_by=(
                        InstructorLifecycleEvent.occurred_at.desc(),
                        InstructorLifecycleEvent.id.desc(),
                    ),
                )
                .label("rn"),
            )
        ).subquery()

        query = (
            self.db.query(
                latest_events.c.user_id,
                latest_events.c.event_type,
                latest_events.c.occurred_at,
                User.first_name,
                User.last_name,
                User.email,
            )
            .join(User, User.id == latest_events.c.user_id)
            .filter(
                latest_events.c.rn == 1,
                latest_events.c.occurred_at <= cutoff,
            )
        )

        if stage:
            query = query.filter(latest_events.c.event_type == stage)

        rows = query.order_by(latest_events.c.occurred_at.asc()).limit(limit).all()

        results: list[dict[str, Any]] = []
        for row in rows:
            first = (row.first_name or "").strip()
            last = (row.last_name or "").strip()
            name = " ".join(part for part in [first, last] if part).strip()
            occurred_at = row.occurred_at
            days_stuck = max(0, (now - occurred_at).days) if occurred_at else 0
            results.append(
                {
                    "user_id": row.user_id,
                    "name": name,
                    "email": row.email,
                    "stage": row.event_type,
                    "days_stuck": days_stuck,
                    "occurred_at": occurred_at,
                }
            )

        return results
