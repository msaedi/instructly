"""Background check API request/response models."""

from datetime import datetime
from typing import Literal

from pydantic import Field

from ._strict_base import StrictModel, StrictRequestModel

BackgroundCheckStatusLiteral = Literal[
    "pending", "review", "consider", "passed", "failed", "canceled"
]


class BackgroundCheckInviteRequest(StrictRequestModel):
    """Payload accepted by the background check invite endpoint."""

    package_slug: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
        description="Optional Checkr package slug override",
    )


class BackgroundCheckInviteResponse(StrictModel):
    """Response returned after invoking a background check invitation."""

    ok: bool = True
    status: BackgroundCheckStatusLiteral
    report_id: str | None = None
    candidate_id: str | None = None
    invitation_id: str | None = None
    already_in_progress: bool = False


class BackgroundCheckStatusResponse(StrictModel):
    """Current background check status for an instructor."""

    status: BackgroundCheckStatusLiteral
    report_id: str | None = None
    completed_at: datetime | None = None
    env: Literal["sandbox", "production"]
    consent_recent: bool = False
    consent_recent_at: datetime | None = None
    valid_until: datetime | None = None
    expires_in_days: int | None = None
    is_expired: bool = False
    eta: datetime | None = None


__all__ = [
    "BackgroundCheckInviteRequest",
    "BackgroundCheckInviteResponse",
    "BackgroundCheckStatusResponse",
    "BackgroundCheckStatusLiteral",
]
