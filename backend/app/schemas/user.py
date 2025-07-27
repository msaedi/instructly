from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr

from .base import StandardizedModel


class UserRole(str, Enum):
    STUDENT = "student"
    INSTRUCTOR = "instructor"


class UserBase(BaseModel):
    email: EmailStr
    full_name: Optional[str] = None
    role: UserRole
    is_active: Optional[bool] = True


class UserCreate(UserBase):
    password: str
    guest_session_id: Optional[str] = None  # For conversion on signup


class UserLogin(BaseModel):
    email: EmailStr
    password: str
    guest_session_id: Optional[str] = None  # For conversion on login


class UserResponse(StandardizedModel):  # Changed from UserBase
    id: int
    email: EmailStr
    full_name: Optional[str] = None
    role: UserRole
    is_active: Optional[bool] = True

    model_config = ConfigDict(from_attributes=True)


class Token(BaseModel):
    access_token: str
    token_type: str
