"""Admin endpoints for managing instructor background checks."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
from typing import Literal, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlalchemy.orm import selectinload

from ..api.dependencies.auth import require_admin
from ..api.dependencies.repositories import get_instructor_repo
from ..core.config import settings
from ..core.exceptions import RepositoryException
from ..models.instructor import InstructorProfile
from ..models.user import User
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
    updated_at: datetime | None = None
    consented_at_recent: bool
    checkr_report_url: str | None = None
    consented_at_recent_at: datetime | None = None
    is_live: bool


class BGCReviewListResponse(BaseModel):
    items: list[BGCReviewItemModel]
    next_cursor: str | None = None


class BGCCaseCountsResponse(BaseModel):
    review: int
    pending: int


class BGCCaseItemModel(BaseModel):
    instructor_id: str
    name: str
    email: str
    is_live: bool
    bgc_status: str
    bgc_report_id: str | None = None
    bgc_completed_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    checkr_report_url: str | None = None
    consent_recent: bool
    consent_recent_at: datetime | None = None

    def to_review_model(self) -> BGCReviewItemModel:
        return BGCReviewItemModel(
            instructor_id=self.instructor_id,
            name=self.name,
            email=self.email,
            bgc_status=self.bgc_status,
            bgc_report_id=self.bgc_report_id,
            bgc_completed_at=self.bgc_completed_at,
            created_at=self.created_at,
            updated_at=self.updated_at,
            consented_at_recent=self.consent_recent,
            consented_at_recent_at=self.consent_recent_at,
            checkr_report_url=self.checkr_report_url,
            is_live=self.is_live,
        )


class BGCCaseListResponse(BaseModel):
    items: list[BGCCaseItemModel]
    next_cursor: str | None = None


class BGCHistoryItem(BaseModel):
    id: str
    result: str
    package: str | None = None
    env: str
    completed_at: datetime
    created_at: datetime
    report_id_present: bool


class BGCHistoryResponse(BaseModel):
    items: list[BGCHistoryItem]
    next_cursor: str | None = None


def _build_case_item(
    profile: InstructorProfile,
    repo: InstructorProfileRepository,
    now: datetime,
) -> BGCCaseItemModel:
    """Convert an instructor profile into a background-check case payload."""

    user = getattr(profile, "user", None)
    first_name = (getattr(user, "first_name", "") or "").strip()
    last_name = (getattr(user, "last_name", "") or "").strip()
    full_name = " ".join(part for part in [first_name, last_name] if part).strip()
    email = (getattr(user, "email", "") or "").strip()
    display_name = full_name or email or profile.id

    consent_recent_at: datetime | None = None
    consent_recent = False
    try:
        latest_consent = repo.latest_consent(profile.id)
    except RepositoryException:
        latest_consent = None

    if latest_consent is not None:
        consent_recent_at = getattr(latest_consent, "consented_at", None)
        if consent_recent_at is not None:
            consent_recent = consent_recent_at >= now - CONSENT_WINDOW

    report_id = getattr(profile, "bgc_report_id", None)

    return BGCCaseItemModel(
        instructor_id=profile.id,
        name=display_name,
        email=email,
        is_live=bool(getattr(profile, "is_live", False)),
        bgc_status=getattr(profile, "bgc_status", ""),
        bgc_report_id=report_id,
        bgc_completed_at=getattr(profile, "bgc_completed_at", None),
        created_at=getattr(profile, "created_at", None),
        updated_at=getattr(profile, "updated_at", None),
        checkr_report_url=_build_checkr_report_url(report_id),
        consent_recent=consent_recent,
        consent_recent_at=consent_recent_at,
    )


def _get_bgc_cases(
    *,
    repo: InstructorProfileRepository,
    status: str,
    limit: int,
    cursor: str | None,
    search: str | None,
) -> tuple[list[BGCCaseItemModel], str | None]:
    """Query background-check cases with shared pagination logic."""

    query = (
        repo.db.query(repo.model)
        .options(selectinload(repo.model.user))
        .order_by(repo.model.id.asc())
    )

    if status in {"review", "pending"}:
        query = query.filter(repo.model.bgc_status == status)

    if cursor:
        query = query.filter(repo.model.id > cursor)

    joined_user = False
    if search:
        term = search.strip()
        if term:
            joined_user = True
            like_value = f"%{term.lower()}%"
            query = query.join(User)
            name_concat = (
                func.coalesce(User.first_name, "") + " " + func.coalesce(User.last_name, "")
            )
            query = query.filter(
                or_(
                    func.lower(repo.model.id).like(like_value),
                    func.lower(func.coalesce(repo.model.bgc_report_id, "")).like(like_value),
                    func.lower(func.coalesce(User.email, "")).like(like_value),
                    func.lower(func.coalesce(User.first_name, "")).like(like_value),
                    func.lower(func.coalesce(User.last_name, "")).like(like_value),
                    func.lower(name_concat).like(like_value),
                )
            )

    if joined_user:
        query = query.distinct()

    rows = query.limit(limit + 1).all()
    now = datetime.now(timezone.utc)
    items = [_build_case_item(profile, repo, now) for profile in rows[:limit]]
    next_cursor = rows[limit].id if len(rows) > limit else None
    return items, next_cursor


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

    items, next_cursor = _get_bgc_cases(
        repo=repo,
        status="review",
        limit=limit,
        cursor=cursor,
        search=None,
    )

    return BGCReviewListResponse(
        items=[case.to_review_model() for case in items],
        next_cursor=next_cursor,
    )


@router.get("/counts", response_model=BGCCaseCountsResponse)
async def bgc_counts(
    repo: InstructorProfileRepository = Depends(get_instructor_repo),
    _: None = Depends(require_admin),
) -> BGCCaseCountsResponse:
    """Return total counts for review and pending background check queues."""

    return BGCCaseCountsResponse(
        review=repo.count_by_bgc_status("review"),
        pending=repo.count_by_bgc_status("pending"),
    )


@router.get("/cases", response_model=BGCCaseListResponse)
async def bgc_cases(
    status_param: str = Query("review", alias="status", description="review, pending, or all"),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    cursor: Optional[str] = Query(None, description="Opaque ULID cursor for pagination"),
    q: Optional[str] = Query(None, description="Search by instructor id, name, or email"),
    repo: InstructorProfileRepository = Depends(get_instructor_repo),
    _: None = Depends(require_admin),
) -> BGCCaseListResponse:
    """Unified listing endpoint for background check cases."""

    normalized = (status_param or "review").lower()
    if normalized not in {"review", "pending", "all"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid status; expected one of: review, pending, all.",
        )

    items, next_cursor = _get_bgc_cases(
        repo=repo,
        status=normalized,
        limit=limit,
        cursor=cursor,
        search=q,
    )
    return BGCCaseListResponse(items=items, next_cursor=next_cursor)


@router.get("/history/{instructor_id}", response_model=BGCHistoryResponse)
async def bgc_history(
    instructor_id: str,
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    cursor: Optional[str] = Query(None, description="Opaque history ULID cursor"),
    repo: InstructorProfileRepository = Depends(get_instructor_repo),
    _: None = Depends(require_admin),
) -> BGCHistoryResponse:
    """Return append-only history of background check completions."""

    fetch_limit = min(limit, MAX_LIMIT)

    try:
        entries = repo.get_history(
            instructor_id,
            limit=fetch_limit + 1,
            cursor=cursor,
        )
    except RepositoryException as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    items: list[BGCHistoryItem] = []
    for entry in entries[:fetch_limit]:
        items.append(
            BGCHistoryItem(
                id=entry.id,
                result=entry.result,
                package=entry.package,
                env=entry.env,
                completed_at=entry.completed_at,
                created_at=entry.created_at,
                report_id_present=bool(entry.report_id_enc),
            )
        )

    next_cursor = entries[fetch_limit].id if len(entries) > fetch_limit else None

    return BGCHistoryResponse(items=items, next_cursor=next_cursor)


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
