# backend/app/schemas/password_reset.py

from datetime import datetime
from typing import Union

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

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


class PasswordResetVerifyResponseValid(BaseModel):
    """Response for valid password reset token"""

    valid: bool = True
    email: str


class PasswordResetVerifyResponseInvalid(BaseModel):
    """Response for invalid password reset token"""

    valid: bool = False


# Union type for the actual response
PasswordResetVerifyResponse = Union[
    PasswordResetVerifyResponseValid, PasswordResetVerifyResponseInvalid
]
