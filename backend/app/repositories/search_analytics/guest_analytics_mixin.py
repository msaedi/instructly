"""Guest session and conversion analytics."""

from datetime import date

from sqlalchemy import and_, func

from ...models.search_history import SearchHistory
from .mixin_base import SearchAnalyticsRepositoryMixinBase


class GuestAnalyticsMixin(SearchAnalyticsRepositoryMixinBase):
    """SearchHistory queries for guest session behavior."""

    def count_deleted_searches(self, start_date: date, end_date: date) -> int:
        """
        Count deleted searches within date range.

        Args:
            start_date: Start of date range
            end_date: End of date range

        Returns:
            Count of deleted searches
        """
        return (
            self.db.query(func.count(SearchHistory.id))
            .filter(
                and_(
                    SearchHistory.deleted_at.isnot(None),
                    func.date(SearchHistory.deleted_at) >= start_date,
                    func.date(SearchHistory.deleted_at) <= end_date,
                )
            )
            .scalar()
            or 0
        )

    def count_guest_sessions(self, start_date: date, end_date: date) -> int:
        """
        Count unique guest sessions within date range.

        Args:
            start_date: Start of date range
            end_date: End of date range

        Returns:
            Count of unique guest sessions
        """
        return (
            self.db.query(func.count(func.distinct(SearchHistory.guest_session_id)))
            .filter(
                and_(
                    SearchHistory.guest_session_id.isnot(None),
                    func.date(SearchHistory.first_searched_at) >= start_date,
                    func.date(SearchHistory.first_searched_at) <= end_date,
                )
            )
            .scalar()
            or 0
        )

    def count_converted_guests(self, start_date: date, end_date: date) -> int:
        """
        Count guest sessions that converted to users.

        Args:
            start_date: Start of date range
            end_date: End of date range

        Returns:
            Count of converted guest sessions
        """
        return (
            self.db.query(func.count(func.distinct(SearchHistory.guest_session_id)))
            .filter(
                and_(
                    SearchHistory.guest_session_id.isnot(None),
                    SearchHistory.converted_to_user_id.isnot(None),
                    func.date(SearchHistory.first_searched_at) >= start_date,
                    func.date(SearchHistory.first_searched_at) <= end_date,
                )
            )
            .scalar()
            or 0
        )

    def count_engaged_guest_sessions(self, start_date: date, end_date: date) -> int:
        """
        Count guest sessions with multiple searches.

        Args:
            start_date: Start of date range
            end_date: End of date range

        Returns:
            Count of engaged guest sessions
        """
        return (
            self.db.query(func.count(func.distinct(SearchHistory.guest_session_id)))
            .filter(
                and_(
                    SearchHistory.guest_session_id.isnot(None),
                    SearchHistory.search_count > 1,
                    func.date(SearchHistory.first_searched_at) >= start_date,
                    func.date(SearchHistory.first_searched_at) <= end_date,
                )
            )
            .scalar()
            or 0
        )

    def get_avg_searches_per_guest(self, start_date: date, end_date: date) -> float:
        """
        Get average searches per guest session.

        Args:
            start_date: Start of date range
            end_date: End of date range

        Returns:
            Average searches per guest session
        """
        return (
            self.db.query(func.avg(SearchHistory.search_count))
            .filter(
                and_(
                    SearchHistory.guest_session_id.isnot(None),
                    func.date(SearchHistory.first_searched_at) >= start_date,
                    func.date(SearchHistory.first_searched_at) <= end_date,
                )
            )
            .scalar()
            or 0
        )
