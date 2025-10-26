# backend/app/routes/admin_badges.py
"""
Admin endpoints for managing badge awards.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..api.dependencies.auth import require_admin
from ..core.exceptions import NotFoundException
from ..database import get_db
from ..schemas.badge import AdminAwardListResponse, AdminAwardSchema
from ..services.badge_admin_service import BadgeAdminService

router = APIRouter(prefix="/api/admin/badges", tags=["admin-badges"])


def get_admin_service(db: Session = Depends(get_db)) -> BadgeAdminService:
    return BadgeAdminService(db)


@router.get(
    "/pending",
    response_model=AdminAwardListResponse,
    dependencies=[Depends(require_admin)],
)
def list_pending_awards(
    before: Optional[datetime] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    service: BadgeAdminService = Depends(get_admin_service),
):
    normalized_status = (status or "pending").strip().lower()
    return service.list_awards(
        status=normalized_status,
        before=before,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/{award_id}/confirm",
    response_model=AdminAwardSchema,
    dependencies=[Depends(require_admin)],
)
def confirm_award(
    award_id: str,
    service: BadgeAdminService = Depends(get_admin_service),
):
    try:
        return service.confirm_award(award_id, datetime.now(timezone.utc))
    except NotFoundException as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post(
    "/{award_id}/revoke",
    response_model=AdminAwardSchema,
    dependencies=[Depends(require_admin)],
)
def revoke_award(
    award_id: str,
    service: BadgeAdminService = Depends(get_admin_service),
):
    try:
        return service.revoke_award(award_id, datetime.now(timezone.utc))
    except NotFoundException as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
