"""Signed upload endpoints for Cloudflare R2 (S3-compatible)."""

import base64
import hashlib
import hmac
import json
import logging
import time
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..api.dependencies.auth import get_current_active_user
from ..core.config import settings
from ..database import get_db
from ..models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/uploads", tags=["uploads"])


class CreateSignedUploadRequest(BaseModel):
    filename: str = Field(..., description="Original file name, used for extension validation")
    content_type: str = Field(..., description="Browser-reported MIME type")
    size_bytes: int = Field(..., ge=1, le=10 * 1024 * 1024, description="Max 10MB")
    purpose: Literal["background_check"]


class SignedUploadResponse(BaseModel):
    upload_url: str
    object_key: str
    public_url: str | None = None
    headers: dict[str, str]
    expires_at: str


def _validate_background_check_file(filename: str, content_type: str) -> None:
    allowed_ext = {".pdf", ".png", ".jpg", ".jpeg"}
    lower = filename.lower()
    if not any(lower.endswith(ext) for ext in allowed_ext):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid file type")
    allowed_ct = {"application/pdf", "image/png", "image/jpeg"}
    if content_type not in allowed_ct:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid content type")


@router.post("/r2/signed-url", response_model=SignedUploadResponse)
def create_signed_upload(
    payload: CreateSignedUploadRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Create a short-lived signed PUT URL for uploading files to R2.

    We implement SigV4 signing locally to avoid requiring boto3.
    """
    if payload.purpose == "background_check":
        _validate_background_check_file(payload.filename, payload.content_type)

    # Ensure R2 configured
    if not settings.r2_bucket_name or not settings.r2_access_key_id or not settings.r2_secret_access_key:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Uploads not configured")

    # Build object key
    user_prefix = current_user.id
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    ext = payload.filename.split(".")[-1].lower()
    object_key = f"uploads/{payload.purpose}/{user_prefix}/{ts}.{ext}"

    # Cloudflare R2 S3 endpoint format: https://<account-id>.r2.cloudflarestorage.com/<bucket>/<key>
    host = f"{settings.r2_account_id}.r2.cloudflarestorage.com"
    canonical_uri = f"/{settings.r2_bucket_name}/{object_key}"
    region = "auto"  # R2 uses "auto" region for SigV4
    service = "s3"
    algorithm = "AWS4-HMAC-SHA256"

    # Expiration: 5 minutes
    expires = 300
    now = datetime.now(timezone.utc)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    datestamp = now.strftime("%Y%m%d")

    # Canonical request for presigned URL (query auth)
    signed_headers = "host"
    credential_scope = f"{datestamp}/{region}/{service}/aws4_request"
    params = {
        "X-Amz-Algorithm": algorithm,
        "X-Amz-Credential": f"{settings.r2_access_key_id}/{credential_scope}",
        "X-Amz-Date": amz_date,
        "X-Amz-Expires": str(expires),
        "X-Amz-SignedHeaders": signed_headers,
        "X-Amz-Content-Sha256": "UNSIGNED-PAYLOAD",
        "content-type": payload.content_type,
    }

    # Build canonical query string
    def qs(d: dict[str, str]) -> str:
        # Build canonical query string: sorted keys, URL-encoded values
        from urllib.parse import quote

        parts: list[str] = []
        for k in sorted(d.keys()):
            parts.append(f"{quote(k, safe='-_.~')}={quote(str(d[k]), safe='-_.~')}")
        return "&".join(parts)

    canonical_querystring = qs(params)
    canonical_headers = f"host:{host}\n"
    canonical_request = "\n".join(
        [
            "PUT",
            canonical_uri,
            canonical_querystring,
            canonical_headers,
            signed_headers,
            "UNSIGNED-PAYLOAD",
        ]
    )

    # String to sign
    def _hmac(key: bytes, msg: str) -> bytes:
        return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()

    string_to_sign = "\n".join(
        [
            algorithm,
            amz_date,
            credential_scope,
            hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
        ]
    )

    k_date = _hmac(("AWS4" + settings.r2_secret_access_key.get_secret_value()).encode("utf-8"), datestamp)
    k_region = _hmac(k_date, region)
    k_service = _hmac(k_region, service)
    k_signing = _hmac(k_service, "aws4_request")
    signature = hmac.new(k_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

    # Final URL
    signed_qs = canonical_querystring + f"&X-Amz-Signature={signature}"
    upload_url = f"https://{host}{canonical_uri}?{signed_qs}"

    public_url = None
    try:
        if settings.r2_public_base_url:
            public_url = f"{settings.r2_public_base_url}/{object_key}"
    except Exception:
        public_url = None

    return SignedUploadResponse(
        upload_url=upload_url,
        object_key=object_key,
        public_url=public_url,
        headers={"Content-Type": payload.content_type},
        expires_at=(datetime.now(timezone.utc).replace(microsecond=0).isoformat()),
    )
