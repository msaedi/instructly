"""
Response models for search endpoints.

These models ensure consistent API responses for search-related endpoints.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class InstructorInfo(BaseModel):
    """Instructor information in search results with privacy protection."""

    id: str = Field(description="Instructor user ID")
    first_name: str = Field(description="Instructor first name")
    last_initial: str = Field(description="Instructor last name initial only")
    bio: Optional[str] = Field(default=None, description="Instructor bio")
    years_experience: Optional[int] = Field(default=None, description="Years of experience")
    areas_of_service: Optional[str] = Field(default=None, description="Service areas")

    @classmethod
    def from_user(
        cls,
        user,
        bio: Optional[str] = None,
        years_experience: Optional[int] = None,
        areas_of_service: Optional[str] = None,
    ) -> "InstructorInfo":
        """Create InstructorInfo from user with privacy protection."""
        return cls(
            id=user.id,
            first_name=user.first_name,
            last_initial=user.last_name[0] if user.last_name else "",
            bio=bio,
            years_experience=years_experience,
            areas_of_service=areas_of_service,
        )


class ServiceOffering(BaseModel):
    """Service offering details."""

    id: str = Field(description="Instructor service ID")
    hourly_rate: float = Field(description="Hourly rate for the service")
    experience_level: Optional[str] = Field(default=None, description="Experience level")
    description: Optional[str] = Field(default=None, description="Service description")
    duration_options: List[int] = Field(description="Available session durations in minutes")
    equipment_required: Optional[List[str]] = Field(default=None, description="Required equipment")
    levels_taught: Optional[List[str]] = Field(default=None, description="Levels taught")
    age_groups: Optional[List[str]] = Field(default=None, description="Age groups served")
    location_types: Optional[List[str]] = Field(default=None, description="Location types (online/in-person)")
    max_distance_miles: Optional[int] = Field(default=None, description="Maximum travel distance")


class SearchResult(BaseModel):
    """Individual search result."""

    service: Dict[str, Any] = Field(description="Service catalog information")
    instructor: InstructorInfo = Field(description="Instructor information")
    offering: ServiceOffering = Field(description="Service offering details")
    match_score: float = Field(description="Match score (0-100)")
    # Optional lightweight coverage data for map summaries (no geometries)
    coverage_regions: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="List of regions served with minimal fields: region_id, name, borough, coverage_type",
    )
    coverage_region_ids: Optional[List[str]] = Field(
        default=None,
        description="List of region IDs served by the instructor for quick FE mapping without extra calls",
    )


class SearchMetadata(BaseModel):
    """Search metadata."""

    used_semantic_search: bool = Field(description="Whether semantic search was used")
    applied_filters: List[str] = Field(description="List of applied filters")
    timestamp: str = Field(description="Search timestamp (ISO format)")
    # Optional observability payload with top-N candidates (if computed)
    observability_candidates: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description=(
            "Optional top-N candidates considered during search for observability/analytics "
            "(position, service_catalog_id, name, score, vector_score, lexical_score, source)."
        ),
    )


class InstructorSearchResponse(BaseModel):
    """Response for instructor search endpoint."""

    model_config = ConfigDict(from_attributes=True)

    query: str = Field(description="Original search query")
    parsed: Dict[str, Any] = Field(description="Parsed query information")
    results: List[SearchResult] = Field(description="Search results")
    total_found: int = Field(description="Total number of results found")
    search_metadata: SearchMetadata = Field(description="Search metadata")
