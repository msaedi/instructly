# backend/app/routes/v1/admin/location_learning.py
"""Admin endpoints for location self-learning."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.dependencies.auth import require_admin
from app.api.dependencies.authz import requires_roles
from app.api.dependencies.database import get_db
from app.schemas.admin_location_learning_responses import (
    AdminLocationLearningAliasActionResponse,
    AdminLocationLearningPendingAliasesResponse,
    AdminLocationLearningProcessResponse,
    AdminLocationLearningUnresolvedQueriesResponse,
)
from app.services.search.location_learning_admin_service import LocationLearningAdminService

router = APIRouter(tags=["admin-location-learning"])


@router.get("/unresolved", response_model=AdminLocationLearningUnresolvedQueriesResponse)
@requires_roles("admin")
async def list_unresolved_location_queries(
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    _: object = Depends(require_admin),
) -> AdminLocationLearningUnresolvedQueriesResponse:
    service = LocationLearningAdminService(db)
    return service.list_unresolved(limit=limit)


@router.get("/pending-aliases", response_model=AdminLocationLearningPendingAliasesResponse)
@requires_roles("admin")
async def list_pending_learned_aliases(
    db: Session = Depends(get_db),
    _: object = Depends(require_admin),
) -> AdminLocationLearningPendingAliasesResponse:
    service = LocationLearningAdminService(db)
    return service.list_pending_aliases()


@router.post("/process", response_model=AdminLocationLearningProcessResponse)
@requires_roles("admin")
async def process_location_learning(
    limit: int = Query(250, ge=1, le=2000),
    db: Session = Depends(get_db),
    _: object = Depends(require_admin),
) -> AdminLocationLearningProcessResponse:
    service = LocationLearningAdminService(db)
    return service.process(limit=limit)


@router.post(
    "/aliases/{alias_id}/approve",
    response_model=AdminLocationLearningAliasActionResponse,
)
@requires_roles("admin")
async def approve_learned_alias(
    alias_id: str,
    db: Session = Depends(get_db),
    _: object = Depends(require_admin),
) -> AdminLocationLearningAliasActionResponse:
    service = LocationLearningAdminService(db)
    if not service.approve_alias(alias_id):
        raise HTTPException(status_code=404, detail="Alias not found")
    return AdminLocationLearningAliasActionResponse(status="approved", alias_id=alias_id)


@router.post(
    "/aliases/{alias_id}/reject",
    response_model=AdminLocationLearningAliasActionResponse,
)
@requires_roles("admin")
async def reject_learned_alias(
    alias_id: str,
    db: Session = Depends(get_db),
    _: object = Depends(require_admin),
) -> AdminLocationLearningAliasActionResponse:
    service = LocationLearningAdminService(db)
    if not service.reject_alias(alias_id):
        raise HTTPException(status_code=404, detail="Alias not found")
    return AdminLocationLearningAliasActionResponse(status="rejected", alias_id=alias_id)
