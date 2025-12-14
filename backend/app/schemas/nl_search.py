# backend/app/schemas/nl_search.py
"""
Pydantic schemas for Natural Language search API.

These schemas define the response format for the NL search pipeline
that combines parsing, embedding, retrieval, filtering, and ranking.

Architecture: Returns INSTRUCTOR-level results (not service-level) with all
embedded data to eliminate N+1 queries from the frontend.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field

# =============================================================================
# Instructor-Level Result Schemas (New Architecture)
# =============================================================================


class InstructorSummary(BaseModel):
    """Embedded instructor info for search results."""

    id: str = Field(..., description="Instructor user ID")
    first_name: str = Field(..., description="Instructor first name")
    last_initial: str = Field(..., description="Last name initial for privacy (e.g., 'D')")
    profile_picture_url: Optional[str] = Field(None, description="Profile picture URL")
    bio_snippet: Optional[str] = Field(None, description="First 150 chars of bio")
    verified: bool = Field(False, description="Whether instructor is verified")
    years_experience: Optional[int] = Field(None, description="Years of experience")


class RatingSummary(BaseModel):
    """Aggregated rating info for an instructor."""

    average: Optional[float] = Field(
        None, ge=0, le=5, description="Average rating (None if no reviews)"
    )
    count: int = Field(0, ge=0, description="Number of reviews")


class ServiceMatch(BaseModel):
    """A service that matched the search query."""

    service_id: str = Field(..., description="Instructor service ID (for booking)")
    service_catalog_id: str = Field(..., description="Service catalog ID (for click tracking)")
    name: str = Field(..., description="Service name")
    description: Optional[str] = Field(None, description="Service description")
    price_per_hour: int = Field(..., ge=0, description="Hourly rate in dollars")
    relevance_score: float = Field(..., ge=0, le=1, description="Semantic match score")


class NLSearchResultItem(BaseModel):
    """Single instructor result with all embedded data (eliminates N+1)."""

    instructor_id: str = Field(..., description="Instructor user ID")

    # Embedded data (eliminates N+1 fetches)
    instructor: InstructorSummary = Field(..., description="Instructor profile info")
    rating: RatingSummary = Field(..., description="Aggregated rating info")
    coverage_areas: List[str] = Field(default_factory=list, description="Service area names")

    # Service matches
    best_match: ServiceMatch = Field(..., description="Best matching service")
    other_matches: List[ServiceMatch] = Field(
        default_factory=list, description="Other matching services (max 3)"
    )
    total_matching_services: int = Field(1, ge=1, description="Total number of matching services")

    # For sorting/display
    relevance_score: float = Field(..., ge=0, le=1, description="Best match relevance score")


# =============================================================================
# Legacy Service-Level Schemas (Kept for backward compatibility during transition)
# =============================================================================


class NLSearchScores(BaseModel):
    """Component scores for transparency and debugging."""

    relevance: float = Field(..., ge=0, le=1, description="Semantic/text match score")
    quality: float = Field(..., ge=0, le=1, description="Instructor quality score")
    distance: float = Field(..., ge=0, le=1, description="Proximity score")
    price: float = Field(..., ge=0, le=1, description="Price fit score")
    freshness: float = Field(..., ge=0, le=1, description="Activity recency score")
    completeness: float = Field(..., ge=0, le=1, description="Profile completeness score")


class NLSearchAvailability(BaseModel):
    """Availability info for a search result."""

    dates: List[str] = Field(default_factory=list, description="Available dates (ISO format)")
    earliest: Optional[str] = Field(None, description="Earliest available date")


class NLSearchMatchInfo(BaseModel):
    """Match details for a search result."""

    audience_boost: float = Field(0.0, description="Audience match boost applied")
    skill_boost: float = Field(0.0, description="Skill level match boost applied")
    soft_filtered: bool = Field(False, description="Whether soft filtering was used")
    soft_filter_reasons: List[str] = Field(
        default_factory=list, description="Reasons for soft filtering"
    )


class NLSearchResult(BaseModel):
    """A single NL search result (LEGACY: service-level, kept for compatibility)."""

    service_id: str = Field(..., description="Instructor service ID")
    instructor_id: str = Field(..., description="Instructor user ID")
    name: str = Field(..., description="Service name")
    description: Optional[str] = Field(None, description="Service description")
    price_per_hour: int = Field(..., description="Hourly rate in dollars")
    rank: int = Field(..., ge=1, description="Result ranking position")
    score: float = Field(..., ge=0, le=2, description="Final ranking score")
    scores: NLSearchScores = Field(..., description="Component score breakdown")
    availability: NLSearchAvailability = Field(..., description="Availability information")
    match_info: NLSearchMatchInfo = Field(..., description="Match boost details")


class ParsedQueryInfo(BaseModel):
    """Parsed query details for response transparency."""

    service_query: str = Field(..., description="Extracted service query")
    location: Optional[str] = Field(None, description="Extracted location")
    max_price: Optional[int] = Field(None, description="Extracted max price")
    date: Optional[str] = Field(None, description="Extracted date")
    time_after: Optional[str] = Field(None, description="Extracted time constraint")
    audience_hint: Optional[str] = Field(None, description="Detected audience hint")
    skill_level: Optional[str] = Field(None, description="Detected skill level")
    urgency: Optional[str] = Field(None, description="Detected urgency level")


class NLSearchMeta(BaseModel):
    """Search response metadata."""

    query: str = Field(..., description="Original search query")
    corrected_query: Optional[str] = Field(None, description="Typo-corrected query if different")
    parsed: ParsedQueryInfo = Field(..., description="Parsed query details")
    total_results: int = Field(..., ge=0, description="Total results returned")
    limit: int = Field(..., ge=1, description="Requested limit")
    latency_ms: int = Field(..., ge=0, description="Total search latency in ms")
    cache_hit: bool = Field(False, description="Whether response was from cache")
    degraded: bool = Field(False, description="Whether search was degraded")
    degradation_reasons: List[str] = Field(
        default_factory=list, description="Reasons for degradation"
    )
    parsing_mode: str = Field("regex", description="Parsing mode used (regex/llm)")
    search_query_id: Optional[str] = Field(None, description="Search query ID for click tracking")


class NLSearchResponse(BaseModel):
    """Complete NL search response with instructor-level results."""

    results: List[NLSearchResultItem] = Field(..., description="Instructor-level search results")
    meta: NLSearchMeta = Field(..., description="Search metadata")


class SearchHealthCache(BaseModel):
    """Cache health status."""

    available: bool = Field(..., description="Whether cache is available")
    response_cache_version: Optional[int] = Field(None, description="Current cache version")
    ttls: Optional[Dict[str, int]] = Field(None, description="Cache TTL settings")
    error: Optional[str] = Field(None, description="Error message if unavailable")


class SearchHealthComponents(BaseModel):
    """Health status of search components."""

    cache: SearchHealthCache = Field(..., description="Cache health status")
    parsing_circuit: str = Field(..., description="Parsing circuit breaker state")
    embedding_circuit: str = Field(..., description="Embedding circuit breaker state")


class SearchHealthResponse(BaseModel):
    """Health check response for search service."""

    status: str = Field(..., description="Overall health status")
    components: SearchHealthComponents = Field(..., description="Component health details")


class SearchMetricsResponse(BaseModel):
    """Aggregate search metrics response."""

    total_searches: int = Field(..., ge=0, description="Total number of searches")
    avg_latency_ms: float = Field(..., ge=0, description="Average latency in ms")
    p50_latency_ms: float = Field(..., ge=0, description="50th percentile latency")
    p95_latency_ms: float = Field(..., ge=0, description="95th percentile latency")
    avg_results: float = Field(..., ge=0, description="Average results per search")
    zero_result_rate: float = Field(..., ge=0, le=1, description="Rate of zero-result searches")
    cache_hit_rate: float = Field(..., ge=0, le=1, description="Cache hit rate")
    degradation_rate: float = Field(..., ge=0, le=1, description="Search degradation rate")


class PopularQueryItem(BaseModel):
    """A popular search query."""

    query: str = Field(..., description="Search query text")
    count: int = Field(..., ge=1, description="Number of times searched")
    avg_results: float = Field(..., ge=0, description="Average results for this query")
    avg_latency_ms: Optional[float] = Field(None, ge=0, description="Average latency in ms")


class PopularQueriesResponse(BaseModel):
    """List of popular search queries."""

    queries: List[PopularQueryItem] = Field(..., description="Popular queries")


class ZeroResultQueryItem(BaseModel):
    """A search query that returned zero results."""

    query: str = Field(..., description="Search query text")
    count: int = Field(..., ge=1, description="Number of times searched")
    last_searched: str = Field(..., description="Last search timestamp")


class ZeroResultQueriesResponse(BaseModel):
    """List of zero-result queries."""

    queries: List[ZeroResultQueryItem] = Field(..., description="Zero-result queries")


class SearchClickResponse(BaseModel):
    """Response for logging a search click."""

    click_id: str = Field(..., description="ID of the logged click")


# =============================================================================
# Search Config Schemas
# =============================================================================


class ModelOption(BaseModel):
    """A selectable model option."""

    id: str = Field(..., description="Model identifier")
    name: str = Field(..., description="Display name")
    description: str = Field(..., description="Model description")


class SearchConfigResponse(BaseModel):
    """Current search configuration."""

    parsing_model: str = Field(..., description="Current parsing model")
    parsing_timeout_ms: int = Field(..., ge=500, le=10000, description="Parsing timeout in ms")
    embedding_model: str = Field(..., description="Current embedding model")
    embedding_timeout_ms: int = Field(..., ge=500, le=10000, description="Embedding timeout in ms")
    available_parsing_models: List[ModelOption] = Field(..., description="Available parsing models")
    available_embedding_models: List[ModelOption] = Field(
        ..., description="Available embedding models"
    )


class SearchConfigUpdate(BaseModel):
    """Request to update search configuration."""

    parsing_model: Optional[str] = Field(None, description="New parsing model")
    parsing_timeout_ms: Optional[int] = Field(
        None, ge=500, le=10000, description="New parsing timeout in ms"
    )
    embedding_model: Optional[str] = Field(None, description="New embedding model")
    embedding_timeout_ms: Optional[int] = Field(
        None, ge=500, le=10000, description="New embedding timeout in ms"
    )


class SearchConfigResetResponse(BaseModel):
    """Response after resetting configuration."""

    status: str = Field(..., description="Reset status")
    config: SearchConfigResponse = Field(..., description="Current config after reset")
