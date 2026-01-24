"""Service layer for MCP invite operations."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.user import User
from app.repositories.factory import RepositoryFactory
from app.repositories.instructor_profile_repository import InstructorProfileRepository
from app.services.base import BaseService
from app.services.config_service import ConfigService


class MCPInviteService(BaseService):
    """Business logic for MCP invite preview/send operations."""

    def __init__(self, db: Session):
        super().__init__(db)
        self._audit_repo = RepositoryFactory.create_audit_repository(db)
        self._profile_repo = InstructorProfileRepository(db)
        self._config_service = ConfigService(db)
        self._user_repo = RepositoryFactory.create_user_repository(db)

    @BaseService.measure_operation("mcp_invites.lookup_users")
    def get_existing_users(self, emails: list[str]) -> list[User]:
        if not emails:
            return []
        return self._user_repo.list_by_emails(emails, case_insensitive=True)

    @BaseService.measure_operation("mcp_invites.founding_cap_remaining")
    def get_founding_cap_remaining(self) -> int:
        pricing_config, _updated_at = self._config_service.get_pricing_config()
        cap_raw = pricing_config.get("founding_instructor_cap", 100)
        try:
            cap = int(cap_raw)
        except (TypeError, ValueError):
            cap = 100
        used = self._profile_repo.count_founding_instructors()
        return max(0, cap - used)

    @BaseService.measure_operation("mcp_invites.audit_preview")
    def write_preview_audit(
        self,
        *,
        actor: User,
        recipient_count: int,
        existing_user_count: int,
        grant_founding: bool,
        expires_in_days: int,
        has_message_note: bool,
    ) -> None:
        audit_entry = AuditLog.from_change(
            entity_type="mcp_invite",
            entity_id=self._new_audit_id(),
            action="invites.preview",
            actor=actor,
            before=None,
            after={
                "recipient_count": recipient_count,
                "existing_user_count": existing_user_count,
                "grant_founding": grant_founding,
                "expires_in_days": expires_in_days,
                "has_message_note": has_message_note,
            },
        )
        self._audit_repo.write(audit_entry)

    @BaseService.measure_operation("mcp_invites.audit_send")
    def write_send_audit(
        self,
        *,
        actor: User,
        audit_id: str,
        recipient_count: int,
        sent_count: int,
        failed_count: int,
        grant_founding: bool,
        expires_in_days: int,
    ) -> None:
        audit_entry = AuditLog.from_change(
            entity_type="mcp_invite",
            entity_id=audit_id,
            action="invites.send",
            actor=actor,
            before=None,
            after={
                "recipient_count": recipient_count,
                "sent_count": sent_count,
                "failed_count": failed_count,
                "grant_founding": grant_founding,
                "expires_in_days": expires_in_days,
            },
        )
        self._audit_repo.write(audit_entry)

    def _new_audit_id(self) -> str:
        from ulid import ULID

        return str(ULID())
