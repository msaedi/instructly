from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from ._strict_base import StrictModel, StrictRequestModel


class InviteValidateResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    valid: bool
    reason: Optional[str] = None
    code: Optional[str] = None
    email: Optional[EmailStr] = None
    role: Optional[str] = None
    expires_at: Optional[datetime] = None
    used_at: Optional[datetime] = None


class InviteGenerateRequest(StrictRequestModel):
    count: int = 1
    role: str = "instructor_beta"
    expires_in_days: int = 30
    source: Optional[str] = None
    emails: Optional[list[EmailStr]] = None


class InviteRecord(BaseModel):
    id: str
    code: str
    email: Optional[EmailStr] = None
    role: str
    expires_at: datetime


class InviteGenerateResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    invites: list[InviteRecord]


class InviteConsumeRequest(StrictRequestModel):
    code: str
    user_id: str
    role: str = "instructor_beta"
    phase: str = "instructor_only"


class AccessGrantResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    access_id: str
    user_id: str
    role: str
    phase: str
    invited_by_code: Optional[str] = None


class InviteSendRequest(StrictRequestModel):
    to_email: EmailStr
    role: str = Field(default="instructor_beta")
    expires_in_days: int = Field(default=14, ge=1, le=180)
    grant_founding_status: bool = Field(default=True)
    source: Optional[str] = None
    base_url: Optional[str] = None


class InviteSendResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    id: str
    code: str
    email: EmailStr
    join_url: str
    welcome_url: str


class BetaMetricsSummaryResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    invites_sent_24h: int
    invites_errors_24h: int
    phase_counts_24h: dict[str, int]


class InviteBatchSendRequest(StrictRequestModel):
    emails: list[EmailStr] = Field(default_factory=list, min_length=1)
    role: str = Field(default="instructor_beta")
    expires_in_days: int = Field(default=14, ge=1, le=180)
    source: Optional[str] = None
    base_url: Optional[str] = None


class InviteBatchSendFailure(BaseModel):
    email: EmailStr
    reason: str


class InviteBatchSendResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    sent: list[InviteSendResponse]
    failed: list[InviteBatchSendFailure]


class InviteBatchAsyncStartResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    task_id: str


class InviteBatchProgressResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    task_id: str
    state: str
    current: int
    total: int
    sent: int
    failed: int
    sent_items: Optional[list[InviteSendResponse]] = None
    failed_items: Optional[list[InviteBatchSendFailure]] = None
