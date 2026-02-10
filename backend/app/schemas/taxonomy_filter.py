"""Schemas for the flexible filter system (taxonomy filters).

Named taxonomy_filter.py to avoid collision with the PostGIS filter_repository.py.
"""

from typing import Dict, List, Literal

from pydantic import ConfigDict, Field

from ._strict_base import StrictModel

FilterType = Literal["single_select", "multi_select"]


class FilterOptionResponse(StrictModel):
    """A single filter option value."""

    id: str
    value: str = Field(..., description="Machine-readable value (e.g., 'elementary')")
    display_name: str = Field(..., description="Human-readable label (e.g., 'Elementary (K-5)')")
    display_order: int = Field(0, description="Order for UI display")

    model_config = ConfigDict(from_attributes=True, extra="forbid", validate_assignment=True)


class FilterDefinitionResponse(StrictModel):
    """A filter type definition."""

    id: str
    key: str = Field(..., description="Machine-readable key (e.g., 'grade_level')")
    display_name: str = Field(..., description="Human-readable name (e.g., 'Grade Level')")
    filter_type: FilterType = Field(
        ..., description="Type of filter: 'single_select' or 'multi_select'"
    )

    model_config = ConfigDict(from_attributes=True, extra="forbid", validate_assignment=True)


class FilterDefinitionWithOptions(FilterDefinitionResponse):
    """A filter definition with all its possible options."""

    options: List[FilterOptionResponse] = Field(default_factory=list)


class SubcategoryFilterResponse(StrictModel):
    """A filter as it applies to a specific subcategory (with only valid options).

    This is the primary schema used by the frontend to render filter UI.
    """

    filter_key: str = Field(..., description="Filter key (e.g., 'grade_level')")
    filter_display_name: str = Field(..., description="Human-readable name")
    filter_type: FilterType = Field(..., description="'single_select' or 'multi_select'")
    options: List[FilterOptionResponse] = Field(
        default_factory=list, description="Valid options for this subcategory"
    )

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class FilterWithOptions(StrictModel):
    """A filter definition with valid options and requirement flag.

    Combines filter definition info with is_required (per-subcategory)
    for use in filter dropdowns.
    """

    id: str
    key: str = Field(..., description="Machine-readable key (e.g., 'grade_level')")
    display_name: str = Field(..., description="Human-readable name (e.g., 'Grade Level')")
    filter_type: FilterType = Field(..., description="'single_select' or 'multi_select'")
    is_required: bool = Field(
        False, description="Whether this filter is required for the subcategory (not yet enforced)"
    )
    options: List[FilterOptionResponse] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class InstructorFilterContext(StrictModel):
    """Filter context for instructor skill selection.

    Combines available filters with current selections for a specific
    subcategory+instructor combination.
    """

    available_filters: List[SubcategoryFilterResponse] = Field(
        default_factory=list, description="Filters available for this subcategory"
    )
    current_selections: Dict[str, List[str]] = Field(
        default_factory=dict,
        description="Instructor's current filter selections (filter_key -> [selected values])",
    )

    model_config = ConfigDict(extra="forbid", validate_assignment=True)
