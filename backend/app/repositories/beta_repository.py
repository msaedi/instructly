"""Repositories for BetaInvite and BetaAccess (repository pattern)."""

from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session

from ..models.beta import BetaAccess, BetaInvite
from .base_repository import BaseRepository


class BetaInviteRepository(BaseRepository[BetaInvite]):
    def __init__(self, db: Session):
        super().__init__(db, BetaInvite)

    def get_by_code(self, code: str) -> Optional[BetaInvite]:
        return self.db.query(BetaInvite).filter(BetaInvite.code == code).first()

    def mark_used(self, code: str, user_id: str, used_at: Optional[datetime] = None) -> bool:
        invite = self.get_by_code(code)
        if not invite or invite.used_at is not None:
            return False
        invite.used_at = used_at or datetime.now().astimezone()
        invite.used_by_user_id = user_id
        self.db.flush()
        return True

    def bulk_create_invites(self, invites: List[dict]) -> List[BetaInvite]:
        return self.bulk_create(invites)


class BetaAccessRepository(BaseRepository[BetaAccess]):
    def __init__(self, db: Session):
        super().__init__(db, BetaAccess)

    def grant_access(self, user_id: str, role: str, phase: str, invited_by_code: Optional[str]) -> BetaAccess:
        return self.create(user_id=user_id, role=role, phase=phase, invited_by_code=invited_by_code)
