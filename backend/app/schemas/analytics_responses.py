from ._strict_base import StrictModel

"""
Response schemas for analytics endpoints.

These schemas ensure consistent response formats for all analytics
and reporting endpoints.
"""

from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, RootModel


class DailySearchTrend(BaseModel):
    """Daily search trend data."""

    date: str = Field(description="Date in ISO format")
    total_searches: int = Field(description="Total searches for the day")
    unique_users: int = Field(description="Unique authenticated users")
    unique_guests: int = Field(description="Unique guest sessions")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "date": "2025-01-20",
                "total_searches": 1234,
                "unique_users": 150,
                "unique_guests": 200,
            }
        }
    )


class SearchTrendsResponse(RootModel[List[DailySearchTrend]]):
    """Search trends over time response."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": [
                {
                    "date": "2025-01-20",
                    "total_searches": 1234,
                    "unique_users": 150,
                    "unique_guests": 200,
                }
            ]
        }
    )


class PopularSearch(BaseModel):
    """Popular search query data."""

    query: str = Field(description="Search query text")
    search_count: int = Field(description="Number of times searched")
    unique_users: int = Field(description="Number of unique users who searched")
    average_results: float = Field(description="Average number of results returned")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "query": "yoga instructor",
                "search_count": 523,
                "unique_users": 201,
                "average_results": 15.7,
            }
        }
    )


class PopularSearchesResponse(RootModel[List[PopularSearch]]):
    """Popular searches response."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": [
                {
                    "query": "yoga instructor",
                    "search_count": 523,
                    "unique_users": 201,
                    "average_results": 15.7,
                }
            ]
        }
    )


class SearchReferrer(BaseModel):
    """Search referrer page data."""

    page: str = Field(description="Referrer page URL or path")
    search_count: int = Field(description="Number of searches from this page")
    unique_sessions: int = Field(description="Number of unique sessions")
    search_types: List[str] = Field(description="Types of searches from this page")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "page": "/instructors/123",
                "search_count": 250,
                "unique_sessions": 180,
                "search_types": ["related", "category"],
            }
        }
    )


class SearchReferrersResponse(RootModel[List[SearchReferrer]]):
    """Search referrers response."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": [
                {
                    "page": "/instructors/123",
                    "search_count": 250,
                    "unique_sessions": 180,
                    "search_types": ["related", "category"],
                }
            ]
        }
    )


class DateRange(BaseModel):
    """Date range for analytics."""

    start: str = Field(description="Start date in ISO format")
    end: str = Field(description="End date in ISO format")
    days: int = Field(description="Number of days in range")

    model_config = ConfigDict(
        json_schema_extra={"example": {"start": "2025-01-01", "end": "2025-01-31", "days": 31}}
    )


class SearchTotals(BaseModel):
    """Search totals and deletion metrics."""

    total_searches: int = Field(description="Total number of searches")
    unique_users: int = Field(description="Unique authenticated users")
    unique_guests: int = Field(description="Unique guest sessions")
    total_users: int = Field(description="Total unique users (authenticated + guests)")
    deleted_searches: int = Field(description="Number of deleted searches")
    deletion_rate: float = Field(description="Percentage of searches deleted")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "total_searches": 10000,
                "unique_users": 500,
                "unique_guests": 800,
                "total_users": 1300,
                "deleted_searches": 100,
                "deletion_rate": 1.0,
            }
        }
    )


class UserBreakdown(BaseModel):
    """User type breakdown."""

    authenticated: int = Field(description="Number of authenticated users")
    guests: int = Field(description="Number of guest sessions")
    converted_guests: int = Field(description="Number of guests who converted to users")
    user_percentage: float = Field(description="Percentage of authenticated users")
    guest_percentage: float = Field(description="Percentage of guests")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "authenticated": 500,
                "guests": 800,
                "converted_guests": 50,
                "user_percentage": 38.46,
                "guest_percentage": 61.54,
            }
        }
    )


class SearchTypeMetrics(BaseModel):
    """Metrics for a search type."""

    count: int = Field(description="Number of searches of this type")
    percentage: float = Field(description="Percentage of total searches")

    model_config = ConfigDict(json_schema_extra={"example": {"count": 2500, "percentage": 25.0}})


class GuestConversionMetrics(BaseModel):
    """Guest session conversion metrics."""

    total: int = Field(description="Total guest sessions")
    converted: int = Field(description="Number of converted sessions")
    conversion_rate: float = Field(description="Conversion rate percentage")

    model_config = ConfigDict(
        json_schema_extra={"example": {"total": 800, "converted": 50, "conversion_rate": 6.25}}
    )


class ConversionBehavior(BaseModel):
    """Conversion behavior metrics."""

    avg_searches_before_conversion: float = Field(description="Average searches before conversion")
    avg_days_to_conversion: float = Field(description="Average days to conversion")
    most_common_first_search: str = Field(description="Most common first search query")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "avg_searches_before_conversion": 3.5,
                "avg_days_to_conversion": 2.3,
                "most_common_first_search": "yoga classes",
            }
        }
    )


class PerformanceMetrics(BaseModel):
    """Search performance metrics."""

    avg_results_per_search: float = Field(description="Average results per search")
    zero_result_rate: float = Field(description="Percentage of searches with zero results")
    most_effective_type: str = Field(description="Most effective search type")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "avg_results_per_search": 15.7,
                "zero_result_rate": 5.2,
                "most_effective_type": "natural_language",
            }
        }
    )


class ConversionMetrics(BaseModel):
    """Combined conversion metrics."""

    guest_sessions: GuestConversionMetrics = Field(description="Guest session metrics")
    conversion_behavior: ConversionBehavior = Field(description="Conversion behavior metrics")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "guest_sessions": {"total": 800, "converted": 50, "conversion_rate": 6.25},
                "conversion_behavior": {
                    "avg_searches_before_conversion": 3.5,
                    "avg_days_to_conversion": 2.3,
                    "most_common_first_search": "yoga classes",
                },
            }
        }
    )


class SearchAnalyticsSummaryResponse(StrictModel):
    """Comprehensive search analytics summary."""

    date_range: DateRange = Field(description="Date range for analytics")
    totals: SearchTotals = Field(description="Search totals and metrics")
    users: UserBreakdown = Field(description="User breakdown by type")
    search_types: Dict[str, SearchTypeMetrics] = Field(description="Breakdown by search type")
    conversions: ConversionMetrics = Field(description="Conversion metrics")
    performance: PerformanceMetrics = Field(description="Search performance metrics")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "date_range": {"start": "2025-01-01", "end": "2025-01-31", "days": 31},
                "totals": {
                    "total_searches": 10000,
                    "unique_users": 500,
                    "unique_guests": 800,
                    "total_users": 1300,
                    "deleted_searches": 100,
                    "deletion_rate": 1.0,
                },
                "users": {
                    "authenticated": 500,
                    "guests": 800,
                    "converted_guests": 50,
                    "user_percentage": 38.46,
                    "guest_percentage": 61.54,
                },
                "search_types": {
                    "natural_language": {"count": 5000, "percentage": 50.0},
                    "category": {"count": 3000, "percentage": 30.0},
                    "quick": {"count": 2000, "percentage": 20.0},
                },
                "conversions": {
                    "guest_sessions": {"total": 800, "converted": 50, "conversion_rate": 6.25},
                    "conversion_behavior": {
                        "avg_searches_before_conversion": 0,
                        "avg_days_to_conversion": 0,
                        "most_common_first_search": "",
                    },
                },
                "performance": {
                    "avg_results_per_search": 15.7,
                    "zero_result_rate": 5.2,
                    "most_effective_type": "natural_language",
                },
            }
        }
    )


class GuestEngagement(BaseModel):
    """Guest engagement metrics."""

    avg_searches_per_session: float = Field(description="Average searches per guest session")
    engaged_sessions: int = Field(description="Sessions with multiple searches")
    engagement_rate: float = Field(description="Percentage of engaged sessions")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "avg_searches_per_session": 2.5,
                "engaged_sessions": 400,
                "engagement_rate": 50.0,
            }
        }
    )


class ConversionMetricsResponse(StrictModel):
    """Guest-to-user conversion metrics response."""

    period: DateRange = Field(description="Time period for metrics")
    guest_sessions: GuestConversionMetrics = Field(description="Guest session conversion metrics")
    conversion_behavior: ConversionBehavior = Field(description="Conversion behavior patterns")
    guest_engagement: GuestEngagement = Field(description="Guest engagement metrics")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "period": {"start": "2025-01-01", "end": "2025-01-31", "days": 31},
                "guest_sessions": {"total": 800, "converted": 50, "conversion_rate": 6.25},
                "conversion_behavior": {
                    "avg_searches_before_conversion": 0,
                    "avg_days_to_conversion": 0,
                    "most_common_first_search": "",
                },
                "guest_engagement": {
                    "avg_searches_per_session": 2.5,
                    "engaged_sessions": 400,
                    "engagement_rate": 50.0,
                },
            }
        }
    )


class ResultDistribution(BaseModel):
    """Search result distribution."""

    zero_results: int = Field(description="Searches with zero results")
    one_to_five_results: int = Field(description="Searches with 1-5 results", alias="1_5_results")
    six_to_ten_results: int = Field(description="Searches with 6-10 results", alias="6_10_results")
    over_ten_results: int = Field(
        description="Searches with over 10 results", alias="over_10_results"
    )

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "zero_results": 500,
                "1_5_results": 2000,
                "6_10_results": 3000,
                "over_10_results": 4500,
            }
        },
    )


class SearchEffectiveness(BaseModel):
    """Search effectiveness metrics."""

    avg_results_per_search: float = Field(description="Average results per search")
    median_results: float = Field(description="Median results per search")
    searches_with_results: int = Field(description="Number of searches with at least one result")
    zero_result_rate: float = Field(description="Percentage of searches with zero results")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "avg_results_per_search": 15.7,
                "median_results": 12.0,
                "searches_with_results": 9500,
                "zero_result_rate": 5.0,
            }
        }
    )


class ProblematicQuery(BaseModel):
    """Problematic search query with low results."""

    query: str = Field(description="Search query text")
    count: int = Field(description="Number of times searched")
    avg_results: float = Field(description="Average results returned")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "query": "advanced quantum physics tutor",
                "count": 25,
                "avg_results": 0.5,
            }
        }
    )


class SearchPerformanceResponse(StrictModel):
    """Search performance metrics response."""

    result_distribution: ResultDistribution = Field(description="Distribution of search results")
    effectiveness: SearchEffectiveness = Field(description="Search effectiveness metrics")
    problematic_queries: List[ProblematicQuery] = Field(description="Queries with poor results")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "result_distribution": {
                    "zero_results": 500,
                    "1_5_results": 2000,
                    "6_10_results": 3000,
                    "over_10_results": 4500,
                },
                "effectiveness": {
                    "avg_results_per_search": 15.7,
                    "median_results": 12.0,
                    "searches_with_results": 9500,
                    "zero_result_rate": 5.0,
                },
                "problematic_queries": [
                    {
                        "query": "advanced quantum physics tutor",
                        "count": 25,
                        "avg_results": 0.5,
                    }
                ],
            }
        }
    )


class ExportAnalyticsResponse(StrictModel):
    """Analytics export response."""

    message: str = Field(description="Status message")
    format: str = Field(description="Export format (csv, xlsx, json)")
    user: str = Field(description="User email who requested export")
    status: str = Field(description="Export status")
    download_url: Optional[str] = Field(default=None, description="Download URL when ready")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "message": "Export analytics endpoint",
                "format": "csv",
                "user": "admin@instainstru.com",
                "status": "Not implemented",
                "download_url": None,
            }
        }
    )


# ===== Candidates (Top-N) Analytics Schemas =====


class CandidateSummaryResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    total_candidates: int
    events_with_candidates: int
    avg_candidates_per_event: float
    zero_result_events_with_candidates: int
    source_breakdown: Dict[str, int]


class CandidateCategoryTrend(BaseModel):
    date: str
    category: str
    count: int


class CandidateCategoryTrendsResponse(RootModel[List[CandidateCategoryTrend]]):
    pass


class CandidateTopService(BaseModel):
    service_catalog_id: str
    service_name: str
    category_name: str
    candidate_count: int
    avg_score: float
    avg_position: float
    active_instructors: int
    opportunity_score: float


class CandidateTopServicesResponse(RootModel[List[CandidateTopService]]):
    pass


class CandidateServiceQuery(BaseModel):
    searched_at: str
    search_query: str
    results_count: Optional[int]
    position: int
    score: Optional[float]
    source: Optional[str]


class CandidateServiceQueriesResponse(RootModel[List[CandidateServiceQuery]]):
    pass


class CandidateScoreDistributionResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    gte_0_90: int
    gte_0_80_lt_0_90: int
    gte_0_70_lt_0_80: int
    lt_0_70: int
