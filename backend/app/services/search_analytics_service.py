# backend/app/services/search_analytics_service.py
"""
Search Analytics Service for InstaInstru Platform.

Business logic layer for search analytics dashboards.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from ..repositories.search_analytics_repository import (
    DailySearchTrendData,
    PopularSearchData,
    SearchAnalyticsRepository,
    SearchReferrerData,
)
from .base import BaseService


@dataclass
class DateRange:
    """Date range for analytics queries."""

    start: date
    end: date
    days: int


class SearchAnalyticsService(BaseService):
    """Service for search analytics operations."""

    def __init__(
        self,
        db: Session,
        repository: Optional[SearchAnalyticsRepository] = None,
    ):
        """
        Initialize service with database session.

        Args:
            db: SQLAlchemy session
            repository: Optional repository instance (for testing)
        """
        super().__init__(db)
        self.repository = repository or SearchAnalyticsRepository(db)

    def _get_date_range(self, days: int) -> DateRange:
        """Calculate date range from days parameter."""
        end_date = datetime.now(timezone.utc).date()
        start_date = end_date - timedelta(days=days - 1)
        return DateRange(start=start_date, end=end_date, days=days)

    def _get_datetime_range(self, days: int) -> Tuple[datetime, datetime]:
        """Calculate datetime range from days parameter."""
        end_datetime = datetime.now(timezone.utc)
        start_datetime = end_datetime - timedelta(days=days)
        return start_datetime, end_datetime

    # ===== Search Trends =====

    @BaseService.measure_operation("get_search_trends")
    def get_search_trends(self, days: int = 30) -> List[DailySearchTrendData]:
        """
        Get search trends over time.

        Args:
            days: Number of days to include

        Returns:
            List of daily search trend data
        """
        date_range = self._get_date_range(days)
        return self.repository.get_search_trends(date_range.start, date_range.end)

    @BaseService.measure_operation("get_popular_searches")
    def get_popular_searches(self, days: int = 30, limit: int = 20) -> List[PopularSearchData]:
        """
        Get most popular search queries.

        Args:
            days: Number of days to include
            limit: Maximum results to return

        Returns:
            List of popular search data
        """
        date_range = self._get_date_range(days)
        return self.repository.get_popular_searches(date_range.start, date_range.end, limit)

    @BaseService.measure_operation("get_search_referrers")
    def get_search_referrers(self, days: int = 30) -> List[SearchReferrerData]:
        """
        Get pages that drive searches.

        Args:
            days: Number of days to include

        Returns:
            List of referrer data
        """
        date_range = self._get_date_range(days)
        return self.repository.get_search_referrers(date_range.start, date_range.end)

    # ===== Search Analytics Summary =====

    @BaseService.measure_operation("get_search_analytics_summary")
    def get_search_analytics_summary(self, days: int = 30) -> Dict[str, Any]:
        """
        Get comprehensive search analytics summary.

        Args:
            days: Number of days to include

        Returns:
            Dictionary with totals, users, search_types, conversions, performance
        """
        date_range = self._get_date_range(days)
        start = date_range.start
        end = date_range.end

        # Get aggregate data
        totals = self.repository.get_search_totals(start, end)
        type_breakdown = self.repository.get_search_type_breakdown(start, end)
        deleted_searches = self.repository.count_deleted_searches(start, end)
        guest_sessions = self.repository.count_guest_sessions(start, end)
        converted_guests = self.repository.count_converted_guests(start, end)
        zero_results = self.repository.count_zero_result_searches(start, end)
        most_effective = self.repository.get_most_effective_search_type(start, end)

        total_searches = totals.total_searches
        unique_users = totals.unique_users
        unique_guests = totals.unique_guests
        total_users = unique_users + unique_guests

        # Build search types dict
        search_types = {}
        for st in type_breakdown:
            search_types[st.search_type] = {
                "count": st.count,
                "percentage": round(
                    (st.count / total_searches * 100) if total_searches > 0 else 0, 2
                ),
            }

        return {
            "date_range": {
                "start": start.isoformat(),
                "end": end.isoformat(),
                "days": days,
            },
            "totals": {
                "total_searches": total_searches,
                "unique_users": unique_users,
                "unique_guests": unique_guests,
                "total_users": total_users,
                "deleted_searches": deleted_searches,
                "deletion_rate": round(
                    (deleted_searches / total_searches * 100) if total_searches > 0 else 0,
                    2,
                ),
            },
            "users": {
                "authenticated": unique_users,
                "guests": unique_guests,
                "converted_guests": converted_guests,
                "user_percentage": round(
                    (unique_users / total_users * 100) if total_users > 0 else 0, 2
                ),
                "guest_percentage": round(
                    (unique_guests / total_users * 100) if total_users > 0 else 0, 2
                ),
            },
            "search_types": search_types,
            "conversions": {
                "guest_sessions": {
                    "total": guest_sessions,
                    "converted": converted_guests,
                    "conversion_rate": round(
                        (converted_guests / guest_sessions * 100) if guest_sessions > 0 else 0,
                        2,
                    ),
                },
                "conversion_behavior": {
                    "avg_searches_before_conversion": 0,
                    "avg_days_to_conversion": 0,
                    "most_common_first_search": "",
                },
            },
            "performance": {
                "avg_results_per_search": round(totals.avg_results, 2),
                "zero_result_rate": round(
                    (zero_results / total_searches * 100) if total_searches > 0 else 0,
                    2,
                ),
                "most_effective_type": most_effective[0] if most_effective else "",
            },
        }

    # ===== Conversion Metrics =====

    @BaseService.measure_operation("get_conversion_metrics")
    def get_conversion_metrics(self, days: int = 30) -> Dict[str, Any]:
        """
        Get guest-to-user conversion metrics.

        Args:
            days: Number of days to include

        Returns:
            Dictionary with period, guest_sessions, conversion_behavior, guest_engagement
        """
        date_range = self._get_date_range(days)
        start = date_range.start
        end = date_range.end

        guest_sessions = self.repository.count_guest_sessions(start, end)
        converted_guests = self.repository.count_converted_guests(start, end)
        engaged_sessions = self.repository.count_engaged_guest_sessions(start, end)
        avg_searches = self.repository.get_avg_searches_per_guest(start, end)

        return {
            "period": {
                "start": start.isoformat(),
                "end": end.isoformat(),
                "days": days,
            },
            "guest_sessions": {
                "total": guest_sessions,
                "converted": converted_guests,
                "conversion_rate": round(
                    (converted_guests / guest_sessions * 100) if guest_sessions > 0 else 0,
                    2,
                ),
            },
            "conversion_behavior": {
                "avg_searches_before_conversion": 0,
                "avg_days_to_conversion": 0,
                "most_common_first_search": "",
            },
            "guest_engagement": {
                "avg_searches_per_session": round(avg_searches, 2),
                "engaged_sessions": engaged_sessions,
                "engagement_rate": round(
                    (engaged_sessions / guest_sessions * 100) if guest_sessions > 0 else 0,
                    2,
                ),
            },
        }

    # ===== Search Performance =====

    @BaseService.measure_operation("get_search_performance")
    def get_search_performance(self, days: int = 30) -> Dict[str, Any]:
        """
        Get search performance metrics.

        Args:
            days: Number of days to include

        Returns:
            Dictionary with result_distribution, effectiveness, problematic_queries
        """
        date_range = self._get_date_range(days)
        start = date_range.start
        end = date_range.end

        # Result distribution
        zero_results = self.repository.count_zero_result_searches(start, end)
        one_to_five = self.repository.count_searches_in_result_range(start, end, 1, 5)
        six_to_ten = self.repository.count_searches_in_result_range(start, end, 6, 10)
        over_ten = self.repository.count_searches_in_result_range(start, end, 11)

        # Effectiveness
        effectiveness = self.repository.get_search_effectiveness(start, end)
        searches_with_results = self.repository.count_searches_with_results(start, end)

        # Problematic queries
        problematic = self.repository.get_problematic_queries(start, end)

        total_searches = effectiveness.total_searches

        return {
            "result_distribution": {
                "zero_results": zero_results,
                "1_5_results": one_to_five,
                "6_10_results": six_to_ten,
                "over_10_results": over_ten,
            },
            "effectiveness": {
                "avg_results_per_search": round(effectiveness.avg_results, 2),
                "median_results": round(effectiveness.avg_results, 2),  # Approximation
                "searches_with_results": searches_with_results,
                "zero_result_rate": round(
                    (zero_results / total_searches * 100) if total_searches > 0 else 0,
                    2,
                ),
            },
            "problematic_queries": [
                {
                    "query": q.query,
                    "count": q.count,
                    "avg_results": q.avg_results,
                }
                for q in problematic
            ],
        }

    # ===== Candidate Analytics =====

    @BaseService.measure_operation("get_candidate_summary")
    def get_candidate_summary(self, days: int = 30) -> Dict[str, Any]:
        """
        Get summary statistics for search candidates.

        Args:
            days: Number of days to include

        Returns:
            Dictionary with candidate summary data
        """
        start_dt, end_dt = self._get_datetime_range(days)
        summary = self.repository.get_candidate_summary(start_dt, end_dt)

        avg_candidates = 0.0
        if summary.events_with_candidates > 0:
            avg_candidates = round(
                summary.total_candidates / float(summary.events_with_candidates), 2
            )

        return {
            "total_candidates": summary.total_candidates,
            "events_with_candidates": summary.events_with_candidates,
            "avg_candidates_per_event": avg_candidates,
            "zero_result_events_with_candidates": summary.zero_result_events_with_candidates,
            "source_breakdown": summary.source_breakdown,
        }

    @BaseService.measure_operation("get_candidate_category_trends")
    def get_candidate_category_trends(self, days: int = 30) -> List[Dict[str, Any]]:
        """
        Get candidate counts by date and category.

        Args:
            days: Number of days to include

        Returns:
            List of category trend data dicts
        """
        start_dt, end_dt = self._get_datetime_range(days)
        trends = self.repository.get_candidate_category_trends(start_dt, end_dt)

        return [{"date": str(t.date), "category": t.category, "count": t.count} for t in trends]

    @BaseService.measure_operation("get_candidate_top_services")
    def get_candidate_top_services(self, days: int = 30, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Get top services by candidate count with opportunity scores.

        Args:
            days: Number of days to include
            limit: Maximum results to return

        Returns:
            List of top service data dicts with opportunity scores
        """
        start_dt, end_dt = self._get_datetime_range(days)
        services = self.repository.get_candidate_top_services(start_dt, end_dt, limit)

        # Get instructor counts for services
        service_ids = [s.service_catalog_id for s in services]
        supply_map = self.repository.get_service_instructor_counts(service_ids)

        result = []
        for s in services:
            active_instructors = supply_map.get(s.service_catalog_id, 0)
            opportunity = float(s.candidate_count) / max(1, active_instructors)
            result.append(
                {
                    "service_catalog_id": s.service_catalog_id,
                    "service_name": s.service_name,
                    "category_name": s.category_name,
                    "candidate_count": s.candidate_count,
                    "avg_score": s.avg_score,
                    "avg_position": s.avg_position,
                    "active_instructors": active_instructors,
                    "opportunity_score": round(opportunity, 2),
                }
            )

        return result

    @BaseService.measure_operation("get_candidate_score_distribution")
    def get_candidate_score_distribution(self, days: int = 30) -> Dict[str, int]:
        """
        Get candidate score distribution.

        Args:
            days: Number of days to include

        Returns:
            Dictionary with score bucket counts
        """
        start_dt, end_dt = self._get_datetime_range(days)

        gte_0_90 = self.repository.count_candidates_by_score_range(start_dt, end_dt, 0.9)
        gte_0_80_lt_0_90 = self.repository.count_candidates_by_score_range(
            start_dt, end_dt, 0.8, 0.9
        )
        gte_0_70_lt_0_80 = self.repository.count_candidates_by_score_range(
            start_dt, end_dt, 0.7, 0.8
        )
        lt_0_70 = self.repository.count_candidates_below_score(start_dt, end_dt, 0.7)

        return {
            "gte_0_90": gte_0_90,
            "gte_0_80_lt_0_90": gte_0_80_lt_0_90,
            "gte_0_70_lt_0_80": gte_0_70_lt_0_80,
            "lt_0_70": lt_0_70,
        }

    @BaseService.measure_operation("get_candidate_service_queries")
    def get_candidate_service_queries(
        self, service_catalog_id: str, days: int = 30, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Get queries that produced candidates for a service.

        Args:
            service_catalog_id: Service catalog ID
            days: Number of days to include
            limit: Maximum results to return

        Returns:
            List of query data dicts
        """
        start_dt, end_dt = self._get_datetime_range(days)
        queries = self.repository.get_candidate_service_queries(
            service_catalog_id, start_dt, end_dt, limit
        )

        return [
            {
                "searched_at": q.searched_at.isoformat() if q.searched_at else "",
                "search_query": q.search_query or "",
                "results_count": q.results_count,
                "position": q.position,
                "score": q.score,
                "source": q.source,
            }
            for q in queries
        ]
