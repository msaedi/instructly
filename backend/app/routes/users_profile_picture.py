"""
Profile picture endpoints: finalize, view URL, delete.

Thin wrappers over PersonalAssetService following repository/service pattern.
"""

import logging
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from ..api.dependencies.auth import get_current_active_user
from ..database import get_db
from ..middleware.rate_limiter import RateLimitKeyType, rate_limit
from ..models.user import User
from ..schemas.base_responses import DeleteResponse, SuccessResponse
from ..services.dependencies import get_personal_asset_service
from ..services.personal_asset_service import PersonalAssetService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/users", tags=["users", "assets"])


class FinalizeProfilePicturePayload(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    object_key: str


@router.post("/me/profile-picture", response_model=SuccessResponse)
@rate_limit(
    "1/minute",
    key_type=RateLimitKeyType.USER,
    error_message="You're updating your picture too frequently. Please wait a minute.",
)
def upload_finalize_profile_picture(
    payload: FinalizeProfilePicturePayload,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
    asset_service: PersonalAssetService = Depends(get_personal_asset_service),
) -> SuccessResponse:
    try:
        asset_service.finalize_profile_picture(current_user, payload.object_key)
        return SuccessResponse(success=True, message="Profile picture updated", data=None)
    except Exception as e:
        logger.error(f"Finalize profile picture failed: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/{user_id}/profile-picture-url", response_model=SuccessResponse)
def get_profile_picture_url(
    user_id: str,
    variant: Optional[Literal["original", "display", "thumb"]] = Query("display"),
    current_user: User = Depends(get_current_active_user),
    asset_service: PersonalAssetService = Depends(get_personal_asset_service),
) -> SuccessResponse:
    try:
        view = asset_service.get_profile_picture_view(user_id, variant or "display")
        return SuccessResponse(
            success=True,
            message="OK",
            data={"url": view.url, "expires_at": view.expires_at},
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.delete("/me/profile-picture", response_model=DeleteResponse)
@rate_limit(
    "1/minute",
    key_type=RateLimitKeyType.USER,
    error_message="You're deleting your picture too frequently. Please wait a minute.",
)
def delete_profile_picture(
    current_user: User = Depends(get_current_active_user),
    asset_service: PersonalAssetService = Depends(get_personal_asset_service),
) -> DeleteResponse:
    try:
        ok = asset_service.delete_profile_picture(current_user)
        return DeleteResponse(
            success=ok, message="Profile picture deleted" if ok else "No profile picture present"
        )
    except Exception as e:
        logger.error(f"Delete profile picture failed: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
