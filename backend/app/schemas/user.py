import re
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
import pytz

from ._strict_base import StrictRequestModel
from .base import StandardizedModel


class UserBase(BaseModel):
    email: EmailStr
    first_name: str = Field(..., min_length=1, max_length=50)
    last_name: str = Field(..., min_length=1, max_length=50)
    phone: Optional[str] = Field(None, max_length=20)
    zip_code: str = Field(..., pattern=r"^\d{5}$")
    is_active: Optional[bool] = True
    timezone: Optional[str] = "America/New_York"

    @field_validator("phone")
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        if v:
            # Remove any non-numeric characters
            cleaned = re.sub(r"\D", "", v)
            # Check if it's a valid phone number (10-14 digits)
            if not (10 <= len(cleaned) <= 14):
                raise ValueError("Phone number must be 10-14 digits")
            # Format as needed (e.g., store with country code)
            if len(cleaned) == 10:
                cleaned = "1" + cleaned  # Add US country code
            return "+" + cleaned
        return v

    @field_validator("timezone")
    def validate_timezone(cls, v: Optional[str]) -> Optional[str]:
        if v and v not in pytz.all_timezones:
            raise ValueError(f"Invalid timezone: {v}")
        return v


class UserCreate(StrictRequestModel, UserBase):
    password: str
    role: Optional[str] = None  # For backward compatibility during registration
    guest_session_id: Optional[str] = None  # For conversion on signup
    metadata: Optional[
        Dict[str, Any]
    ] = None  # Optional client-provided metadata (e.g., invite_code)


class UserUpdate(StrictRequestModel):
    first_name: Optional[str] = Field(None, min_length=1, max_length=50)
    last_name: Optional[str] = Field(None, min_length=1, max_length=50)
    phone: Optional[str] = Field(None, max_length=20)
    zip_code: Optional[str] = Field(None, pattern=r"^\d{5}$")
    timezone: Optional[str] = None

    @field_validator("phone")
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        if v:
            # Remove any non-numeric characters
            cleaned = re.sub(r"\D", "", v)
            # Check if it's a valid phone number (10-14 digits)
            if not (10 <= len(cleaned) <= 14):
                raise ValueError("Phone number must be 10-14 digits")
            # Format as needed (e.g., store with country code)
            if len(cleaned) == 10:
                cleaned = "1" + cleaned  # Add US country code
            return "+" + cleaned
        return v

    @field_validator("timezone")
    def validate_timezone(cls, v: Optional[str]) -> Optional[str]:
        if v and v not in pytz.all_timezones:
            raise ValueError(f"Invalid timezone: {v}")
        return v


class UserLogin(BaseModel):
    model_config = StrictRequestModel.model_config

    email: EmailStr
    password: str
    guest_session_id: Optional[str] = None  # For conversion on login
    captcha_token: Optional[str] = None  # Optional Turnstile token when required


class UserResponse(StandardizedModel):  # Changed from UserBase
    id: str
    email: EmailStr
    first_name: str
    last_name: str
    phone: Optional[str] = None
    phone_verified: Optional[bool] = False
    zip_code: str
    is_active: Optional[bool] = True
    timezone: str = "America/New_York"
    roles: List[str] = []  # List of role names
    permissions: List[str] = []  # List of permission names
    # Profile picture metadata (expose minimal info for clients)
    profile_picture_version: Optional[int] = 0
    has_profile_picture: Optional[bool] = False

    model_config = ConfigDict(from_attributes=True)


class UserWithPermissionsResponse(UserResponse):
    """Enhanced user response with roles and permissions for /me endpoint."""

    # Optional beta metadata (present during beta phases)
    beta_access: Optional[bool] = None
    beta_role: Optional[str] = None
    beta_phase: Optional[str] = None
    beta_invited_by: Optional[str] = None


class Token(BaseModel):
    access_token: str
    token_type: str
