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


class SearchHistoryResponse(SearchHistoryBase):
    """Schema for search history responses."""

    id: int = Field(..., description="Unique identifier for the search history entry")
    created_at: datetime = Field(..., description="When the search was performed")

    class Config:
        orm_mode = True
        json_encoders = {datetime: lambda v: v.isoformat()}
