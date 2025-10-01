"""Instructor background check endpoints."""

from __future__ import annotations

from typing import cast

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.params import Path
from sqlalchemy.orm import Session

from ..api.dependencies.auth import get_current_user
from ..api.dependencies.database import get_db
from ..api.dependencies.services import get_background_check_service
from ..models.instructor import InstructorProfile
from ..models.user import User
from ..repositories.instructor_profile_repository import InstructorProfileRepository
from ..schemas.bgc import (
    BackgroundCheckInviteResponse,
    BackgroundCheckStatusLiteral,
    BackgroundCheckStatusResponse,
)
from ..services.background_check_service import BackgroundCheckService

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

    current_status = _status_literal(getattr(profile, "bgc_status", None))

    if current_status in {"pending", "review", "passed"}:
        return BackgroundCheckInviteResponse(
            status=current_status,
            report_id=getattr(profile, "bgc_report_id", None),
            already_in_progress=True,
        )

    invite_result = await background_check_service.invite(instructor_id)

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

    return BackgroundCheckStatusResponse(
        status=status_value,
        report_id=getattr(profile, "bgc_report_id", None),
        completed_at=getattr(profile, "bgc_completed_at", None),
        env=getattr(profile, "bgc_env", "sandbox"),
    )
