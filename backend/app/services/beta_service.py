from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
import random
from typing import Optional
from urllib.parse import urlencode

from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.constants import BRAND_NAME
from ..models.beta import BetaAccess, BetaInvite
from ..repositories.beta_repository import BetaAccessRepository, BetaInviteRepository
from ..repositories.instructor_profile_repository import InstructorProfileRepository
from ..services.base import BaseService, CacheInvalidationProtocol
from ..services.config_service import ConfigService
from ..services.email import EmailService
from ..services.email_subjects import EmailSubject
from ..services.template_registry import TemplateRegistry
from ..services.template_service import TemplateService

AMBIGUOUS = {"0", "O", "1", "I", "L"}
ALPHABET = [c for c in "ABCDEFGHJKLMNPQRSTUVWXYZ23456789" if c not in AMBIGUOUS]


def _resolve_frontend_origin(base_override: str | None) -> str:
    site_mode = os.getenv("SITE_MODE", "").strip().lower()
    candidate = base_override or settings.frontend_url
    if site_mode == "local" and settings.local_beta_frontend_origin:
        return settings.local_beta_frontend_origin
    return candidate


def _resolve_invite_claim_origin(base_override: str | None) -> str:
    """
    Resolve the base URL for invite claim links.

    Priority order:
    1. Local mode: use local_beta_frontend_origin
    2. Explicit base_override parameter
    3. INVITE_CLAIM_BASE_URL env var (if set)
    4. Fallback to frontend_url
    """
    site_mode = os.getenv("SITE_MODE", "").strip().lower()
    if site_mode == "local" and settings.local_beta_frontend_origin:
        return settings.local_beta_frontend_origin.rstrip("/")

    # Prefer explicit override, then INVITE_CLAIM_BASE_URL (if explicitly set), then frontend_url
    if base_override:
        base = base_override
    elif os.getenv("INVITE_CLAIM_BASE_URL"):
        base = settings.invite_claim_base_url
    else:
        base = settings.frontend_url

    return base.rstrip("/")


def build_join_url(code: str, email: Optional[str], base_override: str | None = None) -> str:
    params = {
        "token": code,
        "utm_source": "email",
        "utm_medium": "invite",
        "utm_campaign": "founding_instructor",
    }
    query = urlencode(params)
    base = _resolve_invite_claim_origin(base_override)
    return f"{base}/invite/claim?{query}"


def build_welcome_url(code: str, email: Optional[str], base_override: str | None = None) -> str:
    params = {"invite_code": code}
    if email:
        params["email"] = email
    query = urlencode(params)
    base = _resolve_frontend_origin(base_override)
    return f"{base}/instructor/welcome?{query}"


def generate_code(length: int = 8) -> str:
    return "".join(random.choice(ALPHABET) for _ in range(length))


class BetaService(BaseService):
    def __init__(self, db: Session, cache: CacheInvalidationProtocol | None = None):
        super().__init__(db, cache)
        self.invites = BetaInviteRepository(db)
        self.access = BetaAccessRepository(db)

    @BaseService.measure_operation("beta_invite_validated")
    def validate_invite(self, code: str) -> tuple[bool, Optional[str], Optional[BetaInvite]]:
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
        self,
        count: int,
        role: str,
        expires_in_days: int,
        source: Optional[str],
        emails: Optional[list[str]],
        grant_founding_status: bool = True,
    ) -> list[BetaInvite]:
        expires_at = datetime.now(timezone.utc) + timedelta(days=expires_in_days)
        records = []
        emails = emails or []
        for i in range(count):
            rec = {
                "id": None,  # let ULID default on model
                "code": generate_code(8),
                "email": emails[i] if i < len(emails) else None,
                "role": role,
                "grant_founding_status": grant_founding_status,
                "expires_at": expires_at,
                "metadata_json": {"source": source} if source else None,
            }
            records.append(rec)
        return self.invites.bulk_create_invites(records)

    @BaseService.measure_operation("beta_invite_consumed")
    def consume_and_grant(
        self, code: str, user_id: str, role: str, phase: str
    ) -> tuple[BetaAccess | None, Optional[str], Optional[BetaInvite]]:
        ok, reason, invite = self.validate_invite(code)
        if not ok:
            return None, reason, invite
        self.invites.mark_used(code, user_id)
        grant = self.access.grant_access(
            user_id=user_id, role=role, phase=phase, invited_by_code=code
        )

        # Invalidate user's auth cache so next /auth/me sees new beta_access
        if grant:
            from ..core.auth_cache import invalidate_cached_user_by_id_sync

            invalidate_cached_user_by_id_sync(user_id, self.db)

        return grant, None, invite

    @BaseService.measure_operation("beta_invite_sent")
    def send_invite_email(
        self,
        to_email: str,
        role: str,
        expires_in_days: int,
        source: str | None,
        base_url: str | None,
        grant_founding_status: bool = True,
    ) -> tuple[BetaInvite, str, str]:
        created = self.bulk_generate(
            count=1,
            role=role,
            expires_in_days=expires_in_days,
            source=source,
            emails=[to_email],
            grant_founding_status=grant_founding_status,
        )
        invite = created[0]
        join_url = build_join_url(invite.code, to_email, base_url)
        welcome_url = build_welcome_url(invite.code, to_email, base_url)

        # Render email
        template_service = TemplateService(self.db, None)
        html = template_service.render_template(
            TemplateRegistry.BETA_INVITE,
            context={
                "brand_name": BRAND_NAME,
                "recipient_name": None,
                "invite_code": invite.code,
                "join_url": join_url,
                "expires_in_days": expires_in_days,
            },
        )

        email_service = EmailService(self.db, None)
        email_service.send_email(
            to_email=to_email,
            subject=EmailSubject.beta_invite(),
            html_content=html,
            text_content=f"Use your invite code {invite.code}. Join: {join_url}",
            from_email="invites@instainstru.com",
            from_name=BRAND_NAME,
            template=TemplateRegistry.BETA_INVITE,
        )

        return invite, join_url, welcome_url

    @BaseService.measure_operation("beta_invite_sent_batch")
    def send_invite_batch(
        self,
        emails: list[str],
        role: str,
        expires_in_days: int,
        source: str | None,
        base_url: str | None,
    ) -> tuple[list[tuple[BetaInvite, str, str, str]], list[tuple[str, str]]]:
        sent: list[tuple[BetaInvite, str, str, str]] = []  # (invite, email, join, welcome)
        failed: list[tuple[str, str]] = []  # (email, reason)
        for em in emails:
            try:
                invite, join_url, welcome_url = self.send_invite_email(
                    to_email=em,
                    role=role,
                    expires_in_days=expires_in_days,
                    source=source,
                    base_url=base_url,
                )
                sent.append((invite, em, join_url, welcome_url))
            except Exception as e:
                failed.append((em, str(e)))
        return sent, failed

    @BaseService.measure_operation("beta_try_grant_founding_status")
    def try_grant_founding_status(self, profile_id: str) -> tuple[bool, str]:
        """Attempt to grant founding status atomically, honoring the configured cap."""
        repo = InstructorProfileRepository(self.db)
        profile = repo.get_by_id(profile_id, load_relationships=False)
        if not profile:
            return False, "Instructor profile not found"

        config_service = ConfigService(self.db)
        pricing_config, _ = config_service.get_pricing_config()
        cap_raw = pricing_config.get("founding_instructor_cap", 100)
        try:
            cap = int(cap_raw)
        except (TypeError, ValueError):
            cap = 100

        granted, current_count = repo.try_claim_founding_status(profile_id, cap)
        if granted:
            return True, f"Granted founding status ({current_count}/{cap})"
        return False, f"Founding cap reached ({current_count}/{cap})"
