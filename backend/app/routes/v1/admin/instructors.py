# backend/app/routes/v1/admin/instructors.py
"""Admin instructor detail endpoints (v1)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.dependencies.auth import require_admin
from app.api.dependencies.repositories import get_instructor_repo
from app.models.instructor import InstructorProfile
from app.models.user import User
from app.repositories.instructor_profile_repository import InstructorProfileRepository
from app.schemas.admin_instructor_responses import (
    AdminInstructorDetailResponse,
    FoundingCountResponse,
)
from app.services.audit_service import AuditService
from app.services.config_service import ConfigService
from app.utils.strict import model_filter

logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin-instructors"])


def _build_admin_instructor_detail_response(
    profile: InstructorProfile,
    repo: InstructorProfileRepository,
) -> AdminInstructorDetailResponse:
    """Build the shared admin instructor detail response payload."""
    user = getattr(profile, "user", None)
    raw_full_name = getattr(user, "full_name", None) if user is not None else None
    if not raw_full_name:
        first = (getattr(user, "first_name", "") or "").strip() if user is not None else ""
        last = (getattr(user, "last_name", "") or "").strip() if user is not None else ""
        raw_full_name = " ".join(part for part in [first, last] if part).strip()

    email = (getattr(user, "email", "") or "").strip() if user is not None else ""

    consent = repo.latest_consent(profile.id)
    consented_at: Optional[datetime] = getattr(consent, "consented_at", None)

    now = datetime.now(timezone.utc)
    valid_until = profile.bgc_valid_until
    expires_in_days = (
        (valid_until - now).days if valid_until is not None and valid_until > now else None
    )
    is_expired = bool(valid_until is not None and valid_until <= now)

    response_payload = {
        "id": profile.id,
        "name": raw_full_name or "",
        "email": email,
        "is_live": bool(getattr(profile, "is_live", False)),
        "bgc_name_mismatch": bool(getattr(profile, "bgc_name_mismatch", False)),
        "verified_dob": getattr(profile, "verified_dob", None),
        "bgc_submitted_dob": getattr(profile, "bgc_submitted_dob", None),
        "bgc_status": profile.bgc_status,
        "bgc_includes_canceled": bool(profile.bgc_includes_canceled),
        "bgc_report_id": profile.bgc_report_id,
        "bgc_completed_at": profile.bgc_completed_at,
        "consent_recent_at": consented_at,
        "created_at": getattr(profile, "created_at", None),
        "updated_at": getattr(profile, "updated_at", None),
        "bgc_valid_until": valid_until,
        "bgc_expires_in_days": expires_in_days,
        "bgc_is_expired": is_expired,
        "bgc_in_dispute": bool(profile.bgc_in_dispute),
        "bgc_dispute_note": profile.bgc_dispute_note,
        "bgc_dispute_opened_at": profile.bgc_dispute_opened_at,
        "bgc_dispute_resolved_at": profile.bgc_dispute_resolved_at,
    }

    return AdminInstructorDetailResponse(
        **model_filter(AdminInstructorDetailResponse, response_payload)
    )


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

    return _build_admin_instructor_detail_response(profile, repo)


@router.post("/{instructor_id}/clear-bgc-mismatch", response_model=AdminInstructorDetailResponse)
async def clear_bgc_mismatch(
    instructor_id: str,
    request: Request,
    repo: InstructorProfileRepository = Depends(get_instructor_repo),
    current_admin: User = Depends(require_admin),
) -> AdminInstructorDetailResponse:
    """Clear a BGC name mismatch flag after admin review."""

    profile = repo.get_by_id_join_user(instructor_id)
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="instructor not found")

    repo.update(profile.id, bgc_name_mismatch=False)
    repo.commit()
    refreshed = repo.get_by_id_join_user(profile.id)
    if not refreshed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="instructor not found")

    try:
        AuditService(repo.db).log(
            action="instructor.clear_bgc_mismatch",
            resource_type="instructor",
            resource_id=profile.id,
            actor=current_admin,
            actor_type="user",
            description="Cleared background check name mismatch flag",
            metadata={"bgc_name_mismatch": False},
            request=request,
        )
    except Exception:
        logger.warning("Audit log write failed for clearing BGC mismatch", exc_info=True)

    return _build_admin_instructor_detail_response(refreshed, repo)


@router.post("/{instructor_id}/reset-bgc", response_model=AdminInstructorDetailResponse)
async def reset_bgc(
    instructor_id: str,
    request: Request,
    repo: InstructorProfileRepository = Depends(get_instructor_repo),
    current_admin: User = Depends(require_admin),
) -> AdminInstructorDetailResponse:
    """Reset BGC state so an instructor can complete a fresh screening."""

    profile = repo.get_by_id_join_user(instructor_id)
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="instructor not found")
    if profile.is_live:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "Instructor is currently live. Set offline before resetting background check.",
                "code": "bgc_reset_live_block",
            },
        )

    repo.update(
        profile.id,
        bgc_name_mismatch=False,
        bgc_status=None,
        bgc_report_id=None,
        bgc_completed_at=None,
        bgc_report_result=None,
        bgc_valid_until=None,
        bgc_eta=None,
        bgc_invited_at=None,
        bgc_includes_canceled=False,
        bgc_in_dispute=False,
        bgc_dispute_note=None,
        bgc_dispute_opened_at=None,
        bgc_dispute_resolved_at=None,
        bgc_pre_adverse_notice_id=None,
        bgc_pre_adverse_sent_at=None,
        bgc_final_adverse_sent_at=None,
        bgc_review_email_sent_at=None,
        checkr_candidate_id=None,
        checkr_invitation_id=None,
        bgc_note=None,
        bgc_submitted_first_name=None,
        bgc_submitted_last_name=None,
        bgc_submitted_dob=None,
    )
    repo.commit()
    refreshed = repo.get_by_id_join_user(profile.id)
    if not refreshed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="instructor not found")

    try:
        AuditService(repo.db).log(
            action="instructor.reset_bgc",
            resource_type="instructor",
            resource_id=profile.id,
            actor=current_admin,
            actor_type="user",
            description="Reset instructor background check state",
            metadata={"bgc_status": None, "bgc_name_mismatch": False},
            request=request,
        )
    except Exception:
        logger.warning("Audit log write failed for resetting BGC", exc_info=True)

    return _build_admin_instructor_detail_response(refreshed, repo)


@router.get("/founding/count", response_model=FoundingCountResponse)
async def founding_instructor_count(
    repo: InstructorProfileRepository = Depends(get_instructor_repo),
    _: None = Depends(require_admin),
) -> FoundingCountResponse:
    """Return founding instructor count and remaining capacity."""

    config_service = ConfigService(repo.db)
    pricing_config, _updated_at = await asyncio.to_thread(config_service.get_pricing_config)
    cap_raw = pricing_config.get("founding_instructor_cap", 100)
    try:
        cap = int(cap_raw)
    except (TypeError, ValueError):
        cap = 100

    count = await asyncio.to_thread(repo.count_founding_instructors)
    remaining = max(0, cap - count)
    response_payload = {"count": count, "cap": cap, "remaining": remaining}
    return FoundingCountResponse(**model_filter(FoundingCountResponse, response_payload))
