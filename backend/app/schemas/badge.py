# backend/app/schemas/badge.py
"""
Pydantic response models for student badges.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict


class BadgeProgressView(BaseModel):
    current: Optional[float] = None
    goal: Optional[float] = None
    percent: Optional[float] = None

    model_config = ConfigDict(extra="allow")


class StudentBadgeView(BaseModel):
    slug: str
    name: str
    description: Optional[str] = None
    earned: bool
    status: Optional[str] = None
    awarded_at: Optional[datetime] = None
    confirmed_at: Optional[datetime] = None
    progress: Optional[BadgeProgressView | Dict[str, Any]] = None

    model_config = ConfigDict(from_attributes=True)


class AdminAwardBadgeSchema(BaseModel):
    slug: str
    name: str
    criteria_type: Optional[str] = None


class AdminAwardStudentSchema(BaseModel):
    id: str
    email: Optional[str] = None
    display_name: Optional[str] = None


class AdminAwardSchema(BaseModel):
    award_id: str
    status: str
    awarded_at: datetime
    hold_until: Optional[datetime] = None
    confirmed_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None
    badge: AdminAwardBadgeSchema
    student: AdminAwardStudentSchema
    progress_snapshot: Optional[Dict[str, Any]] = None


class AdminAwardListResponse(BaseModel):
    items: List[AdminAwardSchema]
    total: int
    next_offset: Optional[int] = None


__all__ = [
    "StudentBadgeView",
    "BadgeProgressView",
    "AdminAwardSchema",
    "AdminAwardListResponse",
    "AdminAwardBadgeSchema",
    "AdminAwardStudentSchema",
]
