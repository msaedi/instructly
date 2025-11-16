"""
Profile picture endpoints: finalize, view URL, delete.

Thin wrappers over PersonalAssetService following repository/service pattern.
"""

import logging
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
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


class ProfilePictureUrlsResponse(BaseModel):
    urls: dict[str, Optional[str]]


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
    response: Response,
    variant: Optional[Literal["original", "display", "thumb"]] = Query("display"),
    asset_service: PersonalAssetService = Depends(get_personal_asset_service),
) -> SuccessResponse:
    try:
        view = asset_service.get_profile_picture_view(user_id, variant or "display")
    except ValueError as exc:
        response.headers["Cache-Control"] = "public, max-age=600"
        response.headers["CDN-Cache-Control"] = "public, max-age=600"
        return SuccessResponse(success=False, message=str(exc), data=None)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    response.headers["Cache-Control"] = "public, max-age=3600"
    response.headers["CDN-Cache-Control"] = "public, max-age=3600"

    return SuccessResponse(
        success=True,
        message="OK",
        data={"url": view.url, "expires_at": view.expires_at},
    )


@router.get("/profile-picture-urls", response_model=ProfilePictureUrlsResponse)
def get_profile_picture_urls_batch(
    response: Response,
    ids: list[str] = Query(
        default=[],
        description="Comma-separated list of user IDs (ids=1,2,3) or repeated ids parameters.",
    ),
    variant: Optional[Literal["original", "display", "thumb"]] = Query("display"),
    asset_service: PersonalAssetService = Depends(get_personal_asset_service),
) -> ProfilePictureUrlsResponse:
    """
    Batch avatar URL lookup.

    Accepts up to 50 user IDs via comma-separated `ids` query param or repeated keys.
    """

    parsed_ids: list[str] = []
    for raw in ids:
        if not raw:
            continue
        parsed_ids.extend([part.strip() for part in raw.split(",") if part.strip()])

    ordered_unique: list[str] = []
    seen: set[str] = set()
    for candidate in parsed_ids:
        if candidate and candidate not in seen:
            seen.add(candidate)
            ordered_unique.append(candidate)

    if len(ordered_unique) > 50:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A maximum of 50 user IDs is supported per request.",
        )

    response.headers["Cache-Control"] = "public, max-age=600"
    response.headers["CDN-Cache-Control"] = "public, max-age=600"

    if not ordered_unique:
        return ProfilePictureUrlsResponse(urls={})

    views = asset_service.get_profile_picture_urls(
        ordered_unique,
        variant=variant or "display",
    )
    payload: dict[str, Optional[str]] = {}
    for requested in ordered_unique:
        view = views.get(requested)
        payload[requested] = view.url if view else None
    return ProfilePictureUrlsResponse(urls=payload)


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
