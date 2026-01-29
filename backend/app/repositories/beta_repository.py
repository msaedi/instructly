"""Repositories for BetaInvite and BetaAccess (repository pattern)."""

from datetime import date, datetime, time, timezone
from typing import Any, List, Optional, Sequence, cast

from sqlalchemy import and_, desc, func, or_, text
from sqlalchemy.orm import Session

from ..models.beta import BetaAccess, BetaInvite, BetaSettings
from ..services.timezone_service import TimezoneService
from .base_repository import BaseRepository


class BetaInviteRepository(BaseRepository[BetaInvite]):
    def __init__(self, db: Session):
        super().__init__(db, BetaInvite)

    def get_by_code(self, code: str) -> Optional[BetaInvite]:
        result = self.db.query(BetaInvite).filter(BetaInvite.code == code).first()
        return cast(Optional[BetaInvite], result)

    def mark_used(self, code: str, user_id: str, used_at: Optional[datetime] = None) -> bool:
        invite = self.get_by_code(code)
        if not invite or invite.used_at is not None:
            return False
        invite.used_at = used_at or datetime.now(timezone.utc)
        invite.used_by_user_id = user_id
        self.db.flush()
        return True

    def bulk_create_invites(self, invites: Sequence[dict[str, Any]]) -> List[BetaInvite]:
        return self.bulk_create(list(invites))

    def list_invites(
        self,
        *,
        email: str | None = None,
        status: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        limit: int = 50,
        cursor: str | None = None,
        now: datetime | None = None,
    ) -> tuple[List[BetaInvite], str | None]:
        """
        List beta invites with optional filters and cursor pagination.

        Cursor format: "<created_at_iso>|<invite_id>"
        """
        query = self.db.query(BetaInvite)
        now_utc = now or datetime.now(timezone.utc)

        if email:
            query = query.filter(func.lower(BetaInvite.email) == email.lower())

        if start_date:
            start_dt = TimezoneService.local_to_utc(start_date, time.min, "UTC")
            query = query.filter(BetaInvite.created_at >= start_dt)
        if end_date:
            end_dt = TimezoneService.local_to_utc(end_date, time.max, "UTC")
            query = query.filter(BetaInvite.created_at <= end_dt)

        if status:
            if status == "accepted":
                query = query.filter(BetaInvite.used_at.is_not(None))
            elif status == "expired":
                query = query.filter(
                    BetaInvite.used_at.is_(None),
                    BetaInvite.expires_at.is_not(None),
                    BetaInvite.expires_at < now_utc,
                )
            elif status == "pending":
                query = query.filter(
                    BetaInvite.used_at.is_(None),
                    BetaInvite.expires_at.is_not(None),
                    BetaInvite.expires_at >= now_utc,
                )
            elif status == "revoked":
                # Revocation isn't tracked; return empty set.
                query = query.filter(text("1=0"))

        if cursor:
            cursor_parts = cursor.split("|", 1)
            if len(cursor_parts) != 2:
                raise ValueError("Invalid cursor")
            cursor_time = datetime.fromisoformat(cursor_parts[0])
            if cursor_time.tzinfo is None:
                cursor_time = cursor_time.replace(tzinfo=timezone.utc)
            cursor_id = cursor_parts[1]
            query = query.filter(
                or_(
                    BetaInvite.created_at < cursor_time,
                    and_(
                        BetaInvite.created_at == cursor_time,
                        BetaInvite.id < cursor_id,
                    ),
                )
            )

        query = query.order_by(
            BetaInvite.created_at.desc(),
            desc(cast(Any, BetaInvite.id)),
        )

        items = cast(List[BetaInvite], query.limit(limit + 1).all())
        next_cursor = None
        if len(items) > limit:
            items = items[:limit]
            last = items[-1]
            next_cursor = f"{last.created_at.isoformat()}|{last.id}"

        return items, next_cursor


class BetaAccessRepository(BaseRepository[BetaAccess]):
    def __init__(self, db: Session):
        super().__init__(db, BetaAccess)

    def grant_access(
        self, user_id: str, role: str, phase: str, invited_by_code: Optional[str]
    ) -> BetaAccess:
        return self.create(user_id=user_id, role=role, phase=phase, invited_by_code=invited_by_code)

    def get_latest_for_user(self, user_id: str) -> Optional[BetaAccess]:
        result = (
            self.db.query(BetaAccess)
            .filter(BetaAccess.user_id == user_id)
            .order_by(BetaAccess.granted_at.desc())
            .first()
        )
        return cast(Optional[BetaAccess], result)


class BetaSettingsRepository(BaseRepository[BetaSettings]):
    def __init__(self, db: Session):
        super().__init__(db, BetaSettings)

    def get_singleton(self) -> BetaSettings:
        rec = self.db.query(BetaSettings).order_by(BetaSettings.updated_at.desc()).first()
        if rec:
            return cast(BetaSettings, rec)
        # Create default if none exists
        return self.create(
            beta_disabled=False, beta_phase="instructor_only", allow_signup_without_invite=False
        )

    def update_settings(
        self, *, beta_disabled: bool, beta_phase: str, allow_signup_without_invite: bool
    ) -> BetaSettings:
        rec = self.get_singleton()
        rec.beta_disabled = beta_disabled
        rec.beta_phase = beta_phase
        rec.allow_signup_without_invite = allow_signup_without_invite
        self.db.flush()
        return rec
