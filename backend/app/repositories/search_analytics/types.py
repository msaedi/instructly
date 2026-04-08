"""Shared dataclasses for search analytics repository results."""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Dict, Optional

__all__ = [
    "DailySearchTrendData",
    "PopularSearchData",
    "SearchReferrerData",
    "SearchTotalsData",
    "SearchTypeBreakdown",
    "SearchEffectivenessData",
    "ProblematicQueryData",
    "CandidateSummaryData",
    "CategoryTrendData",
    "TopServiceData",
    "ServiceSupplyData",
    "CandidateServiceQueryData",
]


@dataclass
class DailySearchTrendData:
    """Daily search trend data."""

    date: date
    total_searches: int
    unique_users: int
    unique_guests: int


@dataclass
class PopularSearchData:
    """Popular search query data."""

    query: Optional[str]
    search_count: int
    unique_users: int
    average_results: float


@dataclass
class SearchReferrerData:
    """Search referrer data."""

    referrer: Optional[str]
    search_count: int
    unique_sessions: int


@dataclass
class SearchTotalsData:
    """Search totals aggregation."""

    total_searches: int
    unique_users: int
    unique_guests: int
    avg_results: float


@dataclass
class SearchTypeBreakdown:
    """Search type count."""

    search_type: Optional[str]
    count: int


@dataclass
class SearchEffectivenessData:
    """Search effectiveness metrics."""

    avg_results: float
    total_searches: int


@dataclass
class ProblematicQueryData:
    """Problematic search query data."""

    query: str
    count: int
    avg_results: float


@dataclass
class CandidateSummaryData:
    """Candidate summary data."""

    total_candidates: int
    events_with_candidates: int
    zero_result_events_with_candidates: int
    source_breakdown: Dict[str, int]


@dataclass
class CategoryTrendData:
    """Category trend data point."""

    date: date
    category: str
    count: int


@dataclass
class TopServiceData:
    """Top service candidate data."""

    service_catalog_id: str
    service_name: str
    category_name: str
    candidate_count: int
    avg_score: float
    avg_position: float


@dataclass
class ServiceSupplyData:
    """Active instructor count per service."""

    service_catalog_id: str
    count: int


@dataclass
class CandidateServiceQueryData:
    """Candidate service query data."""

    searched_at: Optional[datetime]
    search_query: Optional[str]
    results_count: Optional[int]
    position: Optional[int]
    score: Optional[float]
    source: Optional[str]
