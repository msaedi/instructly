# backend/app/schemas/service_catalog.py
"""
Schemas for service catalog endpoints.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class CategoryResponse(BaseModel):
    """Service category response."""

    id: int
    name: str
    slug: str
    description: Optional[str] = None
    display_order: int

    class Config:
        from_attributes = True


class CatalogServiceResponse(BaseModel):
    """Catalog service response."""

    id: int
    category_id: int
    category: Optional[str] = None
    name: str
    slug: str
    description: Optional[str] = None
    search_terms: List[str] = []
    typical_duration_options: List[int] = [60]
    min_recommended_price: Optional[float] = None
    max_recommended_price: Optional[float] = None

    class Config:
        from_attributes = True


class InstructorServiceCreate(BaseModel):
    """Create instructor service from catalog."""

    catalog_service_id: int = Field(..., description="ID of the catalog service")
    hourly_rate: float = Field(..., gt=0, description="Hourly rate for this service")
    custom_description: Optional[str] = Field(None, description="Custom description (optional)")
    duration_options: Optional[List[int]] = Field(
        None, description="Custom duration options in minutes (uses catalog defaults if not provided)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "catalog_service_id": 1,
                "hourly_rate": 75.0,
                "custom_description": "Specializing in jazz piano for intermediate students",
                "duration_options": [30, 45, 60],
            }
        }


class InstructorServiceResponse(BaseModel):
    """Instructor service response with catalog info."""

    id: int
    catalog_service_id: int
    name: str
    category: str
    hourly_rate: float
    description: Optional[str] = None
    duration_options: List[int] = [60]
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
