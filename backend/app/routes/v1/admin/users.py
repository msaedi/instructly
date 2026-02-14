"""Admin user-management endpoints."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies.auth import require_admin
from app.api.dependencies.database import get_db
from app.models.user import User
from app.ratelimit.dependency import rate_limit
from app.repositories.factory import RepositoryFactory
from app.schemas.security import SessionInvalidationResponse

router = APIRouter(tags=["admin-users"])


@router.post(
    "/users/{user_id}/force-logout",
    response_model=SessionInvalidationResponse,
    dependencies=[Depends(rate_limit("admin_mcp"))],
)
async def force_logout_user(
    user_id: str,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> SessionInvalidationResponse:
    """Force logout for all active sessions belonging to a target user."""
    user_repo = RepositoryFactory.create_user_repository(db)
    invalidated = await asyncio.to_thread(user_repo.invalidate_all_tokens, user_id)
    if not invalidated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return SessionInvalidationResponse(message="User sessions have been logged out")


__all__ = ["router"]
