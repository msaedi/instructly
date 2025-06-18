# backend/app/schemas/password_reset.py

from pydantic import BaseModel, EmailStr, Field, field_validator, ConfigDict
from typing import Optional
from datetime import datetime

class PasswordResetRequest(BaseModel):
    """Request model for initiating password reset"""
    email: EmailStr
    
class PasswordResetConfirm(BaseModel):
    """Request model for confirming password reset with new password"""
    token: str
    new_password: str = Field(..., min_length=8)
    
    @field_validator('new_password')
    def validate_password(cls, v):
        if not any(char.isdigit() for char in v):
            raise ValueError('Password must contain at least one digit')
        if not any(char.isupper() for char in v):
            raise ValueError('Password must contain at least one uppercase letter')
        return v

class PasswordResetResponse(BaseModel):
    """Response after requesting password reset"""
    message: str
    
class PasswordResetToken(BaseModel):
    """Internal model for password reset tokens"""
    id: int
    user_id: int
    token: str
    expires_at: datetime
    used: bool = False
    created_at: datetime
    
    class Config:
        from_attributes = True