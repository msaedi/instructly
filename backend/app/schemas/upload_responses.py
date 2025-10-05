"""Strict response schemas for upload endpoints."""

from typing import Dict, Optional

from pydantic import Field

from ._strict_base import StrictModel


class SignedUploadResponse(StrictModel):
    """Response payload for signed upload requests."""

    upload_url: str
    object_key: str
    public_url: Optional[str] = None
    headers: Dict[str, str] = Field(default_factory=dict)
    expires_at: str


class ProxyUploadResponse(StrictModel):
    """Response payload for proxied uploads in local development."""

    ok: bool
    url: Optional[str] = None


__all__ = [
    "ProxyUploadResponse",
    "SignedUploadResponse",
]
