"""Video lesson schemas.

Request/response models for the video lesson endpoints.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from ._strict_base import StrictModel


class VideoJoinResponse(StrictModel):
    """Response from POST /api/v1/lessons/{booking_id}/join."""

    auth_token: str
    room_id: str
    role: str
    booking_id: str


class VideoSessionStatusResponse(StrictModel):
    """Response from GET /api/v1/lessons/{booking_id}/video-session."""

    room_id: str
    session_started_at: Optional[datetime] = None
    session_ended_at: Optional[datetime] = None
    instructor_joined_at: Optional[datetime] = None
    student_joined_at: Optional[datetime] = None
