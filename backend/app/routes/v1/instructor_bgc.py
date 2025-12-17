# backend/app/routes/v1/instructor_bgc.py
"""
Instructor background check endpoints (v1).

Migrated from /api/instructors/{instructor_id}/bgc to /api/v1/instructors/{instructor_id}/bgc
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import logging
from typing import Any, cast

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from fastapi.params import Path
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ...api.dependencies.auth import get_current_user
from ...api.dependencies.database import get_db
from ...api.dependencies.services import get_background_check_service
from ...core.config import settings
from ...core.exceptions import ServiceException
from ...core.metrics import BGC_INVITES_TOTAL
from ...integrations.checkr_client import CheckrError
from ...models.instructor import InstructorProfile
from ...models.user import User
from ...repositories.instructor_profile_repository import InstructorProfileRepository
from ...schemas.bgc import (
    BackgroundCheckInviteRequest,
    BackgroundCheckInviteResponse,
    BackgroundCheckStatusLiteral,
    BackgroundCheckStatusResponse,
)
from ...schemas.instructor_background_checks_responses import (
    ConsentResponse,
    MockStatusResponse,
)
from ...services.background_check_service import BackgroundCheckService
from ...utils.strict import model_filter

CONSENT_WINDOW = timedelta(hours=24)

logger = logging.getLogger(__name__)


class ConsentPayload(BaseModel):
    """Payload required to record FCRA consent."""

    consent_version: str = Field(..., min_length=1, max_length=50)
    disclosure_version: str = Field(..., min_length=1, max_length=50)
    user_agent: str | None = Field(default=None, max_length=512)


# v1 router - mounted under /api/v1/instructors/{instructor_id}/bgc
router = APIRouter(
    tags=["instructors", "background-checks"],
)


def _bgc_invite_problem(
    detail: str,
    *,
    status_code: int,
    checkr_error: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "type": "about:blank",
        "title": "Unable to start background check",
        "status": status_code,
        "detail": detail,
        "code": "bgc_invite_failed",
    }
    if checkr_error:
        payload["checkr_error"] = {k: v for k, v in checkr_error.items() if v is not None}
    return payload


def _bgc_invite_rate_limited_problem() -> dict[str, Any]:
    return {
        "type": "about:blank",
        "title": "Background check recently requested",
        "status": status.HTTP_429_TOO_MANY_REQUESTS,
        "detail": "You recently started a background check. Please wait up to 24 hours before trying again.",
        "code": "bgc_invite_rate_limited",
    }


def _checkr_auth_problem(detail: str | None = None) -> dict[str, Any]:
    return {
        "type": "about:blank",
        "title": "Checkr authentication failed",
        "status": status.HTTP_400_BAD_REQUEST,
        "detail": detail
        or "Checkr API key is invalid or not authorized for the configured environment.",
        "code": "checkr_auth_error",
    }


def _invalid_work_location_problem(
    *,
    zip_code: str | None = None,
    reason: str | None = None,
    provider: str | None = None,
    provider_status: str | None = None,
) -> dict[str, Any]:
    detail = "We couldn't verify your primary teaching ZIP code. Please check it and try again."
    if zip_code:
        detail = (
            f"We couldn't verify your primary teaching ZIP code ({zip_code}). "
            "Please check it and try again."
        )
    debug: dict[str, Any] = {}
    if zip_code:
        debug["zip"] = zip_code
    if reason:
        debug["reason"] = reason
    if provider:
        debug["provider"] = provider
    if provider_status:
        debug["provider_status"] = provider_status
    payload = {
        "type": "about:blank",
        "title": "Invalid work location",
        "status": status.HTTP_400_BAD_REQUEST,
        "detail": detail,
        "code": "invalid_work_location",
    }
    if debug:
        payload["debug"] = debug
    return payload


def _geocoding_provider_problem(provider_error: dict[str, Any] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "type": "about:blank",
        "title": "Location lookup unavailable",
        "status": status.HTTP_400_BAD_REQUEST,
        "detail": "We couldn't reach our address verification service. Please try again later.",
        "code": "geocoding_provider_error",
    }
    if provider_error:
        payload["provider_error"] = {k: v for k, v in provider_error.items() if v is not None}
    return payload


def _clean_str(value: Any) -> str | None:
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
    return None


def _checkr_work_location_problem() -> dict[str, Any]:
    return {
        "type": "about:blank",
        "title": "Checkr work location error",
        "status": status.HTTP_400_BAD_REQUEST,
        "detail": (
            "Background check configuration error: work location could not be accepted by our provider. "
            "Please contact support."
        ),
        "code": "checkr_work_location_error",
    }


def _checkr_package_problem() -> dict[str, Any]:
    return {
        "type": "about:blank",
        "title": "Checkr package misconfigured",
        "status": status.HTTP_400_BAD_REQUEST,
        "detail": (
            "The configured Checkr package slug does not exist in the current Checkr environment. "
            "Please update CHECKR_DEFAULT_PACKAGE (or equivalent) to a valid slug from /v1/packages."
        ),
        "code": "checkr_package_not_found",
    }


def _is_package_not_found_error(err: CheckrError) -> bool:
    if err.status_code != status.HTTP_404_NOT_FOUND:
        return False
    body = getattr(err, "error_body", None)
    if isinstance(body, dict):
        for key in ("error", "message", "detail"):
            value = body.get(key)
            if isinstance(value, str) and "package not found" in value.lower():
                return True
    if isinstance(body, str) and "package not found" in body.lower():
        return True
    if "package not found" in str(err).lower():
        return True
    return False


def _is_work_location_error(err: CheckrError) -> bool:
    if err.status_code not in {
        status.HTTP_400_BAD_REQUEST,
        getattr(status, "HTTP_422_UNPROCESSABLE_CONTENT", 422),
    }:
        return False
    body = getattr(err, "error_body", None)
    needles = ("work_location", "work_locations")
    if isinstance(body, dict):
        for value in body.values():
            if isinstance(value, str) and any(token in value.lower() for token in needles):
                return True
    if isinstance(body, str) and any(token in body.lower() for token in needles):
        return True
    if any(token in str(err).lower() for token in needles):
        return True
    return False


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
    is_admin = user.is_admin
    if not (is_owner or is_admin):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")


def _status_literal(raw_status: str | None) -> BackgroundCheckStatusLiteral:
    status_value = (raw_status or "failed").lower().strip()
    if status_value not in {"pending", "review", "consider", "passed", "failed", "canceled"}:
        return "failed"
    return cast(BackgroundCheckStatusLiteral, status_value)


@router.post(
    "/{instructor_id}/bgc/invite",
    response_model=BackgroundCheckInviteResponse,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "User is not authorized to access this resource"},
        404: {"description": "Instructor not found"},
    },
)
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
    hosted_workflow = getattr(settings, "checkr_hosted_workflow", None)
    package_slug = (
        payload.package_slug
        or getattr(background_check_service, "package", None)
        or getattr(settings, "checkr_package", None)
    )

    logger.debug(
        "BGC invite package resolution",
        extra={
            "evt": "bgc_invite_package_resolution",
            "instructor_id": instructor_id,
            "payload_package": payload.package_slug,
            "service_package": getattr(background_check_service, "package", None),
            "settings_package": getattr(settings, "checkr_package", None),
            "resolved_package": package_slug,
        },
    )

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
        problem = _bgc_invite_rate_limited_problem()
        problem["instance"] = f"/api/v1/instructors/{instructor_id}/bgc/invite"
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=problem,
        )
    logger.info(
        "Background check invite begin",
        extra={
            "evt": "bgc_invite",
            "marker": "invite:begin",
            "instructor_id": instructor_id,
            "package": package_slug,
            "hosted_workflow": hosted_workflow,
        },
    )

    try:
        invite_result = await asyncio.to_thread(
            background_check_service.invite,
            instructor_id,
            package_override=payload.package_slug,
        )
    except ServiceException as exc:
        if exc.code == "invalid_work_location":
            details = exc.details if isinstance(exc.details, dict) else {}
            problem = _invalid_work_location_problem(
                zip_code=_clean_str(details.get("zip_code")),
                reason=_clean_str(details.get("reason")),
                provider=_clean_str(details.get("provider")),
                provider_status=_clean_str(details.get("provider_status")),
            )
            problem["instance"] = f"/api/v1/instructors/{instructor_id}/bgc/invite"
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=problem,
            )
        if exc.code == "geocoding_provider_error":
            details = exc.details if isinstance(exc.details, dict) else {}
            provider_error = {
                "provider": _clean_str(details.get("provider")),
                "status": _clean_str(details.get("provider_status")),
                "zip": _clean_str(details.get("zip_code")),
                "error_message": _clean_str(details.get("error_message")),
            }
            problem = _geocoding_provider_problem(provider_error)
            problem["instance"] = f"/api/v1/instructors/{instructor_id}/bgc/invite"
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=problem,
            )
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

        if isinstance(root_cause, CheckrError):
            if root_cause.status_code == status.HTTP_401_UNAUTHORIZED:
                logger.error(
                    "Background check invite failed due to Checkr authentication",
                    extra={
                        "evt": "bgc_invite",
                        "instructor_id": instructor_id,
                        "outcome": "error",
                        "error": root_cause.error_type or str(root_cause),
                    },
                )
                BGC_INVITES_TOTAL.labels(outcome="error").inc()
                problem = _checkr_auth_problem()
                problem["instance"] = f"/api/v1/instructors/{instructor_id}/bgc/invite"
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=problem)

            if _is_package_not_found_error(root_cause):
                logger.error(
                    "Background check invite failed due to missing package",
                    extra={
                        "evt": "bgc_invite",
                        "instructor_id": instructor_id,
                        "outcome": "error",
                        "error": root_cause.error_type or str(root_cause),
                    },
                )
                BGC_INVITES_TOTAL.labels(outcome="error").inc()
                problem = _checkr_package_problem()
                problem["instance"] = f"/api/v1/instructors/{instructor_id}/bgc/invite"
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=problem)

            if _is_work_location_error(root_cause):
                logger.error(
                    "Background check invite failed due to Checkr work location error",
                    extra={
                        "evt": "bgc_invite",
                        "instructor_id": instructor_id,
                        "outcome": "error",
                        "error": root_cause.error_type or str(root_cause),
                    },
                )
                BGC_INVITES_TOTAL.labels(outcome="error").inc()
                problem = _checkr_work_location_problem()
                problem["instance"] = f"/api/v1/instructors/{instructor_id}/bgc/invite"
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=problem)

            checkr_payload = {
                "http_status": root_cause.status_code,
                "type": root_cause.error_type,
                "message": str(root_cause),
            }
            logger.warning(
                "Background check invite failed: Checkr error",
                extra={
                    "evt": "bgc_invite",
                    "marker": "invite:error",
                    "instructor_id": instructor_id,
                    "package": package_slug,
                    "checkr_status": root_cause.status_code,
                    "checkr_type": root_cause.error_type,
                },
            )
            BGC_INVITES_TOTAL.labels(outcome="error").inc()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=_bgc_invite_problem(
                    "Checkr invitation failed",
                    status_code=status.HTTP_400_BAD_REQUEST,
                    checkr_error=checkr_payload,
                )
                | {"instance": f"/api/v1/instructors/{instructor_id}/bgc/invite"},
            )

        logger.exception(
            "Background check invite failed unexpectedly",
            extra={
                "evt": "bgc_invite",
                "marker": "invite:error",
                "instructor_id": instructor_id,
                "package": package_slug,
            },
        )
        BGC_INVITES_TOTAL.labels(outcome="error").inc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_bgc_invite_problem(
                "Unable to start background check",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
            | {"instance": f"/api/v1/instructors/{instructor_id}/bgc/invite"},
        )

    repo.set_bgc_invited_at(instructor_id, invite_time)
    logger.info(
        "Background check invite success",
        extra={
            "evt": "bgc_invite",
            "marker": "invite:success",
            "instructor_id": instructor_id,
            "package": package_slug,
            "hosted_workflow": hosted_workflow,
        },
    )
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


@router.post(
    "/{instructor_id}/bgc/recheck",
    response_model=BackgroundCheckInviteResponse,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "User is not authorized to access this resource"},
        404: {"description": "Instructor not found"},
    },
)
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
        invite_result = await asyncio.to_thread(background_check_service.invite, instructor_id)
    except ServiceException as exc:
        if exc.code == "invalid_work_location":
            details = exc.details if isinstance(exc.details, dict) else {}
            problem = _invalid_work_location_problem(
                zip_code=_clean_str(details.get("zip_code")),
                reason=_clean_str(details.get("reason")),
                provider=_clean_str(details.get("provider")),
                provider_status=_clean_str(details.get("provider_status")),
            )
            problem["instance"] = f"/api/v1/instructors/{instructor_id}/bgc/recheck"
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=problem,
            )
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

        if isinstance(root_cause, CheckrError):
            if root_cause.status_code == status.HTTP_401_UNAUTHORIZED:
                logger.error(
                    "Background check re-check failed due to Checkr authentication",
                    extra={
                        "evt": "bgc_recheck",
                        "instructor_id": instructor_id,
                        "outcome": "error",
                        "error": root_cause.error_type or str(root_cause),
                    },
                )
                BGC_INVITES_TOTAL.labels(outcome="error").inc()
                problem = _checkr_auth_problem()
                problem["instance"] = f"/api/v1/instructors/{instructor_id}/bgc/recheck"
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=problem)

            if _is_package_not_found_error(root_cause):
                logger.error(
                    "Background check re-check failed due to missing package",
                    extra={
                        "evt": "bgc_recheck",
                        "instructor_id": instructor_id,
                        "outcome": "error",
                        "error": root_cause.error_type or str(root_cause),
                    },
                )
                BGC_INVITES_TOTAL.labels(outcome="error").inc()
                problem = _checkr_package_problem()
                problem["instance"] = f"/api/v1/instructors/{instructor_id}/bgc/recheck"
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=problem,
                )

            if _is_work_location_error(root_cause):
                logger.error(
                    "Background check re-check failed due to Checkr work location error",
                    extra={
                        "evt": "bgc_recheck",
                        "instructor_id": instructor_id,
                        "outcome": "error",
                        "error": root_cause.error_type or str(root_cause),
                    },
                )
                BGC_INVITES_TOTAL.labels(outcome="error").inc()
                problem = _checkr_work_location_problem()
                problem["instance"] = f"/api/v1/instructors/{instructor_id}/bgc/recheck"
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=problem,
                )

            checkr_payload = {
                "http_status": root_cause.status_code,
                "type": root_cause.error_type,
                "message": str(root_cause),
            }
            logger.warning(
                "Background check re-check failed: Checkr error",
                extra={
                    "evt": "bgc_recheck",
                    "instructor_id": instructor_id,
                    "outcome": "error",
                    "checkr_status": root_cause.status_code,
                    "checkr_type": root_cause.error_type,
                },
            )
            BGC_INVITES_TOTAL.labels(outcome="error").inc()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=_bgc_invite_problem(
                    "Checkr invitation failed",
                    status_code=status.HTTP_400_BAD_REQUEST,
                    checkr_error=checkr_payload,
                ),
            )
        if exc.code == "geocoding_provider_error":
            details = exc.details if isinstance(exc.details, dict) else {}
            provider_error = {
                "provider": _clean_str(details.get("provider")),
                "status": _clean_str(details.get("provider_status")),
                "zip": _clean_str(details.get("zip_code")),
                "error_message": _clean_str(details.get("error_message")),
            }
            problem = _geocoding_provider_problem(provider_error)
            problem["instance"] = f"/api/v1/instructors/{instructor_id}/bgc/recheck"
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=problem,
            )

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


@router.get(
    "/{instructor_id}/bgc/status",
    response_model=BackgroundCheckStatusResponse,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "User is not authorized to access this resource"},
        404: {"description": "Instructor not found"},
    },
)
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
        eta=getattr(profile, "bgc_eta", None),
        bgc_includes_canceled=bool(getattr(profile, "bgc_includes_canceled", False)),
    )


@router.post(
    "/{instructor_id}/bgc/consent",
    response_model=ConsentResponse,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "User is not authorized to access this resource"},
        404: {"description": "Instructor not found"},
    },
)
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


@router.post(
    "/{instructor_id}/bgc/mock/pass",
    response_model=MockStatusResponse,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "User is not authorized to access this resource"},
        404: {"description": "Instructor not found"},
    },
)
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


@router.post(
    "/{instructor_id}/bgc/mock/review",
    response_model=MockStatusResponse,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "User is not authorized to access this resource"},
        404: {"description": "Instructor not found"},
    },
)
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


@router.post(
    "/{instructor_id}/bgc/mock/reset",
    response_model=MockStatusResponse,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "User is not authorized to access this resource"},
        404: {"description": "Instructor not found"},
    },
)
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
