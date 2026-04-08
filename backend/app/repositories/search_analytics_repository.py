"""Search analytics repository facade backed by focused internal mixins."""

import logging

from sqlalchemy.orm import Session

from .search_analytics.candidate_analytics_mixin import CandidateAnalyticsMixin
from .search_analytics.guest_analytics_mixin import GuestAnalyticsMixin
from .search_analytics.nl_search_analytics_mixin import NLSearchAnalyticsMixin
from .search_analytics.nl_search_write_mixin import NLSearchWriteMixin
from .search_analytics.search_metrics_mixin import SearchMetricsMixin
from .search_analytics.search_trends_mixin import SearchTrendsMixin
from .search_analytics.types import (
    CandidateServiceQueryData,
    CandidateSummaryData,
    CategoryTrendData,
    DailySearchTrendData,
    PopularSearchData,
    ProblematicQueryData,
    SearchEffectivenessData,
    SearchReferrerData,
    SearchTotalsData,
    SearchTypeBreakdown,
    ServiceSupplyData,
    TopServiceData,
)

__all__ = [
    "SearchAnalyticsRepository",
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

logger = logging.getLogger(__name__)


class SearchAnalyticsRepository(
    SearchTrendsMixin,
    SearchMetricsMixin,
    GuestAnalyticsMixin,
    CandidateAnalyticsMixin,
    NLSearchWriteMixin,
    NLSearchAnalyticsMixin,
):
    """Search analytics repository facade backed by focused internal mixins."""

    def __init__(self, db: Session) -> None:
        """Initialize with database session."""
        self.db = db
        self.logger = logging.getLogger(__name__)
