# backend/app/schemas/service_catalog.py
"""
Schemas for service catalog endpoints.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import ConfigDict, Field

from ._strict_base import StrictModel, StrictRequestModel


class CategoryResponse(StrictModel):
    """Service category response."""

    id: str
    name: str
    subtitle: Optional[str] = None
    slug: str
    description: Optional[str] = None
    display_order: int
    icon_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True, extra="forbid", validate_assignment=True)


class CatalogServiceResponse(StrictModel):
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
    display_order: int | None = None
    online_capable: bool | None = None
    requires_certification: bool | None = None

    model_config = ConfigDict(from_attributes=True, extra="forbid", validate_assignment=True)


class CatalogServiceMinimalResponse(StrictModel):
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


class InstructorServiceResponse(StrictModel):
    """Instructor service response with catalog info."""

    id: str
    catalog_service_id: str
    name: str
    service_catalog_name: Optional[str] = Field(
        default=None,
        description="Human-readable name of the catalog service",
    )
    category: str
    hourly_rate: float
    description: Optional[str] = None
    duration_options: List[int] = [60]
    location_types: Optional[List[str]] = Field(
        default=None,
        description="Legacy location types (in_person, online)",
    )
    offers_travel: bool = False
    offers_at_location: bool = False
    offers_online: bool = True
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True, extra="forbid", validate_assignment=True)


class InstructorServiceCapabilitiesUpdate(StrictRequestModel):
    """Partial update for instructor service location capabilities."""

    offers_travel: Optional[bool] = None
    offers_at_location: Optional[bool] = None
    offers_online: Optional[bool] = None
