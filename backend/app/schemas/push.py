# backend/app/schemas/push.py
"""Schemas for push notification endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import ConfigDict, Field, field_validator

from ._strict_base import StrictModel, StrictRequestModel


class PushSubscribeRequest(StrictRequestModel):
    """Request to subscribe to push notifications."""

    endpoint: str = Field(
        ...,
        description="Push service endpoint URL",
        max_length=2048,
    )
    p256dh_key: str = Field(
        ...,
        alias="p256dh",
        description="Public encryption key",
        max_length=512,
    )
    auth_key: str = Field(
        ...,
        alias="auth",
        description="Auth secret",
        max_length=512,
    )
    user_agent: Optional[str] = Field(None, description="Browser/device info")

    model_config = ConfigDict(
        **StrictRequestModel.model_config,
        populate_by_name=True,
    )

    @field_validator("endpoint")
    @classmethod
    def validate_endpoint(cls, value: str) -> str:
        if not value.startswith("https://"):
            raise ValueError("Push endpoint must use HTTPS")
        return value


class PushUnsubscribeRequest(StrictRequestModel):
    """Request to unsubscribe from push notifications."""

    endpoint: str = Field(..., description="Push service endpoint URL to remove")


class PushSubscriptionResponse(StrictModel):
    """Push subscription details."""

    id: str
    endpoint: str
    user_agent: Optional[str]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, **StrictModel.model_config)


class VapidPublicKeyResponse(StrictModel):
    """VAPID public key response."""

    public_key: str


class PushStatusResponse(StrictModel):
    """Response after subscribe/unsubscribe."""

    success: bool
    message: str
