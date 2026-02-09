# backend/app/schemas/nl_search.py
"""
Pydantic schemas for Natural Language search API.

These schemas define the response format for the NL search pipeline
that combines parsing, embedding, retrieval, filtering, and ranking.

Architecture: Returns INSTRUCTOR-level results (not service-level) with all
embedded data to eliminate N+1 queries from the frontend.
"""
from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional, Union

from pydantic import BaseModel, Field

# =============================================================================
# Instructor-Level Result Schemas (New Architecture)
# =============================================================================


class InstructorTeachingLocationSummary(BaseModel):
    """Approximate teaching location data for public maps."""

    approx_lat: float = Field(..., description="Approximate latitude")
    approx_lng: float = Field(..., description="Approximate longitude")
    neighborhood: Optional[str] = Field(None, description="Neighborhood or city label")


class InstructorSummary(BaseModel):
    """Embedded instructor info for search results."""

    id: str = Field(..., description="Instructor user ID")
    first_name: str = Field(..., description="Instructor first name")
    last_initial: str = Field(..., description="Last name initial for privacy (e.g., 'D')")
    profile_picture_url: Optional[str] = Field(None, description="Profile picture URL")
    bio_snippet: Optional[str] = Field(None, description="First 150 chars of bio")
    verified: bool = Field(False, description="Whether instructor is verified")
    is_founding_instructor: bool = Field(False, description="Founding instructor status")
    years_experience: Optional[int] = Field(None, description="Years of experience")
    teaching_locations: List[InstructorTeachingLocationSummary] = Field(
        default_factory=list, description="Approximate teaching locations for studio pins"
    )


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
    offers_travel: Optional[bool] = Field(
        None, description="Instructor travels to student for this service"
    )
    offers_at_location: Optional[bool] = Field(
        None, description="Instructor teaches at their own location for this service"
    )
    offers_online: Optional[bool] = Field(
        None, description="Instructor offers online lessons for this service"
    )


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

    # Debug-only: distance from searched location (populated for admin tooling when available)
    distance_km: Optional[float] = Field(
        None, ge=0, description="Distance from searched location in kilometers (optional)"
    )
    distance_mi: Optional[float] = Field(
        None, ge=0, description="Distance from searched location in miles (optional)"
    )


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
    time_before: Optional[str] = Field(None, description="Extracted time constraint end")
    audience_hint: Optional[str] = Field(None, description="Detected audience hint")
    skill_level: Optional[str] = Field(None, description="Detected skill level")
    urgency: Optional[str] = Field(None, description="Detected urgency level")
    lesson_type: Optional[str] = Field(
        None, description="Lesson type filter: 'online', 'in_person', or 'any'"
    )
    use_user_location: bool = Field(
        False, description="True if 'near me' detected and user location should be used"
    )


class StageStatus(str, Enum):
    """Status for pipeline stages and location tiers."""

    SUCCESS = "success"
    SKIPPED = "skipped"
    TIMEOUT = "timeout"
    ERROR = "error"
    CACHE_HIT = "cache_hit"
    MISS = "miss"
    CANCELLED = "cancelled"


class LocationTierResult(BaseModel):
    """Result of a location resolution tier attempt."""

    tier: int = Field(..., ge=0, le=5, description="Location tier (0-5)")
    attempted: bool = Field(..., description="Whether the tier was attempted")
    status: StageStatus = Field(..., description="Tier status")
    duration_ms: int = Field(..., ge=0, description="Tier duration in ms")
    result: Optional[str] = Field(None, description="Resolved location name if any")
    confidence: Optional[float] = Field(None, description="Confidence score when available")
    details: Optional[str] = Field(None, description="Additional tier details")


# ============================================================================
# Pipeline Stage Details - Typed Union for API documentation
# ============================================================================
# Note: These models provide typed documentation for OpenAPI/TypeScript generation.
# The service code constructs details as plain dicts; Pydantic validates on serialization.


class CacheCheckStageDetails(BaseModel):
    """Details for cache_check pipeline stage."""

    latency_ms: int = Field(description="Cache check latency in milliseconds")


class Burst1StageDetails(BaseModel):
    """Details for burst1 pipeline stage (pre-OpenAI batch)."""

    text_candidates: int = Field(description="Number of text search candidates")
    region_lookup_loaded: bool = Field(description="Whether region lookup was loaded")
    location_tier: Optional[int] = Field(default=None, description="Location resolution tier used")


class ParseStageDetails(BaseModel):
    """Details for parse pipeline stage."""

    mode: str = Field(description="Parsing mode used (regex/llm)")


class EmbeddingStageDetails(BaseModel):
    """Details for embedding pipeline stage."""

    reason: Optional[str] = Field(default=None, description="Skip/error reason if any")
    used: bool = Field(description="Whether embedding was actually used")


class LocationResolutionStageDetails(BaseModel):
    """Details for location_resolution pipeline stage."""

    resolved: bool = Field(description="Whether location was successfully resolved")
    tier: Optional[int] = Field(default=None, description="Resolution tier that succeeded")


class Burst2StageDetails(BaseModel):
    """Details for burst2 pipeline stage (post-OpenAI batch)."""

    vector_search_used: bool = Field(description="Whether vector search was used")
    total_candidates: int = Field(description="Total candidates after retrieval")
    filter_failed: bool = Field(description="Whether filtering failed")
    ranking_failed: bool = Field(description="Whether ranking failed")


class HydrateStageDetails(BaseModel):
    """Details for hydrate pipeline stage."""

    result_count: int = Field(description="Number of results after hydration")


class BuildResponseStageDetails(BaseModel):
    """Details for build_response pipeline stage."""

    result_count: int = Field(description="Number of results in final response")


class SkippedStageDetails(BaseModel):
    """Details for skipped pipeline stages."""

    reason: str = Field(description="Reason the stage was skipped")


# Union of all pipeline stage details types (without discriminator for runtime compatibility)
# OpenAPI will generate typed interfaces for each model
PipelineStageDetailsUnion = Union[
    CacheCheckStageDetails,
    Burst1StageDetails,
    ParseStageDetails,
    EmbeddingStageDetails,
    LocationResolutionStageDetails,
    Burst2StageDetails,
    HydrateStageDetails,
    BuildResponseStageDetails,
    SkippedStageDetails,
]


class PipelineStage(BaseModel):
    """Timing and status for a pipeline stage."""

    name: str = Field(..., description="Stage name")
    duration_ms: int = Field(..., ge=0, description="Stage duration in ms")
    status: StageStatus = Field(..., description="Stage status")
    details: Optional[PipelineStageDetailsUnion] = Field(
        None, description="Type-specific stage details"
    )


class BudgetInfo(BaseModel):
    """Request budget tracking."""

    initial_ms: int = Field(..., ge=0, description="Initial request budget in ms")
    remaining_ms: int = Field(..., ge=0, description="Remaining budget in ms")
    over_budget: bool = Field(..., description="Whether the budget was exceeded")
    skipped_operations: List[str] = Field(
        default_factory=list, description="Skipped operations due to budget"
    )
    degradation_level: str = Field(..., description="Degradation level label")


class LocationResolutionInfo(BaseModel):
    """Detailed location resolution breakdown."""

    query: str = Field(..., description="Original location query")
    resolved_name: Optional[str] = Field(None, description="Resolved location name")
    resolved_regions: Optional[List[str]] = Field(
        None, description="Resolved sub-regions if applicable"
    )
    successful_tier: Optional[int] = Field(
        None, ge=0, le=5, description="Successful tier number if any"
    )
    tiers: List[LocationTierResult] = Field(default_factory=list, description="Per-tier results")


class SearchDiagnostics(BaseModel):
    """Full diagnostics for admin tooling."""

    total_latency_ms: int = Field(..., ge=0, description="Total latency in ms")
    pipeline_stages: List[PipelineStage] = Field(
        default_factory=list, description="Pipeline stage timings"
    )
    budget: BudgetInfo = Field(..., description="Budget tracking info")
    location_resolution: Optional[LocationResolutionInfo] = Field(
        None, description="Location resolution details"
    )
    initial_candidates: int = Field(..., ge=0, description="Initial candidate count")
    after_text_search: int = Field(..., ge=0, description="Candidates after text search")
    after_vector_search: int = Field(..., ge=0, description="Candidates after vector search")
    after_location_filter: int = Field(..., ge=0, description="Candidates after location filter")
    after_price_filter: int = Field(..., ge=0, description="Candidates after price filter")
    after_availability_filter: int = Field(
        ..., ge=0, description="Candidates after availability filter"
    )
    final_results: int = Field(..., ge=0, description="Final result count")
    cache_hit: bool = Field(..., description="Whether cache was hit")
    parsing_mode: str = Field(..., description="Parsing mode used")
    embedding_used: bool = Field(..., description="Whether query embedding was used")
    vector_search_used: bool = Field(..., description="Whether vector search was used")


class NLSearchContentFilterOption(BaseModel):
    """Taxonomy content filter option surfaced in NL search metadata."""

    value: str = Field(..., description="Machine-readable option value")
    label: str = Field(..., description="Human-readable option label")


class NLSearchContentFilterDefinition(BaseModel):
    """Taxonomy content filter definition surfaced in NL search metadata."""

    key: str = Field(..., description="Machine-readable filter key")
    label: str = Field(..., description="Human-readable filter label")
    type: str = Field(..., description="Filter type (single_select|multi_select)")
    options: List[NLSearchContentFilterOption] = Field(
        default_factory=list,
        description="Available options for this filter key",
    )


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
    skipped_operations: List[str] = Field(
        default_factory=list, description="Operations skipped during degradation"
    )
    parsing_mode: str = Field("regex", description="Parsing mode used (regex/llm)")
    search_query_id: Optional[str] = Field(None, description="Search query ID for click tracking")
    filters_applied: List[str] = Field(
        default_factory=list, description="Filters applied during constraint filtering"
    )
    inferred_filters: Dict[str, List[str]] = Field(
        default_factory=dict,
        description="Taxonomy filter values inferred from query text post-resolution",
    )
    effective_subcategory_id: Optional[str] = Field(
        None,
        description="Resolved subcategory id used to derive taxonomy filter definitions",
    )
    effective_subcategory_name: Optional[str] = Field(
        None,
        description="Resolved subcategory name used to derive taxonomy filter definitions",
    )
    available_content_filters: List[NLSearchContentFilterDefinition] = Field(
        default_factory=list,
        description=(
            "Taxonomy content filter definitions available for this search context "
            "(excludes hard application until user explicitly applies filters)"
        ),
    )
    soft_filtering_used: bool = Field(
        False, description="Whether soft filtering/relaxation was applied"
    )
    filter_stats: Optional[Dict[str, int]] = Field(
        None, description="Filter stage counts for debugging (optional)"
    )
    soft_filter_message: Optional[str] = Field(
        None, description="User-facing message when constraints are relaxed"
    )
    location_resolved: Optional[str] = Field(
        None, description="Resolved location name for display (if available)"
    )
    location_not_found: bool = Field(
        False, description="True if the location text could not be resolved"
    )
    # Near me location resolution status
    requires_auth: bool = Field(
        False, description="True if 'near me' was requested but user is not authenticated"
    )
    requires_address: bool = Field(
        False, description="True if 'near me' was requested but user has no saved address"
    )
    location_message: Optional[str] = Field(
        None, description="User-facing message for location-related issues"
    )
    diagnostics: Optional[SearchDiagnostics] = Field(
        None, description="Detailed diagnostics for admin tooling"
    )


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


class SearchClickRequest(BaseModel):
    """Request payload for logging a search click."""

    search_query_id: str = Field(..., description="Search query ID from NL search")
    instructor_id: str = Field(..., description="Instructor user ID that was clicked")
    service_id: Optional[str] = Field(
        None, description="Service ID that was clicked (instructor_service_id)"
    )
    position: int = Field(..., ge=1, description="Position in search results (1-indexed)")
    action: str = Field("view", description="Action type: view, book, message, favorite")


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


class AdminSearchConfigResponse(BaseModel):
    """Admin search configuration with runtime controls."""

    parsing_model: str = Field(..., description="Current parsing model")
    parsing_timeout_ms: int = Field(..., ge=500, le=10000, description="Parsing timeout in ms")
    embedding_model: str = Field(..., description="Current embedding model")
    embedding_timeout_ms: int = Field(..., ge=500, le=10000, description="Embedding timeout in ms")
    location_model: str = Field(..., description="Current location model")
    location_timeout_ms: int = Field(
        ..., ge=500, le=10000, description="Location LLM timeout in ms"
    )
    search_budget_ms: int = Field(..., ge=50, description="Default request budget in ms")
    high_load_budget_ms: int = Field(..., ge=50, description="High load budget in ms")
    high_load_threshold: int = Field(
        ..., ge=1, description="Concurrent requests to trigger high load"
    )
    uncached_concurrency: int = Field(
        ..., ge=1, description="Max concurrent uncached searches per worker"
    )
    openai_max_retries: int = Field(..., ge=0, description="OpenAI max retries")
    current_in_flight_requests: int = Field(
        ..., ge=0, description="Current in-flight uncached searches"
    )
    available_parsing_models: List[ModelOption] = Field(..., description="Available parsing models")
    available_embedding_models: List[ModelOption] = Field(
        ..., description="Available embedding models"
    )


class AdminSearchConfigUpdate(BaseModel):
    """Admin update payload for search runtime settings."""

    parsing_model: Optional[str] = Field(None, description="New parsing model")
    parsing_timeout_ms: Optional[int] = Field(
        None, ge=500, le=10000, description="New parsing timeout in ms"
    )
    embedding_timeout_ms: Optional[int] = Field(
        None, ge=500, le=10000, description="New embedding timeout in ms"
    )
    location_model: Optional[str] = Field(None, description="New location model")
    location_timeout_ms: Optional[int] = Field(
        None, ge=500, le=10000, description="New location LLM timeout in ms"
    )
    search_budget_ms: Optional[int] = Field(None, ge=50, description="New request budget in ms")
    high_load_budget_ms: Optional[int] = Field(
        None, ge=50, description="New high load budget in ms"
    )
    high_load_threshold: Optional[int] = Field(None, ge=1, description="New high load threshold")
    uncached_concurrency: Optional[int] = Field(
        None, ge=1, description="New uncached concurrency limit"
    )
    openai_max_retries: Optional[int] = Field(None, ge=0, description="New OpenAI max retries")
