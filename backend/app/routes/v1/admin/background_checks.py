# backend/app/routes/v1/admin/background_checks.py
"""Admin endpoints for managing instructor background checks (v1)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import logging
import math
from typing import Any, Literal, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlalchemy.orm import Query as SAQuery

from app.api.dependencies.auth import require_admin
from app.api.dependencies.repositories import (
    get_bgc_webhook_log_repo,
    get_instructor_repo,
)
from app.core.config import settings
from app.core.exceptions import RepositoryException
from app.models.instructor import InstructorProfile
from app.models.user import User
from app.repositories.bgc_webhook_log_repository import BGCWebhookLogRepository
from app.repositories.instructor_profile_repository import InstructorProfileRepository
from app.schemas.admin_background_checks import (
    BGCCaseCountsResponse,
    BGCCaseItemModel,
    BGCCaseListResponse,
    BGCDisputeResponse,
    BGCExpiringItem,
    BGCHistoryItem,
    BGCHistoryResponse,
    BGCLatestConsentResponse,
    BGCOverrideResponse,
    BGCReviewCountResponse,
    BGCReviewListResponse,
    BGCWebhookLogEntry,
    BGCWebhookLogListResponse,
    BGCWebhookStatsResponse,
)
from app.services.background_check_workflow_service import (
    BackgroundCheckWorkflowService,
)
from app.utils.strict import model_filter

logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin-bgc"])

CONSENT_WINDOW = timedelta(hours=24)
DEFAULT_LIMIT = 50
MAX_LIMIT = 200

_WEBHOOK_EVENT_MAP: dict[str, dict[str, list[str]]] = {
    "invitation.": {"prefixes": ["invitation."]},
    "report.": {"prefixes": ["report."]},
    "deferred": {"exact": ["report.deferred"]},
    "canceled": {"exact": ["report.canceled"]},
    "completed": {"exact": ["report.completed"]},
    "error": {"exact": ["report.upgrade_failed", "report.suspended"]},
}


def _parse_event_filters(raw_values: list[str]) -> tuple[list[str], list[str]]:
    exact: list[str] = []
    prefixes: list[str] = []
    for raw in raw_values:
        token = (raw or "").strip().lower()
        if not token:
            continue
        mapping = _WEBHOOK_EVENT_MAP.get(token)
        if mapping:
            exact.extend(mapping.get("exact", []))
            prefixes.extend(mapping.get("prefixes", []))
            continue
        if token.endswith("."):
            prefixes.append(token)
        else:
            exact.append(token)
    return list(dict.fromkeys(exact)), list(dict.fromkeys(prefixes))


def _parse_status_filters(raw_values: list[str]) -> list[int]:
    codes: set[int] = set()
    for raw in raw_values:
        token = (raw or "").strip().lower()
        if not token:
            continue
        if token.endswith("xx") and len(token) == 3 and token[0].isdigit():
            base = int(token[0]) * 100
            codes.update(range(base, base + 100))
            continue
        if token in {"error", "errors"}:
            codes.update(range(400, 600))
            continue
        try:
            codes.add(int(token))
        except ValueError:
            continue
    return sorted(codes)


def _extract_payload_object(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data")
    if isinstance(data, dict):
        obj = data.get("object")
        if isinstance(obj, dict):
            return obj
    return {}


def _build_checkr_report_url(report_id: str | None) -> str | None:
    if not report_id:
        return None

    base_url = "https://dashboard.checkr.com"
    if settings.checkr_env.lower().strip() != "production":
        # Use sandbox indicator for clarity when linking out of non-prod
        return f"{base_url}/sandbox/reports/{report_id}"
    return f"{base_url}/reports/{report_id}"


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
    valid_until = getattr(profile, "bgc_valid_until", None)
    expires_in_days = (
        (valid_until - now).days if valid_until is not None and valid_until > now else None
    )
    is_expired = bool(valid_until is not None and valid_until <= now)

    payload = {
        "instructor_id": profile.id,
        "name": display_name,
        "email": email,
        "is_live": bool(getattr(profile, "is_live", False)),
        "bgc_status": getattr(profile, "bgc_status", ""),
        "bgc_includes_canceled": bool(getattr(profile, "bgc_includes_canceled", False)),
        "bgc_report_id": report_id,
        "bgc_completed_at": getattr(profile, "bgc_completed_at", None),
        "created_at": getattr(profile, "created_at", None),
        "updated_at": getattr(profile, "updated_at", None),
        "checkr_report_url": _build_checkr_report_url(report_id),
        "consent_recent": consent_recent,
        "consent_recent_at": consent_recent_at,
        "bgc_valid_until": valid_until,
        "bgc_expires_in_days": expires_in_days,
        "bgc_is_expired": is_expired,
        "in_dispute": bool(getattr(profile, "bgc_in_dispute", False)),
        "dispute_note": getattr(profile, "bgc_dispute_note", None),
        "dispute_opened_at": getattr(profile, "bgc_dispute_opened_at", None),
        "dispute_resolved_at": getattr(profile, "bgc_dispute_resolved_at", None),
        "bgc_eta": getattr(profile, "bgc_eta", None),
    }

    return BGCCaseItemModel(**model_filter(BGCCaseItemModel, payload))


def _build_case_query(
    *,
    repo: InstructorProfileRepository,
    status: str,
    search: str | None,
) -> SAQuery:
    query = repo.get_bgc_case_base_query()

    if status == "pending":
        query = query.filter(repo.model.bgc_status == "pending")
    elif status == "review":
        query = query.filter(repo.model.bgc_status.in_(["review", "consider"]))

    joined_user = False
    term = (search or "").strip()
    if term:
        joined_user = True
        like_value = f"%{term.lower()}%"
        query = query.join(User)
        name_concat = func.coalesce(User.first_name, "") + " " + func.coalesce(User.last_name, "")
        try:
            report_matches = repo.find_profile_ids_by_report_fragment(term)
        except RepositoryException:
            report_matches = set()

        filters = [
            func.lower(repo.model.id).like(like_value),
            func.lower(func.coalesce(User.email, "")).like(like_value),
            func.lower(func.coalesce(User.first_name, "")).like(like_value),
            func.lower(func.coalesce(User.last_name, "")).like(like_value),
            func.lower(name_concat).like(like_value),
        ]
        if report_matches:
            filters.append(repo.model.id.in_(report_matches))
        query = query.filter(or_(*filters))

    if joined_user:
        query = query.distinct()
    return query


def _get_bgc_cases_cursor(
    *,
    repo: InstructorProfileRepository,
    status: str,
    limit: int,
    cursor: str | None,
    search: str | None,
) -> tuple[list[BGCCaseItemModel], str | None]:
    """Legacy cursor-based pagination for review list endpoint."""

    query = _build_case_query(repo=repo, status=status, search=search)

    if cursor:
        query = query.filter(repo.model.id > cursor)

    query = query.order_by(repo.model.id.asc())
    rows = query.limit(limit + 1).all()
    now = datetime.now(timezone.utc)
    items = [_build_case_item(profile, repo, now) for profile in rows[:limit]]
    next_cursor = rows[limit].id if len(rows) > limit else None
    return items, next_cursor


def _get_bgc_cases_paginated(
    *,
    repo: InstructorProfileRepository,
    status: str,
    page: int,
    page_size: int,
    search: str | None,
) -> tuple[list[BGCCaseItemModel], int, int, int]:
    """Return background-check cases ordered by most recent activity."""

    base_query = _build_case_query(repo=repo, status=status, search=search)
    total = base_query.order_by(None).count()
    if total == 0:
        return [], 0, 1, 1

    total_pages = max(1, math.ceil(total / page_size))
    current_page = max(1, min(page, total_pages))

    order_columns = [
        repo.model.updated_at.desc().nullslast(),
        repo.model.bgc_completed_at.desc().nullslast(),
        repo.model.created_at.desc().nullslast(),
        repo.model.id.desc(),
    ]
    ordered_query = base_query.order_by(*order_columns)
    offset = (current_page - 1) * page_size
    rows = ordered_query.offset(offset).limit(page_size).all()
    now = datetime.now(timezone.utc)
    items = [_build_case_item(profile, repo, now) for profile in rows]
    return items, total, current_page, total_pages


class OverridePayload(BaseModel):
    action: Literal["approve", "reject"]


@router.get("/review/count", response_model=BGCReviewCountResponse)
async def bgc_review_count(
    repo: InstructorProfileRepository = Depends(get_instructor_repo),
    _: None = Depends(require_admin),
) -> BGCReviewCountResponse:
    """Return total instructors currently in review state."""

    payload = {"count": repo.count_by_bgc_statuses(["review", "consider"])}
    return BGCReviewCountResponse(**model_filter(BGCReviewCountResponse, payload))


@router.get("/review", response_model=BGCReviewListResponse)
async def bgc_review_list(
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    cursor: Optional[str] = Query(None, description="Opaque ULID cursor for pagination"),
    repo: InstructorProfileRepository = Depends(get_instructor_repo),
    _: None = Depends(require_admin),
) -> BGCReviewListResponse:
    """List instructors whose background checks require admin review."""

    items, next_cursor = _get_bgc_cases_cursor(
        repo=repo,
        status="review",
        limit=limit,
        cursor=cursor,
        search=None,
    )

    review_items = [case.to_review_model() for case in items]
    payload = {"items": review_items, "next_cursor": next_cursor}
    return BGCReviewListResponse(**model_filter(BGCReviewListResponse, payload))


@router.get("/counts", response_model=BGCCaseCountsResponse)
async def bgc_counts(
    repo: InstructorProfileRepository = Depends(get_instructor_repo),
    _: None = Depends(require_admin),
) -> BGCCaseCountsResponse:
    """Return total counts for review and pending background check queues."""

    payload = {
        "review": repo.count_by_bgc_statuses(["review", "consider"]),
        "pending": repo.count_by_bgc_status("pending"),
    }
    return BGCCaseCountsResponse(**model_filter(BGCCaseCountsResponse, payload))


@router.get("/cases", response_model=BGCCaseListResponse)
async def bgc_cases(
    status_param: str = Query("review", alias="status", description="review, pending, or all"),
    q: Optional[str] = Query(None, description="Search by instructor id, name, or email"),
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    legacy_limit: Optional[int] = Query(
        None,
        alias="limit",
        ge=1,
        le=MAX_LIMIT,
        description="Deprecated; use page_size instead.",
    ),
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

    effective_page_size = legacy_limit or page_size

    (
        items,
        total,
        current_page,
        total_pages,
    ) = _get_bgc_cases_paginated(
        repo=repo,
        status=normalized,
        page=page,
        page_size=effective_page_size,
        search=q,
    )
    payload = {
        "items": items,
        "total": total,
        "page": current_page,
        "page_size": effective_page_size,
        "total_pages": total_pages,
        "has_next": current_page < total_pages,
        "has_prev": current_page > 1,
    }
    return BGCCaseListResponse(**model_filter(BGCCaseListResponse, payload))


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
        item_payload = {
            "id": entry.id,
            "result": entry.result,
            "package": entry.package,
            "env": entry.env,
            "completed_at": entry.completed_at,
            "created_at": entry.created_at,
            "report_id_present": bool(entry.report_id_enc),
        }
        items.append(BGCHistoryItem(**model_filter(BGCHistoryItem, item_payload)))

    next_cursor = entries[fetch_limit].id if len(entries) > fetch_limit else None

    payload = {"items": items, "next_cursor": next_cursor}
    return BGCHistoryResponse(**model_filter(BGCHistoryResponse, payload))


@router.get("/expiring", response_model=list[BGCExpiringItem])
async def bgc_expiring(
    days: int = Query(30, ge=1, le=180, description="Lookahead window in days"),
    limit: int = Query(100, ge=1, le=1000),
    repo: InstructorProfileRepository = Depends(get_instructor_repo),
    _: None = Depends(require_admin),
) -> list[BGCExpiringItem]:
    """Return instructors whose background checks are expiring soon."""

    expiring_profiles = repo.list_expiring_within(days, limit=limit)
    results: list[BGCExpiringItem] = []
    for profile in expiring_profiles:
        user = getattr(profile, "user", None)
        item_payload = {
            "instructor_id": profile.id,
            "email": getattr(user, "email", None),
            "bgc_valid_until": getattr(profile, "bgc_valid_until", None),
        }
        results.append(BGCExpiringItem(**model_filter(BGCExpiringItem, item_payload)))
    return results


@router.get("/webhooks", response_model=BGCWebhookLogListResponse)
async def bgc_webhook_logs(
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    cursor: str | None = Query(None, description="Opaque cursor for pagination"),
    event: list[str] = Query(default_factory=list),
    status_param: list[str] = Query(default_factory=list, alias="status"),
    q: str | None = Query(None, description="Search delivery id or signature"),
    log_repo: BGCWebhookLogRepository = Depends(get_bgc_webhook_log_repo),
    repo: InstructorProfileRepository = Depends(get_instructor_repo),
    _: None = Depends(require_admin),
) -> BGCWebhookLogListResponse:
    """Return recent Checkr webhook deliveries for troubleshooting."""

    exact_events, event_prefixes = _parse_event_filters(event)
    status_codes = _parse_status_filters(status_param)
    search_value = (q or "").strip() or None

    entries, next_cursor = await asyncio.to_thread(
        log_repo.list_filtered,
        limit=limit,
        cursor=cursor,
        events=exact_events or None,
        event_prefixes=event_prefixes or None,
        status_codes=status_codes or None,
        search=search_value,
    )

    report_cache: dict[str, str | None] = {}
    candidate_cache: dict[str, str | None] = {}
    invitation_cache: dict[str, str | None] = {}

    def _resolve_by_report(report_id: str | None) -> str | None:
        if not report_id:
            return None
        if report_id not in report_cache:
            profile = repo.get_by_report_id(report_id)
            report_cache[report_id] = getattr(profile, "id", None) if profile else None
        return report_cache[report_id]

    def _resolve_by_invitation(invitation_id: str | None) -> str | None:
        if not invitation_id:
            return None
        if invitation_id not in invitation_cache:
            profile = repo.get_by_invitation_id(invitation_id)
            invitation_cache[invitation_id] = getattr(profile, "id", None) if profile else None
        return invitation_cache[invitation_id]

    def _resolve_by_candidate(candidate_id: str | None) -> str | None:
        if not candidate_id:
            return None
        if candidate_id not in candidate_cache:
            profile = repo.get_by_candidate_id(candidate_id)
            candidate_cache[candidate_id] = getattr(profile, "id", None) if profile else None
        return candidate_cache[candidate_id]

    items: list[BGCWebhookLogEntry] = []
    for entry in entries:
        payload = entry.payload_json if isinstance(entry.payload_json, dict) else {}
        data_object = _extract_payload_object(payload) if isinstance(payload, dict) else {}

        raw_result = None
        if isinstance(data_object, dict):
            raw_result = (
                data_object.get("result")
                or data_object.get("status")
                or data_object.get("adjudication")
            )

        candidate_id = data_object.get("candidate_id")
        if not isinstance(candidate_id, str):
            candidate_id = None
        invitation_id = data_object.get("invitation_id")
        if not isinstance(invitation_id, str):
            invitation_id = None
        report_id: str | None = None
        if isinstance(data_object.get("object"), str) and data_object.get("object") == "report":
            report_id = data_object.get("id") if isinstance(data_object.get("id"), str) else None
        if report_id is None:
            potential = data_object.get("report_id")
            report_id = potential if isinstance(potential, str) else None

        instructor_id = (
            _resolve_by_report(report_id)
            or _resolve_by_invitation(invitation_id)
            or _resolve_by_candidate(candidate_id)
        )

        item_payload = {
            "id": entry.id,
            "event_type": entry.event_type,
            "delivery_id": entry.delivery_id,
            "resource_id": entry.resource_id,
            "result": raw_result if isinstance(raw_result, str) else None,
            "http_status": entry.http_status,
            "signature": entry.signature,
            "created_at": entry.created_at,
            "payload": payload if isinstance(payload, dict) else {},
            "instructor_id": instructor_id,
            "report_id": report_id,
            "candidate_id": candidate_id,
            "invitation_id": invitation_id,
        }
        items.append(BGCWebhookLogEntry(**model_filter(BGCWebhookLogEntry, item_payload)))

    error_count = await asyncio.to_thread(
        log_repo.count_errors_since,
        since=datetime.now(timezone.utc) - timedelta(hours=24),
    )

    response_payload = {
        "items": items,
        "next_cursor": next_cursor,
        "error_count_24h": error_count,
    }
    return BGCWebhookLogListResponse(**model_filter(BGCWebhookLogListResponse, response_payload))


@router.get("/webhooks/stats", response_model=BGCWebhookStatsResponse)
async def bgc_webhook_stats(
    log_repo: BGCWebhookLogRepository = Depends(get_bgc_webhook_log_repo),
    _: None = Depends(require_admin),
) -> BGCWebhookStatsResponse:
    """Return summary stats for Checkr webhooks."""

    since = datetime.now(timezone.utc) - timedelta(hours=24)
    count = await asyncio.to_thread(log_repo.count_errors_since, since=since)
    payload = {"error_count_24h": count}
    return BGCWebhookStatsResponse(**model_filter(BGCWebhookStatsResponse, payload))


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

    if getattr(profile, "bgc_in_dispute", False) and action == "reject":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot finalize adverse action while dispute is open",
        )

    if action == "approve":
        repo.update_bgc(
            instructor_id,
            status="passed",
            report_id=profile.bgc_report_id,
            env=profile.bgc_env or settings.checkr_env,
        )
        profile.bgc_completed_at = profile.bgc_completed_at or now
        repo.commit()
        response_payload = {"ok": True, "new_status": "passed"}
        return BGCOverrideResponse(**model_filter(BGCOverrideResponse, response_payload))

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
    repo.commit()
    response_payload = {"ok": True, "new_status": "failed"}
    return BGCOverrideResponse(**model_filter(BGCOverrideResponse, response_payload))


@router.post("/{instructor_id}/dispute/open", response_model=BGCDisputeResponse)
async def open_bgc_dispute(
    instructor_id: str,
    payload: dict[str, Any] = Body(...),
    repo: InstructorProfileRepository = Depends(get_instructor_repo),
    _: None = Depends(require_admin),
) -> BGCDisputeResponse:
    note = payload.get("note") if isinstance(payload, dict) else None
    try:
        repo.set_dispute_open(instructor_id, note=note)
        repo.commit()
    except RepositoryException as exc:
        repo.rollback()
        message = str(exc)
        status_code = (
            status.HTTP_404_NOT_FOUND
            if "not found" in message.lower()
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=status_code, detail="Unable to open dispute") from exc

    profile = repo.get_by_id(instructor_id, load_relationships=False)
    logger.info(
        "Background check dispute opened",
        extra={"evt": "bgc_dispute_open", "instructor_id": instructor_id},
    )
    response_payload = {
        "ok": True,
        "in_dispute": bool(getattr(profile, "bgc_in_dispute", False)),
        "dispute_note": getattr(profile, "bgc_dispute_note", None),
        "dispute_opened_at": getattr(profile, "bgc_dispute_opened_at", None),
        "dispute_resolved_at": getattr(profile, "bgc_dispute_resolved_at", None),
        "resumed": False,
        "scheduled_for": None,
    }
    return BGCDisputeResponse(**model_filter(BGCDisputeResponse, response_payload))


@router.post("/{instructor_id}/dispute/resolve", response_model=BGCDisputeResponse)
async def resolve_bgc_dispute(
    instructor_id: str,
    payload: dict[str, Any] = Body(...),
    repo: InstructorProfileRepository = Depends(get_instructor_repo),
    _: None = Depends(require_admin),
) -> BGCDisputeResponse:
    note = payload.get("note") if isinstance(payload, dict) else None
    workflow = BackgroundCheckWorkflowService(repo)
    try:
        resumed, scheduled_for = await workflow.resolve_dispute_and_resume_final_adverse(
            instructor_id, note=note
        )
        repo.commit()
    except RepositoryException as exc:
        repo.rollback()
        message = str(exc)
        status_code = (
            status.HTTP_404_NOT_FOUND
            if "not found" in message.lower()
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=status_code, detail="Unable to resolve dispute") from exc

    profile = repo.get_by_id(instructor_id, load_relationships=False)
    logger.info(
        "Background check dispute resolved",
        extra={"evt": "bgc_dispute_resolve", "instructor_id": instructor_id},
    )
    response_payload = {
        "ok": True,
        "in_dispute": bool(getattr(profile, "bgc_in_dispute", False)),
        "dispute_note": getattr(profile, "bgc_dispute_note", None),
        "dispute_opened_at": getattr(profile, "bgc_dispute_opened_at", None),
        "dispute_resolved_at": getattr(profile, "bgc_dispute_resolved_at", None),
        "resumed": resumed,
        "scheduled_for": scheduled_for,
    }
    return BGCDisputeResponse(**model_filter(BGCDisputeResponse, response_payload))


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

    payload = {
        "instructor_id": consent.instructor_id,
        "consented_at": consent.consented_at,
        "consent_version": consent.consent_version,
        "ip_address": consent.ip_address,
    }
    return BGCLatestConsentResponse(**model_filter(BGCLatestConsentResponse, payload))
