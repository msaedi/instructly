"""Service for initiating Checkr background checks via hosted invitations."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional, TypedDict, cast

from sqlalchemy.orm import Session

from ..core.exceptions import NotFoundException, ServiceException
from ..integrations.checkr_client import CheckrClient, CheckrError
from ..repositories.instructor_profile_repository import InstructorProfileRepository
from ..schemas.bgc import BackgroundCheckStatusLiteral
from .base import BaseService


class InviteResult(TypedDict):
    status: BackgroundCheckStatusLiteral
    report_id: Optional[str]


class BackgroundCheckService(BaseService):
    """Coordinates Checkr interactions and instructor profile updates."""

    def __init__(
        self,
        db: Session,
        *,
        client: CheckrClient,
        repository: InstructorProfileRepository,
        package: str,
        env: str,
    ) -> None:
        super().__init__(db)
        self.client = client
        self.repository = repository
        self.package = package
        self.env = env

    @BaseService.measure_operation("bgc.invite")
    async def invite(self, instructor_id: str) -> InviteResult:
        """Create a Checkr candidate and hosted invitation for an instructor."""

        profile = self.repository.get_by_id(instructor_id, load_relationships=True)
        if not profile:
            raise NotFoundException(
                message="Instructor profile not found",
                code="INSTRUCTOR_NOT_FOUND",
                details={"instructor_id": instructor_id},
            )

        user = profile.user
        if not user:
            raise ServiceException("Instructor profile missing associated user")

        candidate_payload: Dict[str, Any] = {
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": user.email,
        }

        optional_fields: Dict[str, Optional[str]] = {
            "phone": getattr(user, "phone", None),
            "zipcode": getattr(user, "zip_code", None),
        }

        # Safely include optional fields supported by hosted invitations
        candidate_payload.update({key: value for key, value in optional_fields.items() if value})

        try:
            candidate = await self.client.create_candidate(**candidate_payload)
            candidate_id = candidate.get("id")
            if not candidate_id:
                raise ServiceException("Checkr candidate response missing identifier")

            invitation = await self.client.create_invitation(
                candidate_id=candidate_id,
                package=self.package,
            )
        except CheckrError as exc:
            details = {"status_code": exc.status_code} if exc.status_code else {}
            raise ServiceException(
                "Failed to initiate instructor background check", details=details
            ) from exc

        report_id = cast(Optional[str], invitation.get("report_id"))

        with self.transaction():
            self.repository.update_bgc(
                instructor_id,
                status="pending",
                report_id=report_id,
                env=self.env,
            )

        return {
            "status": "pending",
            "report_id": report_id,
        }

    @BaseService.measure_operation("bgc.webhook_update")
    def update_status_from_report(
        self,
        report_id: str,
        *,
        status: BackgroundCheckStatusLiteral,
        completed: bool,
    ) -> bool:
        """Update instructor profile fields based on a Checkr report event."""

        completed_at = datetime.now(timezone.utc) if completed else None

        with self.transaction():
            updated: int = self.repository.update_bgc_by_report_id(
                report_id,
                status=status,
                completed_at=completed_at,
            )

        if not updated:
            self.logger.info(
                "No instructor profile updated for Checkr report", extra={"report_id": report_id}
            )

        return updated > 0
