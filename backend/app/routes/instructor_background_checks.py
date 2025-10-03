"""Instructor background check endpoints."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
from typing import cast

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.params import Path
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..api.dependencies.auth import get_current_user
from ..api.dependencies.database import get_db
from ..api.dependencies.services import get_background_check_service
from ..core.config import settings
from ..core.exceptions import ServiceException
from ..integrations.checkr_client import CheckrError
from ..models.instructor import InstructorProfile
from ..models.user import User
from ..repositories.instructor_profile_repository import InstructorProfileRepository
from ..schemas.bgc import (
    BackgroundCheckInviteResponse,
    BackgroundCheckStatusLiteral,
    BackgroundCheckStatusResponse,
)
from ..services.background_check_service import BackgroundCheckService

CONSENT_WINDOW = timedelta(hours=24)

logger = logging.getLogger(__name__)


class ConsentPayload(BaseModel):
    """Payload required to record FCRA consent."""

    consent_version: str = Field(..., min_length=1, max_length=50)


class ConsentResponse(BaseModel):
    """Acknowledgement returned after recording consent."""

    ok: bool = True


class MockStatusResponse(BaseModel):
    """Response returned by non-production mock status changers."""

    ok: bool = True
    status: BackgroundCheckStatusLiteral


router = APIRouter(
    prefix="/api/instructors/{instructor_id}/bgc",
    tags=["instructors", "background-checks"],
)


def _get_instructor_profile(
    instructor_id: str,
    repo: InstructorProfileRepository,
) -> InstructorProfile:
    profile = repo.get_by_id(instructor_id, load_relationships=False)
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Instructor not found")
    return profile


def _ensure_owner_or_admin(user: User, instructor_user_id: str) -> None:
    is_owner = user.id == instructor_user_id
    is_admin = any(getattr(role, "name", "") == "admin" for role in user.roles)
    if not (is_owner or is_admin):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")


def _status_literal(raw_status: str | None) -> BackgroundCheckStatusLiteral:
    status_value = (raw_status or "failed").lower().strip()
    if status_value not in {"pending", "review", "passed", "failed"}:
        return "failed"
    return cast(BackgroundCheckStatusLiteral, status_value)


@router.post("/invite", response_model=BackgroundCheckInviteResponse)
async def trigger_background_check_invite(
    instructor_id: str = Path(..., description="Instructor profile ULID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    background_check_service: BackgroundCheckService = Depends(get_background_check_service),
) -> BackgroundCheckInviteResponse:
    repo = InstructorProfileRepository(db)
    profile = _get_instructor_profile(instructor_id, repo)
    _ensure_owner_or_admin(current_user, profile.user_id)

    if background_check_service.config_error and settings.site_mode != "prod":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": (
                    "Background check configuration missing sandbox API key while CHECKR_FAKE=false. "
                    "Set CHECKR_FAKE=true (default) or provide CHECKR_API_KEY."
                ),
                "config_error": background_check_service.config_error,
            },
        )

    current_status = _status_literal(getattr(profile, "bgc_status", None))

    if current_status in {"pending", "review", "passed"}:
        return BackgroundCheckInviteResponse(
            status=current_status,
            report_id=getattr(profile, "bgc_report_id", None),
            already_in_progress=True,
        )

    latest_consent = repo.latest_consent(instructor_id)
    now = datetime.now(timezone.utc)
    consent_recent = bool(
        latest_consent
        and latest_consent.consented_at
        and latest_consent.consented_at >= now - CONSENT_WINDOW
    )

    logger.info(
        "BGC invite: instructor=%s consent_recent=%s consent_at=%s",
        instructor_id,
        consent_recent,
        getattr(latest_consent, "consented_at", None),
    )

    if not consent_recent:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "FCRA consent required",
                "code": "bgc_consent_required",
            },
        )

    try:
        invite_result = await background_check_service.invite(instructor_id)
    except ServiceException as exc:
        root_cause = exc.__cause__
        if (
            isinstance(root_cause, CheckrError)
            and "api key must be provided" in str(root_cause).lower()
            and settings.site_mode != "prod"
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "message": (
                        "Checkr API key must be provided to send background check invites. "
                        "Use CHECKR_FAKE=true for non-production or supply CHECKR_API_KEY."
                    ),
                },
            ) from exc

        raise

    return BackgroundCheckInviteResponse(
        status=invite_result["status"],
        report_id=invite_result.get("report_id"),
    )


@router.get("/status", response_model=BackgroundCheckStatusResponse)
async def get_background_check_status(
    instructor_id: str = Path(..., description="Instructor profile ULID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BackgroundCheckStatusResponse:
    repo = InstructorProfileRepository(db)
    profile = _get_instructor_profile(instructor_id, repo)
    _ensure_owner_or_admin(current_user, profile.user_id)

    status_value = _status_literal(getattr(profile, "bgc_status", None))

    latest_consent = repo.latest_consent(instructor_id)
    consent_recent_at = getattr(latest_consent, "consented_at", None)
    now = datetime.now(timezone.utc)
    consent_recent = bool(consent_recent_at and consent_recent_at >= now - CONSENT_WINDOW)

    return BackgroundCheckStatusResponse(
        status=status_value,
        report_id=getattr(profile, "bgc_report_id", None),
        completed_at=getattr(profile, "bgc_completed_at", None),
        env=getattr(profile, "bgc_env", "sandbox"),
        consent_recent=consent_recent,
        consent_recent_at=consent_recent_at,
    )


@router.post("/consent", response_model=ConsentResponse)
async def record_background_check_consent(
    payload: ConsentPayload,
    request: Request,
    instructor_id: str = Path(..., description="Instructor profile ULID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ConsentResponse:
    """Persist the instructor's consent acknowledgement for FCRA compliance."""

    repo = InstructorProfileRepository(db)
    profile = _get_instructor_profile(instructor_id, repo)
    _ensure_owner_or_admin(current_user, profile.user_id)

    ip_address = request.client.host if request.client else None
    repo.record_bgc_consent(
        instructor_id,
        consent_version=payload.consent_version,
        ip_address=ip_address,
    )

    return ConsentResponse()


def _ensure_non_production() -> None:
    if str(settings.site_mode).lower() == "prod":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Unavailable in production"
        )


@router.post("/mock/pass", response_model=MockStatusResponse)
async def mock_background_check_pass(
    instructor_id: str = Path(..., description="Instructor profile ULID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MockStatusResponse:
    """Non-production helper to mark background check as passed."""

    _ensure_non_production()
    repo = InstructorProfileRepository(db)
    profile = _get_instructor_profile(instructor_id, repo)
    _ensure_owner_or_admin(current_user, profile.user_id)

    profile.bgc_status = "passed"
    profile.bgc_completed_at = getattr(profile, "bgc_completed_at", None) or datetime.now(
        timezone.utc
    )

    return MockStatusResponse(status="passed")


@router.post("/mock/review", response_model=MockStatusResponse)
async def mock_background_check_review(
    instructor_id: str = Path(..., description="Instructor profile ULID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MockStatusResponse:
    """Non-production helper to mark background check as under review."""

    _ensure_non_production()
    repo = InstructorProfileRepository(db)
    profile = _get_instructor_profile(instructor_id, repo)
    _ensure_owner_or_admin(current_user, profile.user_id)

    profile.bgc_status = "review"
    profile.bgc_completed_at = None

    return MockStatusResponse(status="review")


@router.post("/mock/reset", response_model=MockStatusResponse)
async def mock_background_check_reset(
    instructor_id: str = Path(..., description="Instructor profile ULID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MockStatusResponse:
    """Non-production helper to reset background check metadata."""

    _ensure_non_production()
    repo = InstructorProfileRepository(db)
    profile = _get_instructor_profile(instructor_id, repo)
    _ensure_owner_or_admin(current_user, profile.user_id)

    profile.bgc_status = "failed"
    profile.bgc_completed_at = None
    profile.bgc_report_id = None

    return MockStatusResponse(status="failed")
