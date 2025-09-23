# backend/app/schemas/service_catalog.py
"""
Schemas for service catalog endpoints.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from ._strict_base import StrictRequestModel


class CategoryResponse(BaseModel):
    """Service category response."""

    id: str
    name: str
    subtitle: Optional[str] = None
    slug: str
    description: Optional[str] = None
    display_order: int
    icon_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True, extra="forbid", validate_assignment=True)


class CatalogServiceResponse(BaseModel):
    """Catalog service response."""

    id: str
    category_id: str
    category: Optional[str] = None
    name: str
    slug: str
    description: Optional[str] = None
    search_terms: List[str] = []
    typical_duration_options: List[int] = [60]
    min_recommended_price: Optional[float] = None
    max_recommended_price: Optional[float] = None

    model_config = ConfigDict(from_attributes=True, extra="forbid", validate_assignment=True)


class CatalogServiceMinimalResponse(BaseModel):
    """Minimal catalog service response for pills/lists."""

    id: str
    name: str
    slug: str

    model_config = ConfigDict(from_attributes=True, extra="forbid", validate_assignment=True)


class InstructorServiceCreate(StrictRequestModel):
    """Create instructor service from catalog."""

    catalog_service_id: str = Field(..., description="ID of the catalog service")
    hourly_rate: float = Field(..., gt=0, description="Hourly rate for this service")
    custom_description: Optional[str] = Field(None, description="Custom description (optional)")
    duration_options: Optional[List[int]] = Field(
        None,
        description="Custom duration options in minutes (uses catalog defaults if not provided)",
    )

    model_config = ConfigDict(
        **StrictRequestModel.model_config,
        json_schema_extra={
            "example": {
                "catalog_service_id": 1,
                "hourly_rate": 75.0,
                "custom_description": "Specializing in jazz piano for intermediate students",
                "duration_options": [30, 45, 60],
            }
        },
    )


class InstructorServiceResponse(BaseModel):
    """Instructor service response with catalog info."""

    id: str
    catalog_service_id: str
    name: str
    category: str
    hourly_rate: float
    description: Optional[str] = None
    duration_options: List[int] = [60]
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True, extra="forbid", validate_assignment=True)
