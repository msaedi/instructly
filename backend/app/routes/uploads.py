"""Signed upload endpoints for Cloudflare R2 (S3-compatible)."""

import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.params import File, Form
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from ..api.dependencies.auth import get_current_active_user
from ..core.config import Settings, settings
from ..database import get_db
from ..middleware.rate_limiter import RateLimitKeyType, rate_limit
from ..models.user import User
from ..schemas.base_responses import SuccessResponse
from ..services.dependencies import get_personal_asset_service
from ..services.personal_asset_service import PersonalAssetService

logger = logging.getLogger(__name__)


def get_settings() -> Settings:
    return settings


router = APIRouter(prefix="/api/uploads", tags=["uploads"])


class CreateSignedUploadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    filename: str = Field(..., description="Original file name, used for extension validation")
    content_type: str = Field(..., description="Browser-reported MIME type")
    size_bytes: int = Field(..., ge=1, le=10 * 1024 * 1024, description="Max 10MB")
    purpose: Literal["background_check", "profile_picture"]


class SignedUploadResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    upload_url: str
    object_key: str
    public_url: str | None = None
    headers: dict[str, str]
    expires_at: str


class ProxyUploadResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    ok: bool
    url: str | None = None


_PROXY_ALLOWED_CONTENT_TYPES: set[str] = {"image/jpeg", "image/png", "image/webp"}
_PROXY_MAX_BYTES = 5 * 1024 * 1024


def _validate_background_check_file(filename: str, content_type: str) -> None:
    allowed_ext = {".pdf", ".png", ".jpg", ".jpeg"}
    lower = filename.lower()
    if not any(lower.endswith(ext) for ext in allowed_ext):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid file type")
    allowed_ct = {"application/pdf", "image/png", "image/jpeg"}
    if content_type not in allowed_ct:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid content type")


@router.post("/r2/signed-url", response_model=SignedUploadResponse)
@rate_limit(
    "1/minute",
    key_type=RateLimitKeyType.USER,
    error_message="Too many upload attempts. Please wait a minute.",
)
def create_signed_upload(
    payload: CreateSignedUploadRequest,
    current_user: User = Depends(get_current_active_user),
    _db: Session = Depends(get_db),
    asset_service: PersonalAssetService = Depends(get_personal_asset_service),
) -> SignedUploadResponse:
    """Create a short-lived signed PUT URL for uploading files to R2.

    We implement SigV4 signing locally to avoid requiring boto3.
    """
    if payload.purpose == "background_check":
        _validate_background_check_file(payload.filename, payload.content_type)
    elif payload.purpose == "profile_picture":
        # Lightweight allowlist; full validation occurs on finalize
        if payload.content_type not in {"image/png", "image/jpeg"}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid content type"
            )

    # Ensure R2 configured
    if (
        not settings.r2_bucket_name
        or not settings.r2_access_key_id
        or not settings.r2_secret_access_key
    ):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Uploads not configured"
        )

    # Build object key using service helper (keeps structure consistent)
    object_key = asset_service.initiate_upload_key(
        payload.purpose, current_user.id, payload.filename
    )

    # Generate presigned PUT via client
    pre = asset_service.storage.generate_presigned_put(object_key, payload.content_type)

    public_url = None
    try:
        if settings.r2_public_base_url:
            public_url = f"{settings.r2_public_base_url}/{object_key}"
    except Exception:
        public_url = None

    return SignedUploadResponse(
        upload_url=pre.url,
        object_key=object_key,
        public_url=public_url,
        headers=pre.headers,
        expires_at=pre.expires_at,
    )


@router.post("/r2/proxy", response_model=ProxyUploadResponse)
async def proxy_upload_to_r2(
    file: UploadFile = File(...),
    key: str = Form(..., description="Temporary object key from the signed upload response"),
    content_type: str = Form(..., description="Content type reported by the browser"),
    current_user: User = Depends(get_current_active_user),
    _db: Session = Depends(get_db),
    asset_service: PersonalAssetService = Depends(get_personal_asset_service),
    app_settings: Settings = Depends(get_settings),
) -> ProxyUploadResponse:
    """Upload the file server-side for local development to avoid browser CORS issues."""

    if app_settings.site_mode != "local":
        # Mirror a 404 so hosted environments never expose this helper endpoint.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Proxy upload unavailable"
        )

    normalized_key = key.strip()
    if not normalized_key or ".." in normalized_key or not normalized_key.startswith("uploads/"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid object key")
    if f"/{current_user.id}/" not in normalized_key:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden object key")

    declared_content_type = (content_type or "").strip().lower() or (
        file.content_type or ""
    ).lower()
    if declared_content_type not in _PROXY_ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported content type",
        )

    data = await file.read(_PROXY_MAX_BYTES + 1)
    await file.close()

    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file")
    if len(data) > _PROXY_MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File exceeds 5MB limit",
        )

    try:
        ok, status_code = asset_service.storage.upload_bytes(
            normalized_key, data, declared_content_type
        )
    except Exception as exc:  # pragma: no cover - network failure path
        logger.error("Proxy upload failed for %s: %s", normalized_key, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to upload to storage"
        ) from exc

    if not ok:
        logger.error(
            "Proxy upload returned non-success status for %s: %s", normalized_key, status_code
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to upload to storage"
        )

    public_url = None
    try:
        if settings.r2_public_base_url:
            public_url = f"{settings.r2_public_base_url}/{normalized_key}"
    except Exception:  # pragma: no cover - formatting/logging path
        public_url = None

    return ProxyUploadResponse(ok=True, url=public_url)


class FinalizeProfilePictureRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    object_key: str = Field(..., description="Temporary upload object key from signed PUT")


@router.post("/r2/finalize/profile-picture", response_model=SuccessResponse)
@rate_limit(
    "1/minute",
    key_type=RateLimitKeyType.USER,
    error_message="You're updating your picture too frequently. Please wait a minute.",
)
def finalize_profile_picture(
    payload: FinalizeProfilePictureRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
    asset_service: PersonalAssetService = Depends(get_personal_asset_service),
) -> SuccessResponse:
    """Finalize a previously uploaded profile picture: validate, process, version, store."""
    try:
        asset_service.finalize_profile_picture(current_user, payload.object_key)
        return SuccessResponse(success=True, message="Profile picture updated", data=None)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Finalize profile picture failed for user={current_user.id}: {e}")
        raise HTTPException(status_code=400, detail=str(e))
