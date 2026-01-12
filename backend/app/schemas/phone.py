"""Schemas for phone number management and verification."""

from pydantic import BaseModel, Field


class PhoneUpdateRequest(BaseModel):
    phone_number: str = Field(..., description="Phone number in E.164 format")


class PhoneUpdateResponse(BaseModel):
    phone_number: str | None = None
    verified: bool = False


class PhoneVerifyConfirmRequest(BaseModel):
    code: str = Field(..., min_length=6, max_length=6)


class PhoneVerifyResponse(BaseModel):
    sent: bool = False
    verified: bool = False
