# backend/app/schemas/search_history.py
"""
Pydantic schemas for Search History.

Defines request/response models for search history endpoints.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import ConfigDict, Field, field_serializer, field_validator

from ._strict_base import StrictModel, StrictRequestModel


class SearchContext(StrictModel):
    """Context about where the search originated."""

    page_origin: Optional[str] = None
    viewport_width: Optional[int] = None
    viewport_height: Optional[int] = None
    referrer: Optional[str] = None
    session_search_count: Optional[int] = None


class DeviceContext(StrictModel):
    """Device information for analytics."""

    screen_width: Optional[int] = None
    screen_height: Optional[int] = None
    connection_type: Optional[str] = None
    connection_effective_type: Optional[str] = None
    device_type: Optional[str] = None
    browser: Optional[str] = None
    os: Optional[str] = None
    viewport_size: Optional[str] = None  # Format: "WxH" e.g. "375x812"
    screen_resolution: Optional[str] = None  # Format: "WxH" e.g. "750x1624"
    language: Optional[str] = None
    timezone: Optional[str] = None


class ObservabilityCandidate(StrictModel):
    """Search candidate for observability tracking."""

    position: Optional[int] = None
    service_catalog_id: Optional[str] = None
    id: Optional[str] = None  # Alternative to service_catalog_id
    score: Optional[float] = None
    vector_score: Optional[float] = None
    lexical_score: Optional[float] = None
    source: Optional[str] = None


class SearchHistoryBase(StrictModel):
    """Base schema for search history."""

    search_query: str = Field(..., description="The search query string", min_length=1)
    search_type: str = Field(
        default="natural_language",
        description="Type of search: natural_language, category, service_pill, filter, or search_history",
    )
    results_count: Optional[int] = Field(None, description="Number of results returned", ge=0)
    guest_session_id: Optional[str] = Field(
        None, description="UUID for guest session tracking", max_length=36
    )

    @field_validator("search_type")
    @classmethod
    def validate_search_type(cls, v: str) -> str:
        """Validate search type is one of allowed values."""
        allowed_types = ["natural_language", "category", "service_pill", "filter", "search_history"]
        if v not in allowed_types:
            raise ValueError(f"search_type must be one of: {', '.join(allowed_types)}")
        return v

    @field_validator("search_query")
    @classmethod
    def validate_search_query(cls, v: str) -> str:
        """Validate search query is not empty after stripping."""
        if not v.strip():
            raise ValueError("search_query cannot be empty")
        return v.strip()


class SearchHistoryCreate(StrictRequestModel, SearchHistoryBase):
    """Schema for creating search history."""

    search_context: Optional[SearchContext] = Field(
        None, description="Additional context like page origin, viewport size, etc."
    )
    device_context: Optional[DeviceContext] = Field(
        None,
        description="Device context from frontend including screen size, connection type, etc.",
    )
    observability_candidates: Optional[List[ObservabilityCandidate]] = Field(
        default=None,
        description=(
            "Optional top-N candidate objects for observability. "
            "Each item may include: position, service_catalog_id (or id), score, vector_score, lexical_score, source."
        ),
    )


class GuestSearchHistoryCreate(StrictRequestModel):
    """Schema for creating guest search history (no user_id required)."""

    search_query: str = Field(..., description="The search query string", min_length=1)
    search_type: str = Field(
        default="natural_language",
        description="Type of search: natural_language, category, service_pill, filter, or search_history",
    )
    results_count: Optional[int] = Field(None, description="Number of results returned", ge=0)
    guest_session_id: str = Field(..., description="UUID for guest session tracking", max_length=36)

    @field_validator("search_type")
    @classmethod
    def validate_search_type(cls, v: str) -> str:
        """Validate search type is one of allowed values."""
        allowed_types = ["natural_language", "category", "service_pill", "filter", "search_history"]
        if v not in allowed_types:
            raise ValueError(f"search_type must be one of: {', '.join(allowed_types)}")
        return v

    @field_validator("search_query")
    @classmethod
    def validate_search_query(cls, v: str) -> str:
        """Validate search query is not empty after stripping."""
        if not v.strip():
            raise ValueError("search_query cannot be empty")
        return v.strip()


class SearchHistoryResponse(SearchHistoryBase):
    """Schema for search history responses."""

    id: str = Field(..., description="Unique identifier for the search history entry")
    first_searched_at: datetime = Field(..., description="When the search was first performed")
    last_searched_at: datetime = Field(..., description="When the search was last performed")
    search_count: int = Field(..., description="Number of times this search was performed")
    search_event_id: Optional[str] = Field(
        None, description="ID of the associated search event for tracking interactions"
    )

    model_config = ConfigDict(from_attributes=True, extra="forbid", validate_assignment=True)

    @field_serializer("first_searched_at", "last_searched_at")
    def serialize_datetime(self, dt: datetime) -> str:
        """Serialize datetime to ISO format."""
        return dt.isoformat() if isinstance(dt, datetime) else ""


class SearchHistoryInDB(SearchHistoryBase):
    """Schema for search history in database."""

    id: str
    user_id: Optional[str]
    first_searched_at: datetime
    last_searched_at: datetime
    search_count: int
    deleted_at: Optional[datetime]
    converted_to_user_id: Optional[str]
    converted_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)
