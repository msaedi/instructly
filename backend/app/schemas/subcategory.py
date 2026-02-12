"""Schemas for service subcategories and category tree responses.

This module defines the middle tier of the 3-level taxonomy plus the composite
tree schemas (CategoryWithSubcategories, CategoryTreeResponse) that combine
categories and subcategories. The tree schemas live here (not in service_catalog.py)
to avoid circular imports — this file imports from service_catalog.py, not vice versa.
"""

from typing import List, Optional

from pydantic import ConfigDict, Field

from ._strict_base import StrictModel, StrictRequestModel
from .service_catalog import CatalogServiceResponse, CategoryResponse
from .taxonomy_filter import SubcategoryFilterResponse


class SubcategoryBase(StrictModel):
    """Base fields shared by subcategory schemas."""

    name: str = Field(..., max_length=255, description="Display name (e.g., 'Piano', 'Guitar')")
    display_order: int = Field(0, description="Order for UI display (lower numbers first)")


class SubcategoryCreate(StrictRequestModel, SubcategoryBase):
    """Schema for creating a new subcategory."""

    category_id: str = Field(..., description="ULID of the parent category")


class SubcategoryResponse(SubcategoryBase):
    """Full subcategory response."""

    id: str
    category_id: str

    model_config = ConfigDict(from_attributes=True, extra="forbid", validate_assignment=True)


class SubcategoryBrief(StrictModel):
    """Minimal subcategory for list views (browse page pills)."""

    id: str
    name: str
    service_count: int = Field(0, description="Number of services in this subcategory")

    model_config = ConfigDict(from_attributes=True, extra="forbid", validate_assignment=True)


class SubcategoryWithServices(SubcategoryResponse):
    """Subcategory with nested services (for category detail / onboarding)."""

    services: List[CatalogServiceResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True, extra="forbid", validate_assignment=True)


# ── Category tree schemas (composite: category + subcategories) ──


class CategoryWithSubcategories(CategoryResponse):
    """Category with subcategory list (for browse page)."""

    subcategories: List[SubcategoryBrief] = Field(default_factory=list)


class CategoryTreeResponse(CategoryResponse):
    """Full 3-level tree: category → subcategories → services.

    Used for onboarding flows and admin category management.
    """

    subcategories: List[SubcategoryWithServices] = Field(default_factory=list)


class SubcategorySummary(StrictModel):
    """Subcategory summary for listing within a category page."""

    id: str
    slug: Optional[str] = None
    name: str
    description: Optional[str] = None
    service_count: int = 0

    model_config = ConfigDict(from_attributes=True, extra="forbid", validate_assignment=True)


class SubcategoryDetail(StrictModel):
    """Full subcategory detail for /category/subcategory pages.

    Includes nested services and applicable filters.
    """

    id: str
    slug: Optional[str] = None
    name: str
    description: Optional[str] = None
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None
    category: Optional[CategoryResponse] = None
    services: List[CatalogServiceResponse] = Field(default_factory=list)
    filters: List[SubcategoryFilterResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True, extra="forbid", validate_assignment=True)


class CategorySummary(StrictModel):
    """Lightweight category for homepage grid."""

    id: str
    slug: Optional[str] = None
    name: str
    description: Optional[str] = None
    subcategory_count: int = 0

    model_config = ConfigDict(from_attributes=True, extra="forbid", validate_assignment=True)


class CategoryDetail(StrictModel):
    """Full category detail for /categories/{slug} pages.

    Includes subcategory listing with counts.
    """

    id: str
    slug: Optional[str] = None
    name: str
    description: Optional[str] = None
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None
    subcategories: List[SubcategorySummary] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True, extra="forbid", validate_assignment=True)
