"""Strict response schemas for service catalog aggregate endpoints."""

from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from ._strict_base import StrictModel


class SearchFiltersApplied(BaseModel):
    """Filters applied to instructor search."""

    search: Optional[str] = None
    service_catalog_id: Optional[str] = None
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    service_area_boroughs: Optional[List[str]] = None
    age_group: Optional[str] = None


class SearchPagination(BaseModel):
    """Pagination metadata for search results."""

    skip: int = 0
    limit: int = 100
    count: int = 0


class InstructorSearchResultService(BaseModel):
    """Service offering in search results."""

    id: str
    catalog_service_id: str
    name: str
    hourly_rate: float
    custom_description: Optional[str] = None
    is_active: bool = True
    duration_options: List[int] = Field(default_factory=list)


class InstructorSearchResult(BaseModel):
    """Instructor in search results."""

    id: str
    user_id: str
    first_name: str
    last_initial: str
    bio: Optional[str] = None
    years_experience: Optional[int] = None
    average_rating: Optional[float] = None
    review_count: int = 0
    is_live: bool = False
    profile_picture_version: int = 0
    has_profile_picture: bool = False
    services: List[InstructorSearchResultService] = Field(default_factory=list)
    service_area_summary: Optional[str] = None
    service_area_boroughs: List[str] = Field(default_factory=list)
    is_favorited: Optional[bool] = None
    favorited_count: int = 0
    teaches_kids: Optional[bool] = None
    teaches_adults: Optional[bool] = None


class ServiceSearchMetadata(StrictModel):
    """Metadata describing instructor search results."""

    filters_applied: SearchFiltersApplied = Field(default_factory=SearchFiltersApplied)
    pagination: SearchPagination = Field(default_factory=SearchPagination)
    total_matches: int = 0
    active_instructors: int = 0


class ServiceSearchResponse(StrictModel):
    """Envelope for service-focused instructor search results."""

    instructors: List[InstructorSearchResult] = Field(default_factory=list)
    metadata: ServiceSearchMetadata
    search_type: Literal["service"] = "service"
    query: str


class TopCategoryServiceItem(StrictModel):
    """Minimal service representation for top-per-category capsules."""

    id: str
    name: str
    slug: Optional[str] = None
    demand_score: float = 0.0
    active_instructors: int = 0
    is_trending: bool = False
    display_order: Optional[int] = None


class TopCategoryItem(StrictModel):
    """Top services grouped under a category."""

    id: str
    name: str
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
    subcategory_id: str
    name: str
    slug: Optional[str] = None
    description: Optional[str] = None
    search_terms: List[str] = Field(default_factory=list)
    eligible_age_groups: List[str] = Field(default_factory=list)
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
    "InstructorSearchResult",
    "InstructorSearchResultService",
    "SearchFiltersApplied",
    "SearchPagination",
    "ServiceSearchMetadata",
    "ServiceSearchResponse",
    "TopCategoryItem",
    "TopCategoryServiceItem",
    "TopServicesMetadata",
    "TopServicesPerCategoryResponse",
]
