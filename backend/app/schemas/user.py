from typing import List, Optional

import pytz
from pydantic import BaseModel, ConfigDict, EmailStr, field_validator

from .base import StandardizedModel


class UserBase(BaseModel):
    email: EmailStr
    full_name: Optional[str] = None
    is_active: Optional[bool] = True
    timezone: Optional[str] = "America/New_York"

    @field_validator("timezone")
    def validate_timezone(cls, v):
        if v and v not in pytz.all_timezones:
            raise ValueError(f"Invalid timezone: {v}")
        return v


class UserCreate(UserBase):
    password: str
    role: Optional[str] = None  # For backward compatibility during registration
    guest_session_id: Optional[str] = None  # For conversion on signup


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    timezone: Optional[str] = None

    @field_validator("timezone")
    def validate_timezone(cls, v):
        if v and v not in pytz.all_timezones:
            raise ValueError(f"Invalid timezone: {v}")
        return v


class UserLogin(BaseModel):
    email: EmailStr
    password: str
    guest_session_id: Optional[str] = None  # For conversion on login


class UserResponse(StandardizedModel):  # Changed from UserBase
    id: int
    email: EmailStr
    full_name: Optional[str] = None
    is_active: Optional[bool] = True
    timezone: str = "America/New_York"
    roles: List[str] = []  # List of role names
    permissions: List[str] = []  # List of permission names

    model_config = ConfigDict(from_attributes=True)


class UserWithPermissionsResponse(UserResponse):
    """Enhanced user response with roles and permissions for /me endpoint."""

    pass  # roles and permissions already defined in UserResponse


class Token(BaseModel):
    access_token: str
    token_type: str
