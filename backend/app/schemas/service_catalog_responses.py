"""Strict response schemas for service catalog aggregate endpoints."""

from typing import Any, Dict, List, Literal, Optional

from pydantic import Field

from ._strict_base import StrictModel


class ServiceSearchMetadata(StrictModel):
    """Metadata describing instructor search results."""

    filters_applied: Dict[str, Any] = Field(default_factory=dict)
    pagination: Dict[str, Any] = Field(default_factory=dict)
    total_matches: int = 0
    active_instructors: int = 0


class ServiceSearchResponse(StrictModel):
    """Envelope for service-focused instructor search results."""

    instructors: List[Dict[str, Any]] = Field(default_factory=list)
    metadata: ServiceSearchMetadata
    search_type: Literal["service"] = "service"
    query: str


class TopCategoryServiceItem(StrictModel):
    """Minimal service representation for top-per-category capsules."""

    id: str
    name: str
    slug: str
    demand_score: float = 0.0
    active_instructors: int = 0
    is_trending: bool = False
    display_order: Optional[int] = None


class TopCategoryItem(StrictModel):
    """Top services grouped under a category."""

    id: str
    name: str
    slug: str
    icon_name: Optional[str] = None
    services: List[TopCategoryServiceItem] = Field(default_factory=list)


class TopServicesMetadata(StrictModel):
    """Metadata for top-per-category payloads."""

    services_per_category: int
    total_categories: int
    cached_for_seconds: int
    updated_at: str


class TopServicesPerCategoryResponse(StrictModel):
    """Response payload for top services per category."""

    categories: List[TopCategoryItem] = Field(default_factory=list)
    metadata: TopServicesMetadata


class CategoryServiceDetail(StrictModel):
    """Detailed catalog service information with instructor analytics."""

    id: str
    category_id: str
    name: str
    slug: str
    description: Optional[str] = None
    search_terms: List[str] = Field(default_factory=list)
    display_order: Optional[int] = None
    online_capable: Optional[bool] = None
    requires_certification: Optional[bool] = None
    is_active: Optional[bool] = None
    active_instructors: int = 0
    instructor_count: int = 0
    demand_score: float = 0.0
    is_trending: bool = False
    actual_min_price: Optional[float] = None
    actual_max_price: Optional[float] = None


class CategoryWithServices(StrictModel):
    """Category record containing detailed services."""

    id: str
    name: str
    slug: str
    subtitle: Optional[str] = None
    description: Optional[str] = None
    icon_name: Optional[str] = None
    services: List[CategoryServiceDetail] = Field(default_factory=list)


class AllServicesMetadata(StrictModel):
    """Metadata for full catalog-with-instructors payload."""

    total_categories: int
    cached_for_seconds: int
    updated_at: str
    total_services: Optional[int] = None


class AllServicesWithInstructorsResponse(StrictModel):
    """Full catalog payload including instructor analytics."""

    categories: List[CategoryWithServices] = Field(default_factory=list)
    metadata: AllServicesMetadata


__all__ = [
    "AllServicesMetadata",
    "AllServicesWithInstructorsResponse",
    "CategoryServiceDetail",
    "CategoryWithServices",
    "ServiceSearchMetadata",
    "ServiceSearchResponse",
    "TopCategoryItem",
    "TopCategoryServiceItem",
    "TopServicesMetadata",
    "TopServicesPerCategoryResponse",
]
