"""Time-series and top-level search trend analytics."""

from datetime import date
from typing import List

from sqlalchemy import and_, desc, func

from ...models.search_event import SearchEvent
from .mixin_base import SearchAnalyticsRepositoryMixinBase
from .types import DailySearchTrendData, PopularSearchData, SearchReferrerData


class SearchTrendsMixin(SearchAnalyticsRepositoryMixinBase):
    """Time-series aggregations on search events."""

    def get_search_trends(self, start_date: date, end_date: date) -> List[DailySearchTrendData]:
        """
        Get daily search trends within date range.

        Args:
            start_date: Start of date range
            end_date: End of date range

        Returns:
            List of daily search trend data
        """
        rows = (
            self.db.query(
                func.date(SearchEvent.searched_at).label("date"),
                func.count(SearchEvent.id).label("total_searches"),
                func.count(func.distinct(SearchEvent.user_id)).label("unique_users"),
                func.count(func.distinct(SearchEvent.guest_session_id)).label("unique_guests"),
            )
            .filter(
                and_(
                    func.date(SearchEvent.searched_at) >= start_date,
                    func.date(SearchEvent.searched_at) <= end_date,
                )
            )
            .group_by(func.date(SearchEvent.searched_at))
            .order_by(func.date(SearchEvent.searched_at))
            .all()
        )

        return [
            DailySearchTrendData(
                date=row.date,
                total_searches=row.total_searches,
                unique_users=row.unique_users or 0,
                unique_guests=row.unique_guests or 0,
            )
            for row in rows
        ]

    def get_popular_searches(
        self, start_date: date, end_date: date, limit: int = 20
    ) -> List[PopularSearchData]:
        """
        Get most popular search queries within date range.

        Args:
            start_date: Start of date range
            end_date: End of date range
            limit: Maximum results to return

        Returns:
            List of popular search data
        """
        rows = (
            self.db.query(
                SearchEvent.search_query,
                func.count(SearchEvent.id).label("search_count"),
                func.count(func.distinct(SearchEvent.user_id)).label("unique_users"),
                func.avg(SearchEvent.results_count).label("average_results"),
            )
            .filter(
                and_(
                    func.date(SearchEvent.searched_at) >= start_date,
                    func.date(SearchEvent.searched_at) <= end_date,
                    SearchEvent.search_query.isnot(None),
                    SearchEvent.search_query != "",
                )
            )
            .group_by(SearchEvent.search_query)
            .order_by(desc("search_count"))
            .limit(limit)
            .all()
        )

        return [
            PopularSearchData(
                query=row.search_query,
                search_count=row.search_count,
                unique_users=row.unique_users or 0,
                average_results=round(row.average_results or 0, 2),
            )
            for row in rows
        ]

    def get_search_referrers(self, start_date: date, end_date: date) -> List[SearchReferrerData]:
        """
        Get pages that drive searches (referrers).

        Args:
            start_date: Start of date range
            end_date: End of date range

        Returns:
            List of referrer data
        """
        rows = (
            self.db.query(
                SearchEvent.referrer,
                func.count(SearchEvent.id).label("search_count"),
                func.count(func.distinct(SearchEvent.session_id)).label("unique_sessions"),
            )
            .filter(
                and_(
                    func.date(SearchEvent.searched_at) >= start_date,
                    func.date(SearchEvent.searched_at) <= end_date,
                    SearchEvent.referrer.isnot(None),
                    SearchEvent.referrer != "",
                )
            )
            .group_by(SearchEvent.referrer)
            .order_by(desc("search_count"))
            .all()
        )

        return [
            SearchReferrerData(
                referrer=row.referrer,
                search_count=row.search_count,
                unique_sessions=row.unique_sessions or 0,
            )
            for row in rows
        ]
