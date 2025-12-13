# backend/app/schemas/nl_search.py
"""
Pydantic schemas for Natural Language search API.

These schemas define the response format for the NL search pipeline
that combines parsing, embedding, retrieval, filtering, and ranking.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


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
    """A single NL search result."""

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


class NLSearchResponse(BaseModel):
    """Complete NL search response."""

    results: List[NLSearchResult] = Field(..., description="Search results")
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
