from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.constants import BRAND_NAME
from ..repositories.beta_repository import BetaAccessRepository, BetaInviteRepository
from ..services.base import BaseService
from ..services.email import EmailService
from ..services.email_subjects import EmailSubject
from ..services.template_registry import TemplateRegistry
from ..services.template_service import TemplateService

AMBIGUOUS = {"0", "O", "1", "I", "L"}
ALPHABET = [c for c in "ABCDEFGHJKLMNPQRSTUVWXYZ23456789" if c not in AMBIGUOUS]


def generate_code(length: int = 8) -> str:
    return "".join(random.choice(ALPHABET) for _ in range(length))


class BetaService:
    def __init__(self, db: Session):
        self.invites = BetaInviteRepository(db)
        self.access = BetaAccessRepository(db)
        self.db = db

    @BaseService.measure_operation("beta_invite_validated")
    def validate_invite(self, code: str) -> tuple[bool, Optional[str], Optional[object]]:
        invite = self.invites.get_by_code(code)
        if not invite:
            return False, "not_found", None
        now = datetime.now(timezone.utc)
        if invite.expires_at and invite.expires_at.astimezone(timezone.utc) < now:
            return False, "expired", invite
        if invite.used_at is not None:
            return False, "used", invite
        return True, None, invite

    @BaseService.measure_operation("beta_invite_generated_bulk")
    def bulk_generate(
        self, count: int, role: str, expires_in_days: int, source: Optional[str], emails: Optional[list[str]]
    ):
        expires_at = datetime.now(timezone.utc) + timedelta(days=expires_in_days)
        records = []
        emails = emails or []
        for i in range(count):
            rec = {
                "id": None,  # let ULID default on model
                "code": generate_code(8),
                "email": emails[i] if i < len(emails) else None,
                "role": role,
                "expires_at": expires_at,
                "metadata_json": {"source": source} if source else None,
            }
            records.append(rec)
        return self.invites.bulk_create_invites(records)

    @BaseService.measure_operation("beta_invite_consumed")
    def consume_and_grant(self, code: str, user_id: str, role: str, phase: str):
        ok, reason, invite = self.validate_invite(code)
        if not ok:
            return None, reason
        self.invites.mark_used(code, user_id)
        grant = self.access.grant_access(user_id=user_id, role=role, phase=phase, invited_by_code=code)
        return grant, None

    @BaseService.measure_operation("beta_invite_sent")
    def send_invite_email(
        self, to_email: str, role: str, expires_in_days: int, source: str | None, base_url: str | None
    ):
        created = self.bulk_generate(
            count=1, role=role, expires_in_days=expires_in_days, source=source, emails=[to_email]
        )
        invite = created[0]
        base = base_url or settings.frontend_url
        join_url = f"{base}/instructor/join?invite_code={invite.code}&email={to_email}"
        welcome_url = f"{base}/instructor/welcome?invite_code={invite.code}&email={to_email}"

        # Render email
        template_service = TemplateService(self.db, None)
        html = template_service.render_template(
            TemplateRegistry.BETA_INVITE,
            context={
                "brand_name": BRAND_NAME,
                "recipient_name": None,
                "invite_code": invite.code,
                "welcome_url": welcome_url,
                "join_url": join_url,
                "expires_in_days": expires_in_days,
            },
        )

        email_service = EmailService(self.db, None)
        email_service.send_email(
            to_email=to_email,
            subject=EmailSubject.beta_invite(),
            html_content=html,
            text_content=f"Use your invite code {invite.code}. Join: {join_url} or go to: {welcome_url}",
            from_email="invites@instainstru.com",
            from_name=BRAND_NAME,
        )

        return invite, join_url, welcome_url
