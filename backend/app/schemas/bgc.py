"""Background check API response models."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

BackgroundCheckStatusLiteral = Literal["pending", "review", "passed", "failed"]


class BackgroundCheckInviteResponse(BaseModel):
    """Response returned after invoking a background check invitation."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    ok: bool = True
    status: BackgroundCheckStatusLiteral
    report_id: str | None = None
    already_in_progress: bool = False


class BackgroundCheckStatusResponse(BaseModel):
    """Current background check status for an instructor."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    status: BackgroundCheckStatusLiteral
    report_id: str | None = None
    completed_at: datetime | None = None
    env: Literal["sandbox", "production"]


__all__ = [
    "BackgroundCheckInviteResponse",
    "BackgroundCheckStatusResponse",
    "BackgroundCheckStatusLiteral",
]
