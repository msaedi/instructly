"""Admin user-management endpoints."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.dependencies.auth import require_admin
from app.api.dependencies.database import get_db
from app.models.user import User
from app.ratelimit.dependency import rate_limit
from app.repositories.factory import RepositoryFactory
from app.schemas.security import SessionInvalidationResponse
from app.services.audit_service import AuditService

router = APIRouter(tags=["admin-users"])
logger = logging.getLogger(__name__)


@router.post(
    "/users/{user_id}/force-logout",
    response_model=SessionInvalidationResponse,
    dependencies=[Depends(rate_limit("admin_mcp"))],
)
async def force_logout_user(
    user_id: str,
    request: Request,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> SessionInvalidationResponse:
    """Force logout for all active sessions belonging to a target user."""
    user_repo = RepositoryFactory.create_user_repository(db)
    invalidated = await asyncio.to_thread(
        user_repo.invalidate_all_tokens,
        user_id,
        trigger="admin_force_logout",
    )
    if not invalidated:
        logger.error("Admin force-logout: token invalidation failed for user_id=%s", user_id)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    try:
        AuditService(db).log(
            action="admin.force_logout",
            resource_type="user",
            resource_id=user_id,
            actor=current_admin,
            actor_type="user",
            description="Admin forced logout for user",
            metadata={"target_user_id": user_id},
            request=request,
        )
    except Exception:
        logger.warning("Audit log write failed for admin force-logout", exc_info=True)
    return SessionInvalidationResponse(message="User sessions have been logged out")


__all__ = ["router"]
