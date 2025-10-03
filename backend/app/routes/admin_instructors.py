"""Admin instructor detail endpoints."""

from __future__ import annotations

from datetime import datetime
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..api.dependencies.auth import require_admin
from ..api.dependencies.repositories import get_instructor_repo
from ..repositories.instructor_profile_repository import InstructorProfileRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/instructors", tags=["admin-instructors"])


class AdminInstructorDetailResponse(BaseModel):
    id: str
    name: str
    email: str
    is_live: bool
    bgc_status: str | None
    bgc_report_id: str | None
    bgc_completed_at: datetime | None
    consent_recent_at: datetime | None
    created_at: datetime | None
    updated_at: datetime | None


@router.get("/{instructor_id}", response_model=AdminInstructorDetailResponse)
async def admin_instructor_detail(
    instructor_id: str,
    repo: InstructorProfileRepository = Depends(get_instructor_repo),
    _: None = Depends(require_admin),
) -> AdminInstructorDetailResponse:
    """Return administrative instructor detail including consent recency."""

    profile = repo.get_by_id_join_user(instructor_id)
    if not profile:
        raise HTTPException(status_code=404, detail="instructor not found")

    user = getattr(profile, "user", None)
    raw_full_name = getattr(user, "full_name", None) if user is not None else None
    if not raw_full_name:
        first = (getattr(user, "first_name", "") or "").strip() if user is not None else ""
        last = (getattr(user, "last_name", "") or "").strip() if user is not None else ""
        raw_full_name = " ".join(part for part in [first, last] if part).strip()

    email = (getattr(user, "email", "") or "").strip() if user is not None else ""

    consent = repo.latest_consent(profile.id)
    consented_at: Optional[datetime] = getattr(consent, "consented_at", None)

    return AdminInstructorDetailResponse(
        id=profile.id,
        name=raw_full_name or "",
        email=email,
        is_live=bool(getattr(profile, "is_live", False)),
        bgc_status=getattr(profile, "bgc_status", None),
        bgc_report_id=getattr(profile, "bgc_report_id", None),
        bgc_completed_at=getattr(profile, "bgc_completed_at", None),
        consent_recent_at=consented_at,
        created_at=getattr(profile, "created_at", None),
        updated_at=getattr(profile, "updated_at", None),
    )
