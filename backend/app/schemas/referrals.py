"""
Schemas for referral-related endpoints.
"""

from typing import List, Optional

from pydantic import AnyUrl, BaseModel, EmailStr, Field

from ._strict_base import StrictRequestModel


class ReferralSendRequest(StrictRequestModel):
    """Request payload for sending referral invites."""

    emails: List[EmailStr] = Field(..., description="List of recipient email addresses")
    referral_link: AnyUrl = Field(..., description="Referral link to include in the invite")
    from_name: Optional[str] = Field(
        default=None,
        description="Display name of the inviter (falls back to a generic label if omitted)",
    )


class ReferralSendError(BaseModel):
    """Details for a failed referral send attempt."""

    email: EmailStr
    error: str


class ReferralSendResponse(BaseModel):
    """Response after attempting to send referral invites."""

    status: str = Field(description="Operation status ('ok' if the operation ran)")
    sent: int = Field(description="Number of emails successfully sent")
    failed: int = Field(description="Number of emails that failed to send")
    errors: List[ReferralSendError] = Field(
        default_factory=list, description="List of errors for individual recipients"
    )
