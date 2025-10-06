from ._strict_base import StrictModel

"""Background check API response models."""

from datetime import datetime
from typing import Literal

BackgroundCheckStatusLiteral = Literal["pending", "review", "passed", "failed"]


class BackgroundCheckInviteResponse(StrictModel):
    """Response returned after invoking a background check invitation."""

    ok: bool = True
    status: BackgroundCheckStatusLiteral
    report_id: str | None = None
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


__all__ = [
    "BackgroundCheckInviteResponse",
    "BackgroundCheckStatusResponse",
    "BackgroundCheckStatusLiteral",
]
