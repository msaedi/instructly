"""Strict response schemas for admin instructor endpoints."""

from datetime import datetime
from typing import Optional

from ._strict_base import StrictModel


class AdminInstructorDetailResponse(StrictModel):
    """Detailed instructor metadata for administrative tooling."""

    id: str
    name: str
    email: str
    is_live: bool
    bgc_status: Optional[str] = None
    bgc_report_id: Optional[str] = None
    bgc_completed_at: Optional[datetime] = None
    consent_recent_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    bgc_valid_until: Optional[datetime] = None
    bgc_expires_in_days: Optional[int] = None
    bgc_is_expired: bool = False
    bgc_in_dispute: bool = False
    bgc_dispute_note: Optional[str] = None
    bgc_dispute_opened_at: Optional[datetime] = None
    bgc_dispute_resolved_at: Optional[datetime] = None


__all__ = ["AdminInstructorDetailResponse"]
