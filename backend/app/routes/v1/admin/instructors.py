# backend/app/routes/v1/admin/instructors.py
"""Admin instructor detail endpoints (v1)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies.auth import require_admin
from app.api.dependencies.repositories import get_instructor_repo
from app.repositories.instructor_profile_repository import InstructorProfileRepository
from app.schemas.admin_instructor_responses import (
    AdminInstructorDetailResponse,
    FoundingCountResponse,
)
from app.services.config_service import ConfigService
from app.utils.strict import model_filter

logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin-instructors"])


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

    now = datetime.now(timezone.utc)
    valid_until = getattr(profile, "bgc_valid_until", None)
    expires_in_days = (
        (valid_until - now).days if valid_until is not None and valid_until > now else None
    )
    is_expired = bool(valid_until is not None and valid_until <= now)

    response_payload = {
        "id": profile.id,
        "name": raw_full_name or "",
        "email": email,
        "is_live": bool(getattr(profile, "is_live", False)),
        "bgc_status": getattr(profile, "bgc_status", None),
        "bgc_includes_canceled": bool(getattr(profile, "bgc_includes_canceled", False)),
        "bgc_report_id": getattr(profile, "bgc_report_id", None),
        "bgc_completed_at": getattr(profile, "bgc_completed_at", None),
        "consent_recent_at": consented_at,
        "created_at": getattr(profile, "created_at", None),
        "updated_at": getattr(profile, "updated_at", None),
        "bgc_valid_until": valid_until,
        "bgc_expires_in_days": expires_in_days,
        "bgc_is_expired": is_expired,
        "bgc_in_dispute": bool(getattr(profile, "bgc_in_dispute", False)),
        "bgc_dispute_note": getattr(profile, "bgc_dispute_note", None),
        "bgc_dispute_opened_at": getattr(profile, "bgc_dispute_opened_at", None),
        "bgc_dispute_resolved_at": getattr(profile, "bgc_dispute_resolved_at", None),
    }

    return AdminInstructorDetailResponse(
        **model_filter(AdminInstructorDetailResponse, response_payload)
    )


@router.get("/founding/count", response_model=FoundingCountResponse)
async def founding_instructor_count(
    repo: InstructorProfileRepository = Depends(get_instructor_repo),
    _: None = Depends(require_admin),
) -> FoundingCountResponse:
    """Return founding instructor count and remaining capacity."""

    config_service = ConfigService(repo.db)
    pricing_config, _ = await asyncio.to_thread(config_service.get_pricing_config)
    cap_raw = pricing_config.get("founding_instructor_cap", 100)
    try:
        cap = int(cap_raw)
    except (TypeError, ValueError):
        cap = 100

    count = await asyncio.to_thread(repo.count_founding_instructors)
    remaining = max(0, cap - count)
    response_payload = {"count": count, "cap": cap, "remaining": remaining}
    return FoundingCountResponse(**model_filter(FoundingCountResponse, response_payload))
