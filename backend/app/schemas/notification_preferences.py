# backend/app/schemas/notification_preferences.py
"""Schemas for notification preference endpoints."""

from __future__ import annotations

from typing import Dict, List

from pydantic import ConfigDict

from ._strict_base import StrictModel, StrictRequestModel


class PreferenceResponse(StrictModel):
    """Single preference response."""

    id: str
    category: str
    channel: str
    enabled: bool
    locked: bool

    model_config = ConfigDict(from_attributes=True, **StrictModel.model_config)


class PreferencesByCategory(StrictModel):
    """Preferences grouped by category for frontend consumption."""

    lesson_updates: Dict[str, bool]
    messages: Dict[str, bool]
    learning_tips: Dict[str, bool]
    system_updates: Dict[str, bool]
    promotional: Dict[str, bool]


class UpdatePreferenceRequest(StrictRequestModel):
    """Request to update a single preference."""

    enabled: bool


class PreferenceUpdate(StrictRequestModel):
    """Single preference update for bulk requests."""

    category: str
    channel: str
    enabled: bool


class BulkUpdateRequest(StrictRequestModel):
    """Bulk preference update request."""

    updates: List[PreferenceUpdate]
