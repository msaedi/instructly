# backend/app/services/student_badge_service.py
"""
Service layer for exposing student badge state to the API.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from ..repositories.badge_repository import (
    BadgeRepository,
)
from ..repositories.factory import RepositoryFactory


class StudentBadgeService:
    """Business logic for querying student badge data."""

    EARNED_STATUSES = {"pending", "confirmed"}

    def __init__(self, db: Session):
        self.db = db
        self.repository: BadgeRepository = RepositoryFactory.create_badge_repository(db)

    def get_student_badges(self, student_id: str) -> List[Dict[str, Any]]:
        """
        Return badge state for the requested student in display order.
        """
        definitions = self.repository.list_active_badge_definitions()
        award_rows = self.repository.list_student_badge_awards(student_id)
        progress_rows = self.repository.list_student_badge_progress(student_id)
        total_completed = self.repository.count_completed_lessons(student_id)

        awards_by_slug = {row["slug"]: row for row in award_rows}
        progress_by_slug = {row["slug"]: row for row in progress_rows}

        response: List[Dict[str, Any]] = []
        for definition in definitions:
            slug = definition.slug
            criteria_config = definition.criteria_config or {}
            hide_progress = bool(criteria_config.get("hide_progress"))

            award = awards_by_slug.get(slug)
            progress_entry = progress_by_slug.get(slug)
            award_status = award.get("status") if award else None

            earned = award_status in self.EARNED_STATUSES

            badge_payload: Dict[str, Any] = {
                "slug": slug,
                "name": definition.name,
                "description": definition.description,
                "earned": earned,
            }
            if award_status:
                badge_payload["status"] = award_status

            show_threshold = int(criteria_config.get("show_after_total_lessons", 0) or 0)
            limited_visibility = (
                (not earned) and show_threshold and total_completed < show_threshold
            )

            if earned and award:
                badge_payload["awarded_at"] = award["awarded_at"]
                badge_payload["confirmed_at"] = award.get("confirmed_at")

                progress_payload = _format_progress_snapshot(award.get("progress_snapshot"))
                if progress_payload is None and progress_entry:
                    progress_payload = _format_progress_snapshot(
                        progress_entry.get("current_progress")
                    )
                badge_payload["progress"] = progress_payload
            else:
                badge_payload["progress"] = None
                if not hide_progress and not limited_visibility:
                    snapshot_source = (
                        progress_entry.get("current_progress") if progress_entry else None
                    )
                    progress_payload = _format_progress_snapshot(snapshot_source)
                    if progress_payload is None and award:
                        progress_payload = _format_progress_snapshot(award.get("progress_snapshot"))
                    badge_payload["progress"] = progress_payload

            response.append(badge_payload)

        return response


def _format_progress_snapshot(snapshot: Optional[dict]) -> Optional[Dict[str, Any]]:
    """
    Normalize a stored progress snapshot and compute percent (capped at 100).
    """
    if not isinstance(snapshot, dict) or not snapshot:
        return None

    progress = dict(snapshot)
    current = progress.get("current")
    goal = progress.get("goal")

    percent: Optional[float] = None
    if isinstance(current, (int, float)) and isinstance(goal, (int, float)) and goal:
        raw_percent = (current / goal) * 100
        percent = min(raw_percent, 100.0)
        percent = round(percent, 2)

    if percent is not None:
        progress["percent"] = percent

    return progress


__all__ = ["StudentBadgeService"]
