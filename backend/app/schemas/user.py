from pydantic import BaseModel, EmailStr
from typing import Optional
from enum import Enum
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

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserResponse(StandardizedModel):  # Changed from UserBase
    id: int
    email: EmailStr
    full_name: Optional[str] = None
    role: UserRole
    is_active: Optional[bool] = True

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str