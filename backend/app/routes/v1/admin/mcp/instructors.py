"""MCP Admin endpoints for instructor operations (service token auth)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.dependencies.auth import validate_mcp_service
from app.api.dependencies.database import get_db
from app.core.exceptions import NotFoundException
from app.models.user import User
from app.ratelimit.dependency import rate_limit
from app.schemas.mcp import (
    MCPActor,
    MCPInstructorBGC,
    MCPInstructorDetailResponse,
    MCPInstructorListItem,
    MCPInstructorListResponse,
    MCPInstructorOnboarding,
    MCPInstructorService as MCPInstructorServiceSchema,
    MCPInstructorStats,
    MCPMeta,
    MCPServiceCoverageData,
    MCPServiceCoverageResponse,
)
from app.services.mcp_instructor_service import MCPInstructorService

router = APIRouter(tags=["MCP Admin - Instructors"])


@router.get(
    "",
    response_model=MCPInstructorListResponse,
    dependencies=[Depends(rate_limit("admin_mcp"))],
)
async def list_instructors(
    status: Literal["registered", "onboarding", "live", "paused"] | None = None,
    is_founding: bool | None = None,
    service_slug: str | None = None,
    category_slug: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = None,
    current_user: User = Depends(validate_mcp_service),
    db: Session = Depends(get_db),
) -> MCPInstructorListResponse:
    service = MCPInstructorService(db)
    try:
        payload = service.list_instructors(
            status=status,
            is_founding=is_founding,
            service_slug=service_slug,
            category_slug=category_slug,
            limit=limit,
            cursor=cursor,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    meta = MCPMeta(
        request_id=str(uuid4()),
        generated_at=datetime.now(timezone.utc),
        actor=MCPActor(id=current_user.id, email=current_user.email),
    )

    items = [MCPInstructorListItem(**item) for item in payload.get("items", [])]

    return MCPInstructorListResponse(
        meta=meta,
        items=items,
        next_cursor=payload.get("next_cursor"),
        limit=payload.get("limit", limit),
    )


@router.get(
    "/coverage",
    response_model=MCPServiceCoverageResponse,
    dependencies=[Depends(rate_limit("admin_mcp"))],
)
async def get_service_coverage(
    status: Literal["registered", "onboarding", "live", "paused"] = "live",
    group_by: Literal["category", "service"] = "category",
    top: int = Query(default=25, ge=1, le=200),
    current_user: User = Depends(validate_mcp_service),
    db: Session = Depends(get_db),
) -> MCPServiceCoverageResponse:
    service = MCPInstructorService(db)
    data = service.get_service_coverage(status=status, group_by=group_by, top=top)

    meta = MCPMeta(
        request_id=str(uuid4()),
        generated_at=datetime.now(timezone.utc),
        actor=MCPActor(id=current_user.id, email=current_user.email),
    )

    return MCPServiceCoverageResponse(meta=meta, data=MCPServiceCoverageData(**data))


@router.get(
    "/{identifier}",
    response_model=MCPInstructorDetailResponse,
    dependencies=[Depends(rate_limit("admin_mcp"))],
)
async def get_instructor_detail(
    identifier: str,
    current_user: User = Depends(validate_mcp_service),
    db: Session = Depends(get_db),
) -> MCPInstructorDetailResponse:
    service = MCPInstructorService(db)
    try:
        detail = service.get_instructor_detail(identifier)
    except NotFoundException as exc:
        raise HTTPException(status_code=404, detail="Instructor not found") from exc

    meta = MCPMeta(
        request_id=str(uuid4()),
        generated_at=datetime.now(timezone.utc),
        actor=MCPActor(id=current_user.id, email=current_user.email),
    )

    return MCPInstructorDetailResponse(
        meta=meta,
        user_id=detail["user_id"],
        name=detail["name"],
        email=detail["email"],
        phone=detail.get("phone"),
        status=detail["status"],
        is_founding=detail["is_founding"],
        founding_granted_at=detail.get("founding_granted_at"),
        admin_url=detail["admin_url"],
        live_at=detail.get("live_at"),
        onboarding=MCPInstructorOnboarding(**detail["onboarding"]),
        bgc=MCPInstructorBGC(**detail["bgc"]),
        services=[MCPInstructorServiceSchema(**svc) for svc in detail.get("services", [])],
        stats=MCPInstructorStats(**detail["stats"]),
    )
