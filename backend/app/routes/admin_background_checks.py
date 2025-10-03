"""Admin endpoints for managing instructor background checks."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
from typing import Literal, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import selectinload

from ..api.dependencies.auth import require_admin
from ..api.dependencies.repositories import get_instructor_repo
from ..core.config import settings
from ..core.exceptions import RepositoryException
from ..repositories.instructor_profile_repository import InstructorProfileRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/bgc", tags=["admin-bgc"])

CONSENT_WINDOW = timedelta(hours=24)
DEFAULT_LIMIT = 50
MAX_LIMIT = 200


def _build_checkr_report_url(report_id: str | None) -> str | None:
    if not report_id:
        return None

    base_url = "https://dashboard.checkr.com"
    if settings.checkr_env.lower().strip() != "production":
        # Use sandbox indicator for clarity when linking out of non-prod
        return f"{base_url}/sandbox/reports/{report_id}"
    return f"{base_url}/reports/{report_id}"


class BGCReviewCountResponse(BaseModel):
    count: int


class BGCReviewItemModel(BaseModel):
    instructor_id: str
    name: str
    email: str
    bgc_status: str
    bgc_report_id: str | None = None
    bgc_completed_at: datetime | None = None
    created_at: datetime | None = None
    consented_at_recent: bool
    checkr_report_url: str | None = None


class BGCReviewListResponse(BaseModel):
    items: list[BGCReviewItemModel]
    next_cursor: str | None = None


class OverridePayload(BaseModel):
    action: Literal["approve", "reject"]


class BGCOverrideResponse(BaseModel):
    ok: bool
    new_status: Literal["passed", "failed"]


class BGCLatestConsentResponse(BaseModel):
    instructor_id: str
    consented_at: datetime
    consent_version: str
    ip_address: str | None = None


@router.get("/review/count", response_model=BGCReviewCountResponse)
async def bgc_review_count(
    repo: InstructorProfileRepository = Depends(get_instructor_repo),
    _: None = Depends(require_admin),
) -> BGCReviewCountResponse:
    """Return total instructors currently in review state."""

    return BGCReviewCountResponse(count=repo.count_by_bgc_status("review"))


@router.get("/review", response_model=BGCReviewListResponse)
async def bgc_review_list(
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    cursor: Optional[str] = Query(None, description="Opaque ULID cursor for pagination"),
    repo: InstructorProfileRepository = Depends(get_instructor_repo),
    _: None = Depends(require_admin),
) -> BGCReviewListResponse:
    """List instructors whose background checks require admin review."""

    query = (
        repo.db.query(repo.model)
        .options(selectinload(repo.model.user))
        .filter(repo.model.bgc_status == "review")
        .order_by(repo.model.id.asc())
    )

    if cursor:
        query = query.filter(repo.model.id > cursor)

    rows = query.limit(limit + 1).all()
    items: list[BGCReviewItemModel] = []

    for profile in rows[:limit]:
        user = getattr(profile, "user", None)
        name_parts = [getattr(user, "first_name", ""), getattr(user, "last_name", "")]
        name = " ".join(part for part in name_parts if part).strip()
        email = getattr(user, "email", None) or ""

        try:
            consented_recent = repo.has_recent_consent(profile.id, CONSENT_WINDOW)
        except RepositoryException:
            consented_recent = False

        items.append(
            BGCReviewItemModel(
                instructor_id=profile.id,
                name=name or email or profile.id,
                email=email,
                bgc_status=profile.bgc_status,
                bgc_report_id=profile.bgc_report_id,
                bgc_completed_at=profile.bgc_completed_at,
                created_at=profile.created_at,
                consented_at_recent=consented_recent,
                checkr_report_url=_build_checkr_report_url(profile.bgc_report_id),
            )
        )

    next_cursor = rows[limit].id if len(rows) > limit else None
    return BGCReviewListResponse(items=items, next_cursor=next_cursor)


@router.post("/{instructor_id}/override", response_model=BGCOverrideResponse)
async def bgc_review_override(
    instructor_id: str,
    payload: OverridePayload = Body(...),
    repo: InstructorProfileRepository = Depends(get_instructor_repo),
    _: None = Depends(require_admin),
) -> BGCOverrideResponse:
    """Approve or reject a background check under admin review."""

    profile = repo.get_by_id(instructor_id, load_relationships=False)
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Instructor not found")

    action = payload.action
    now = datetime.now(timezone.utc)

    if action == "approve":
        repo.update_bgc(
            instructor_id,
            status="passed",
            report_id=profile.bgc_report_id,
            env=profile.bgc_env or settings.checkr_env,
        )
        profile.bgc_completed_at = profile.bgc_completed_at or now
        repo.db.commit()
        return BGCOverrideResponse(ok=True, new_status="passed")

    if not settings.bgc_suppress_adverse_emails:
        logger.info(
            "Admin reject triggered final adverse notification",
            extra={"instructor_id": instructor_id, "report_id": profile.bgc_report_id},
        )
        # TODO: integrate with mailer service when adverse-action workflow is implemented

    repo.update_bgc(
        instructor_id,
        status="failed",
        report_id=profile.bgc_report_id,
        env=profile.bgc_env or settings.checkr_env,
    )
    profile.bgc_completed_at = now
    repo.db.commit()
    return BGCOverrideResponse(ok=True, new_status="failed")


@router.get("/consent/{instructor_id}/latest", response_model=BGCLatestConsentResponse)
async def admin_latest_consent(
    instructor_id: str,
    repo: InstructorProfileRepository = Depends(get_instructor_repo),
    _: None = Depends(require_admin),
) -> BGCLatestConsentResponse:
    """Return the most recent consent record for an instructor."""

    consent = repo.latest_consent(instructor_id)
    if not consent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no consent on file")

    return BGCLatestConsentResponse(
        instructor_id=consent.instructor_id,
        consented_at=consent.consented_at,
        consent_version=consent.consent_version,
        ip_address=consent.ip_address,
    )
