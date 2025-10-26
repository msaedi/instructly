# backend/app/services/badge_admin_service.py
"""
Admin operations for managing badge awards.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from ..core.exceptions import NotFoundException
from ..models.badge import BadgeDefinition, StudentBadge
from ..models.user import User
from ..repositories.badge_repository import BadgeRepository
from ..repositories.factory import RepositoryFactory


def _student_display_name(user: User) -> str:
    first = (user.first_name or "").strip()
    last = (user.last_name or "").strip()
    if not first and not last:
        return str(user.email or user.id)
    last_initial = f"{last[:1]}." if last else ""
    return f"{first} {last_initial}".strip()


class BadgeAdminService:
    """Service layer for admin-only badge award management."""

    def __init__(self, db: Session):
        self.db = db
        self.repository: BadgeRepository = RepositoryFactory.create_badge_repository(db)

    def list_awards(
        self,
        *,
        status: Optional[str],
        before: Optional[datetime],
        limit: int,
        offset: int,
    ) -> Dict[str, Any]:
        before_dt = before or datetime.now(timezone.utc)
        rows, total = self.repository.list_awards(
            status=status,
            before=before_dt,
            limit=limit,
            offset=offset,
        )
        items = [self._serialize_award(sb, bd, user) for sb, bd, user in rows]
        next_offset = offset + len(items) if offset + len(items) < total else None
        return {
            "items": items,
            "total": total,
            "next_offset": next_offset,
        }

    def confirm_award(self, award_id: str, now_utc: datetime) -> Dict[str, Any]:
        updated = self.repository.update_award_status(award_id, "confirmed", now_utc)
        if not updated:
            raise NotFoundException("Award not found or not pending")
        row = self.repository.get_award_with_details(award_id)
        if not row:
            raise NotFoundException("Award not found")
        return self._serialize_award(*row)

    def revoke_award(self, award_id: str, now_utc: datetime) -> Dict[str, Any]:
        updated = self.repository.update_award_status(award_id, "revoked", now_utc)
        if not updated:
            raise NotFoundException("Award not found or not pending")
        row = self.repository.get_award_with_details(award_id)
        if not row:
            raise NotFoundException("Award not found")
        return self._serialize_award(*row)

    def _serialize_award(
        self,
        award: StudentBadge,
        badge: BadgeDefinition,
        user: User,
    ) -> Dict[str, Any]:
        return {
            "award_id": award.id,
            "status": award.status,
            "awarded_at": award.awarded_at,
            "hold_until": award.hold_until,
            "confirmed_at": award.confirmed_at,
            "revoked_at": award.revoked_at,
            "badge": {
                "id": badge.id,
                "slug": badge.slug,
                "name": badge.name,
                "criteria_type": badge.criteria_type,
            },
            "student": {
                "id": user.id,
                "email": user.email,
                "display_name": _student_display_name(user),
            },
            "progress_snapshot": award.progress_snapshot,
        }


__all__ = ["BadgeAdminService"]
