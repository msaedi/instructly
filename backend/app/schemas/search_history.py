# backend/app/schemas/search_history.py
"""
Pydantic schemas for Search History.

Defines request/response models for search history endpoints.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, validator


class SearchHistoryBase(BaseModel):
    """Base schema for search history."""

    search_query: str = Field(..., description="The search query string", min_length=1)
    search_type: str = Field(
        default="natural_language", description="Type of search: natural_language, category, service_pill, or filter"
    )
    results_count: Optional[int] = Field(None, description="Number of results returned", ge=0)
    guest_session_id: Optional[str] = Field(None, description="UUID for guest session tracking", max_length=36)

    @validator("search_type")
    def validate_search_type(cls, v):
        """Validate search type is one of allowed values."""
        allowed_types = ["natural_language", "category", "service_pill", "filter"]
        if v not in allowed_types:
            raise ValueError(f"search_type must be one of: {', '.join(allowed_types)}")
        return v

    @validator("search_query")
    def validate_search_query(cls, v):
        """Validate search query is not empty after stripping."""
        if not v.strip():
            raise ValueError("search_query cannot be empty")
        return v.strip()


class SearchHistoryCreate(SearchHistoryBase):
    """Schema for creating search history."""


class GuestSearchHistoryCreate(BaseModel):
    """Schema for creating guest search history (no user_id required)."""

    search_query: str = Field(..., description="The search query string", min_length=1)
    search_type: str = Field(
        default="natural_language", description="Type of search: natural_language, category, service_pill, or filter"
    )
    results_count: Optional[int] = Field(None, description="Number of results returned", ge=0)
    guest_session_id: str = Field(..., description="UUID for guest session tracking", max_length=36)

    @validator("search_type")
    def validate_search_type(cls, v):
        """Validate search type is one of allowed values."""
        allowed_types = ["natural_language", "category", "service_pill", "filter"]
        if v not in allowed_types:
            raise ValueError(f"search_type must be one of: {', '.join(allowed_types)}")
        return v

    @validator("search_query")
    def validate_search_query(cls, v):
        """Validate search query is not empty after stripping."""
        if not v.strip():
            raise ValueError("search_query cannot be empty")
        return v.strip()


class SearchHistoryResponse(SearchHistoryBase):
    """Schema for search history responses."""

    id: int = Field(..., description="Unique identifier for the search history entry")
    created_at: datetime = Field(..., description="When the search was performed")

    class Config:
        from_attributes = True
        json_encoders = {datetime: lambda v: v.isoformat()}


class SearchHistoryInDB(SearchHistoryBase):
    """Schema for search history in database."""

    id: int
    user_id: Optional[int]
    created_at: datetime
    deleted_at: Optional[datetime]
    converted_to_user_id: Optional[int]
    converted_at: Optional[datetime]

    class Config:
        from_attributes = True
