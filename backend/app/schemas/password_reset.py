# backend/app/schemas/password_reset.py

from datetime import datetime
from typing import Any, Callable, Dict, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_serializer

from ._strict_base import StrictModel, StrictRequestModel


class PasswordResetRequest(StrictRequestModel):
    """Request model for initiating password reset"""

    email: EmailStr


class PasswordResetConfirm(StrictRequestModel):
    """Request model for confirming password reset with new password"""

    token: str
    new_password: str = Field(..., min_length=8)

    @field_validator("new_password")
    def validate_password(cls, v: str) -> str:
        if not any(char.isdigit() for char in v):
            raise ValueError("Password must contain at least one digit")
        if not any(char.isupper() for char in v):
            raise ValueError("Password must contain at least one uppercase letter")
        return v


class PasswordResetResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    """Response after requesting password reset"""

    message: str


class PasswordResetToken(BaseModel):
    """Internal model for password reset tokens"""

    id: str
    user_id: str
    token: str
    expires_at: datetime
    used: bool = False
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PasswordResetVerifyResponse(StrictModel):
    """Response for password reset token verification."""

    valid: bool
    email: Optional[str] = None

    @model_serializer(mode="wrap")
    def _serialize(
        self, handler: Callable[["PasswordResetVerifyResponse"], Dict[str, Any]]
    ) -> Dict[str, Any]:
        data = handler(self)
        if data.get("email") is None:
            data.pop("email", None)
        return data
