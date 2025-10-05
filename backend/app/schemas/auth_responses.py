"""Strict response schemas for authentication routes."""

from typing import List, Optional

from pydantic import EmailStr, Field

from ._strict_base import StrictModel


class AuthUserResponse(StrictModel):
    """Minimal strict representation of a user for auth endpoints."""

    id: str
    email: EmailStr
    first_name: str
    last_name: str
    phone: Optional[str] = None
    zip_code: Optional[str] = None
    is_active: bool = True
    timezone: Optional[str] = None
    roles: List[str] = Field(default_factory=list)
    permissions: List[str] = Field(default_factory=list)
    profile_picture_version: Optional[int] = 0
    has_profile_picture: Optional[bool] = False


class AuthUserWithPermissionsResponse(AuthUserResponse):
    """Extends auth user response with optional beta metadata."""

    beta_access: Optional[bool] = None
    beta_role: Optional[str] = None
    beta_phase: Optional[str] = None
    beta_invited_by: Optional[str] = None


class AuthTokenResponse(StrictModel):
    """Strict token payload for session-based login responses."""

    access_token: str
    token_type: str


__all__ = [
    "AuthTokenResponse",
    "AuthUserResponse",
    "AuthUserWithPermissionsResponse",
]
