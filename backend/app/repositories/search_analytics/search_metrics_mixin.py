"""Point-in-time search metrics and quality analytics."""

from datetime import date
from typing import List, Optional, Tuple

from sqlalchemy import and_, desc, func

from ...models.search_event import SearchEvent
from .mixin_base import SearchAnalyticsRepositoryMixinBase
from .types import (
    ProblematicQueryData,
    SearchEffectivenessData,
    SearchTotalsData,
    SearchTypeBreakdown,
)


class SearchMetricsMixin(SearchAnalyticsRepositoryMixinBase):
    """SearchEvent point metrics and query quality analysis."""

    def get_search_totals(self, start_date: date, end_date: date) -> SearchTotalsData:
        """
        Get aggregate search totals within date range.

        Args:
            start_date: Start of date range
            end_date: End of date range

        Returns:
            Search totals data
        """
        row = (
            self.db.query(
                func.count(SearchEvent.id).label("total_searches"),
                func.count(func.distinct(SearchEvent.user_id)).label("unique_users"),
                func.count(func.distinct(SearchEvent.guest_session_id)).label("unique_guests"),
                func.avg(SearchEvent.results_count).label("avg_results"),
            )
            .filter(
                and_(
                    func.date(SearchEvent.searched_at) >= start_date,
                    func.date(SearchEvent.searched_at) <= end_date,
                )
            )
            .first()
        )

        return SearchTotalsData(
            total_searches=row.total_searches or 0,
            unique_users=row.unique_users or 0,
            unique_guests=row.unique_guests or 0,
            avg_results=float(row.avg_results or 0),
        )

    def get_search_type_breakdown(
        self, start_date: date, end_date: date
    ) -> List[SearchTypeBreakdown]:
        """
        Get search type distribution within date range.

        Args:
            start_date: Start of date range
            end_date: End of date range

        Returns:
            List of search type counts
        """
        rows = (
            self.db.query(SearchEvent.search_type, func.count(SearchEvent.id).label("count"))
            .filter(
                and_(
                    func.date(SearchEvent.searched_at) >= start_date,
                    func.date(SearchEvent.searched_at) <= end_date,
                )
            )
            .group_by(SearchEvent.search_type)
            .all()
        )

        return [SearchTypeBreakdown(search_type=row.search_type, count=row.count) for row in rows]

    def count_zero_result_searches(self, start_date: date, end_date: date) -> int:
        """
        Count searches with zero results.

        Args:
            start_date: Start of date range
            end_date: End of date range

        Returns:
            Count of zero result searches
        """
        return (
            self.db.query(func.count(SearchEvent.id))
            .filter(
                and_(
                    func.date(SearchEvent.searched_at) >= start_date,
                    func.date(SearchEvent.searched_at) <= end_date,
                    SearchEvent.results_count == 0,
                )
            )
            .scalar()
            or 0
        )

    def get_most_effective_search_type(
        self, start_date: date, end_date: date
    ) -> Optional[Tuple[str, float]]:
        """
        Get search type with highest average results.

        Args:
            start_date: Start of date range
            end_date: End of date range

        Returns:
            Tuple of (search_type, avg_results) or None
        """
        row = (
            self.db.query(
                SearchEvent.search_type,
                func.avg(SearchEvent.results_count).label("avg_results"),
            )
            .filter(
                and_(
                    func.date(SearchEvent.searched_at) >= start_date,
                    func.date(SearchEvent.searched_at) <= end_date,
                    SearchEvent.results_count.isnot(None),
                )
            )
            .group_by(SearchEvent.search_type)
            .order_by(desc("avg_results"))
            .first()
        )

        if row:
            return (row.search_type, float(row.avg_results or 0))
        return None

    def count_searches_with_results(self, start_date: date, end_date: date) -> int:
        """
        Count searches that returned at least one result.

        Args:
            start_date: Start of date range
            end_date: End of date range

        Returns:
            Count of searches with results
        """
        return (
            self.db.query(func.count(SearchEvent.id))
            .filter(
                and_(
                    func.date(SearchEvent.searched_at) >= start_date,
                    func.date(SearchEvent.searched_at) <= end_date,
                    SearchEvent.results_count.isnot(None),
                    SearchEvent.results_count > 0,
                )
            )
            .scalar()
            or 0
        )

    def count_searches_in_result_range(
        self, start_date: date, end_date: date, min_results: int, max_results: Optional[int] = None
    ) -> int:
        """
        Count searches with results in a specific range.

        Args:
            start_date: Start of date range
            end_date: End of date range
            min_results: Minimum result count (inclusive)
            max_results: Maximum result count (inclusive), None for no upper bound

        Returns:
            Count of searches in range
        """
        filters = [
            func.date(SearchEvent.searched_at) >= start_date,
            func.date(SearchEvent.searched_at) <= end_date,
            SearchEvent.results_count.isnot(None),
        ]

        if max_results is not None:
            filters.append(SearchEvent.results_count.between(min_results, max_results))
        else:
            filters.append(SearchEvent.results_count >= min_results)

        return self.db.query(func.count(SearchEvent.id)).filter(and_(*filters)).scalar() or 0

    def get_search_effectiveness(self, start_date: date, end_date: date) -> SearchEffectivenessData:
        """
        Get search effectiveness metrics.

        Args:
            start_date: Start of date range
            end_date: End of date range

        Returns:
            Search effectiveness data
        """
        row = (
            self.db.query(
                func.avg(SearchEvent.results_count).label("avg_results"),
                func.count(SearchEvent.id).label("total_searches"),
            )
            .filter(
                and_(
                    func.date(SearchEvent.searched_at) >= start_date,
                    func.date(SearchEvent.searched_at) <= end_date,
                    SearchEvent.results_count.isnot(None),
                )
            )
            .first()
        )

        return SearchEffectivenessData(
            avg_results=float(row.avg_results or 0),
            total_searches=row.total_searches or 0,
        )

    def get_problematic_queries(
        self, start_date: date, end_date: date, min_count: int = 5, limit: int = 10
    ) -> List[ProblematicQueryData]:
        """
        Get queries with low average results.

        Args:
            start_date: Start of date range
            end_date: End of date range
            min_count: Minimum search count to consider
            limit: Maximum results to return

        Returns:
            List of problematic query data
        """
        rows = (
            self.db.query(
                SearchEvent.search_query,
                func.count(SearchEvent.id).label("count"),
                func.avg(SearchEvent.results_count).label("avg_results"),
            )
            .filter(
                and_(
                    func.date(SearchEvent.searched_at) >= start_date,
                    func.date(SearchEvent.searched_at) <= end_date,
                    SearchEvent.results_count.isnot(None),
                    SearchEvent.search_query.isnot(None),
                    SearchEvent.search_query != "",
                )
            )
            .group_by(SearchEvent.search_query)
            .having(func.count(SearchEvent.id) >= min_count)
            .order_by(func.avg(SearchEvent.results_count))
            .limit(limit)
            .all()
        )

        return [
            ProblematicQueryData(
                query=row.search_query,
                count=row.count,
                avg_results=round(row.avg_results or 0, 2),
            )
            for row in rows
        ]
