"""Repositories for BetaInvite and BetaAccess (repository pattern)."""

from datetime import datetime, timezone
from typing import Any, List, Optional, Sequence, cast

from sqlalchemy.orm import Session

from ..models.beta import BetaAccess, BetaInvite, BetaSettings
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
