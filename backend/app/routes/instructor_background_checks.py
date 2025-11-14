"""Instructor background check endpoints."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
from typing import cast

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from fastapi.params import Path
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..api.dependencies.auth import get_current_user
from ..api.dependencies.database import get_db
from ..api.dependencies.services import get_background_check_service
from ..core.config import settings
from ..core.exceptions import ServiceException
from ..core.metrics import BGC_INVITES_TOTAL
from ..integrations.checkr_client import CheckrError
from ..models.instructor import InstructorProfile
from ..models.user import User
from ..repositories.instructor_profile_repository import InstructorProfileRepository
from ..schemas.bgc import (
    BackgroundCheckInviteRequest,
    BackgroundCheckInviteResponse,
    BackgroundCheckStatusLiteral,
    BackgroundCheckStatusResponse,
)
from ..schemas.instructor_background_checks_responses import (
    ConsentResponse,
    MockStatusResponse,
)
from ..services.background_check_service import BackgroundCheckService
from ..utils.strict import model_filter

CONSENT_WINDOW = timedelta(hours=24)

logger = logging.getLogger(__name__)


class ConsentPayload(BaseModel):
    """Payload required to record FCRA consent."""

    consent_version: str = Field(..., min_length=1, max_length=50)
    disclosure_version: str = Field(..., min_length=1, max_length=50)
    user_agent: str | None = Field(default=None, max_length=512)


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
    if status_value not in {"pending", "review", "consider", "passed", "failed"}:
        return "failed"
    return cast(BackgroundCheckStatusLiteral, status_value)


@router.post("/invite", response_model=BackgroundCheckInviteResponse)
async def trigger_background_check_invite(
    payload: BackgroundCheckInviteRequest = Body(
        default_factory=BackgroundCheckInviteRequest,
        description="Optional configuration for the Checkr invitation",
    ),
    instructor_id: str = Path(..., description="Instructor profile ULID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    background_check_service: BackgroundCheckService = Depends(get_background_check_service),
) -> BackgroundCheckInviteResponse:
    repo = InstructorProfileRepository(db)
    profile = _get_instructor_profile(instructor_id, repo)
    _ensure_owner_or_admin(current_user, profile.user_id)

    if background_check_service.config_error and settings.site_mode != "prod":
        logger.error(
            "Background check invite blocked due to configuration error",
            extra={
                "evt": "bgc_invite",
                "instructor_id": instructor_id,
                "outcome": "error",
                "config_error": background_check_service.config_error,
            },
        )
        BGC_INVITES_TOTAL.labels(outcome="error").inc()
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

    if current_status in {"pending", "review", "consider", "passed"}:
        response = BackgroundCheckInviteResponse(
            status=current_status,
            report_id=getattr(profile, "bgc_report_id", None),
            already_in_progress=True,
        )
        logger.info(
            "Background check invite skipped; already in progress",
            extra={
                "evt": "bgc_invite",
                "instructor_id": instructor_id,
                "outcome": "ok",
                "already_in_progress": True,
                "status": current_status,
            },
        )
        BGC_INVITES_TOTAL.labels(outcome="ok").inc()
        return response

    latest_consent = repo.latest_consent(instructor_id)
    now = datetime.now(timezone.utc)
    consent_recent = bool(
        latest_consent
        and latest_consent.consented_at
        and latest_consent.consented_at >= now - CONSENT_WINDOW
    )

    if not consent_recent:
        logger.info(
            "Background check invite blocked; consent required",
            extra={
                "evt": "bgc_invite",
                "instructor_id": instructor_id,
                "outcome": "consent_required",
            },
        )
        BGC_INVITES_TOTAL.labels(outcome="consent_required").inc()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "FCRA consent required",
                "code": "bgc_consent_required",
            },
        )

    invite_time = datetime.now(timezone.utc)
    if getattr(
        profile, "bgc_invited_at", None
    ) and invite_time - profile.bgc_invited_at < timedelta(hours=24):
        logger.info(
            "Background check invite rate limited",
            extra={
                "evt": "bgc_invite",
                "instructor_id": instructor_id,
                "outcome": "rate_limited",
            },
        )
        BGC_INVITES_TOTAL.labels(outcome="rate_limited").inc()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Invite rate-limited; try again later",
        )

    try:
        invite_result = await background_check_service.invite(
            instructor_id,
            package_override=payload.package_slug,
        )
    except ServiceException as exc:
        root_cause = exc.__cause__
        if (
            isinstance(root_cause, CheckrError)
            and "api key must be provided" in str(root_cause).lower()
            and settings.site_mode != "prod"
        ):
            logger.error(
                "Background check invite failed due to missing API key",
                extra={
                    "evt": "bgc_invite",
                    "instructor_id": instructor_id,
                    "outcome": "error",
                    "error": str(root_cause),
                },
            )
            BGC_INVITES_TOTAL.labels(outcome="error").inc()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "message": (
                        "Checkr API key must be provided to send background check invites. "
                        "Use CHECKR_FAKE=true for non-production or supply CHECKR_API_KEY."
                    ),
                },
            ) from exc

        logger.error(
            "Background check invite failed",
            extra={
                "evt": "bgc_invite",
                "instructor_id": instructor_id,
                "outcome": "error",
                "error": str(exc),
            },
        )
        BGC_INVITES_TOTAL.labels(outcome="error").inc()
        raise

    repo.set_bgc_invited_at(instructor_id, invite_time)

    logger.info(
        "Background check invite sent",
        extra={
            "evt": "bgc_invite",
            "instructor_id": instructor_id,
            "outcome": "ok",
        },
    )
    BGC_INVITES_TOTAL.labels(outcome="ok").inc()

    return BackgroundCheckInviteResponse(
        status=invite_result["status"],
        report_id=invite_result.get("report_id"),
        candidate_id=invite_result.get("candidate_id"),
        invitation_id=invite_result.get("invitation_id"),
    )


@router.post("/recheck", response_model=BackgroundCheckInviteResponse)
async def trigger_background_check_recheck(
    instructor_id: str = Path(..., description="Instructor profile ULID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    background_check_service: BackgroundCheckService = Depends(get_background_check_service),
) -> BackgroundCheckInviteResponse:
    repo = InstructorProfileRepository(db)
    profile = _get_instructor_profile(instructor_id, repo)
    _ensure_owner_or_admin(current_user, profile.user_id)

    if background_check_service.config_error and settings.site_mode != "prod":
        logger.error(
            "Background check re-check blocked due to configuration error",
            extra={
                "evt": "bgc_recheck",
                "instructor_id": instructor_id,
                "outcome": "error",
                "config_error": background_check_service.config_error,
            },
        )
        BGC_INVITES_TOTAL.labels(outcome="error").inc()
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

    latest_consent = repo.latest_consent(instructor_id)
    now = datetime.now(timezone.utc)
    consent_recent = bool(
        latest_consent
        and latest_consent.consented_at
        and latest_consent.consented_at >= now - CONSENT_WINDOW
    )

    if not consent_recent:
        logger.info(
            "Background check re-check blocked; consent required",
            extra={
                "evt": "bgc_recheck",
                "instructor_id": instructor_id,
                "outcome": "consent_required",
            },
        )
        BGC_INVITES_TOTAL.labels(outcome="consent_required").inc()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "FCRA consent required",
                "code": "bgc_consent_required",
            },
        )

    invite_time = datetime.now(timezone.utc)
    invited_at = getattr(profile, "bgc_invited_at", None)
    if invited_at is not None and invite_time - invited_at < timedelta(hours=24):
        retry_after_seconds = int(
            (timedelta(hours=24) - (invite_time - invited_at)).total_seconds()
        )
        logger.info(
            "Background check re-check rate limited",
            extra={
                "evt": "bgc_recheck",
                "instructor_id": instructor_id,
                "outcome": "rate_limited",
            },
        )
        BGC_INVITES_TOTAL.labels(outcome="rate_limited").inc()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "bgc_recheck_rate_limited",
                "message": "Re-check rate limited; try again later.",
                "retry_after_seconds": retry_after_seconds,
            },
        )

    current_status = _status_literal(getattr(profile, "bgc_status", None))
    if current_status in {"pending", "review", "consider"}:
        logger.info(
            "Background check re-check skipped; already in progress",
            extra={
                "evt": "bgc_recheck",
                "instructor_id": instructor_id,
                "outcome": "recheck_ok",
                "already_in_progress": True,
                "status": current_status,
            },
        )
        BGC_INVITES_TOTAL.labels(outcome="recheck_ok").inc()
        return BackgroundCheckInviteResponse(
            status=current_status,
            report_id=getattr(profile, "bgc_report_id", None),
            already_in_progress=True,
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
            logger.error(
                "Background check re-check failed due to missing API key",
                extra={
                    "evt": "bgc_recheck",
                    "instructor_id": instructor_id,
                    "outcome": "error",
                    "error": str(root_cause),
                },
            )
            BGC_INVITES_TOTAL.labels(outcome="error").inc()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "message": (
                        "Checkr API key must be provided to send background check re-checks. "
                        "Use CHECKR_FAKE=true for non-production or supply CHECKR_API_KEY."
                    ),
                },
            ) from exc

        logger.error(
            "Background check re-check failed",
            extra={
                "evt": "bgc_recheck",
                "instructor_id": instructor_id,
                "outcome": "error",
                "error": str(exc),
            },
        )
        BGC_INVITES_TOTAL.labels(outcome="error").inc()
        raise

    repo.set_bgc_invited_at(instructor_id, invite_time)

    logger.info(
        "Background check re-check started",
        extra={
            "evt": "bgc_recheck",
            "instructor_id": instructor_id,
            "outcome": "recheck_ok",
        },
    )
    BGC_INVITES_TOTAL.labels(outcome="recheck_ok").inc()

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
    valid_until = getattr(profile, "bgc_valid_until", None)
    expires_in_days = (
        (valid_until - now).days if valid_until is not None and valid_until > now else None
    )
    is_expired = bool(valid_until is not None and valid_until <= now)

    return BackgroundCheckStatusResponse(
        status=status_value,
        report_id=getattr(profile, "bgc_report_id", None),
        completed_at=getattr(profile, "bgc_completed_at", None),
        env=getattr(profile, "bgc_env", "sandbox"),
        consent_recent=consent_recent,
        consent_recent_at=consent_recent_at,
        valid_until=valid_until,
        expires_in_days=expires_in_days,
        is_expired=is_expired,
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
    user_agent = payload.user_agent or request.headers.get("user-agent")
    consent = repo.record_bgc_consent(
        instructor_id,
        consent_version=payload.disclosure_version,
        ip_address=ip_address,
    )

    logger.info(
        "Background check disclosure authorized",
        extra={
            "evt": "bgc_consent",
            "instructor_id": instructor_id,
            "consent_version": payload.consent_version,
            "disclosure_version": payload.disclosure_version,
            "user_agent": user_agent,
            "consent_record_id": consent.id,
        },
    )

    response_payload = {"ok": True}
    return ConsentResponse(**model_filter(ConsentResponse, response_payload))


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

    response_payload = {"status": "passed"}
    return MockStatusResponse(**model_filter(MockStatusResponse, response_payload))


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

    response_payload = {"status": "review"}
    return MockStatusResponse(**model_filter(MockStatusResponse, response_payload))


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

    response_payload = {"status": "failed"}
    return MockStatusResponse(**model_filter(MockStatusResponse, response_payload))
