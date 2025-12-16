"""Request models for admin location learning endpoints."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class AdminLocationLearningCreateAliasRequest(BaseModel):
    """Create a manual location alias mapping."""

    alias: str = Field(..., min_length=1, max_length=255, description="Alias text to map")
    region_boundary_id: Optional[str] = Field(
        None, description="RegionBoundary id to map to (single-resolution alias)"
    )
    candidate_region_ids: Optional[List[str]] = Field(
        None,
        description="If provided (len>=2), create an ambiguous alias requiring clarification",
    )
    alias_type: Optional[str] = Field(
        "landmark",
        description="Classification for this alias (abbreviation|colloquial|landmark|typo)",
    )
