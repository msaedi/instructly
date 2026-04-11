"""SearchHistory-backed analytics reads."""

from datetime import datetime
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Query

from ...models.search_history import SearchHistory
from .mixin_base import SearchAnalyticsRepositoryMixinBase


class SearchHistoryAnalyticsMixin(SearchAnalyticsRepositoryMixinBase):
    """Analytics queries that read from the deduplicated SearchHistory table."""

    def find_analytics_eligible_searches(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        include_deleted: bool = True,
    ) -> Query:
        """
        Get searches eligible for analytics.

        This includes soft-deleted searches but excludes duplicates
        from guest-to-user conversions.
        """
        query = self.db.query(SearchHistory)

        if not include_deleted:
            query = query.filter(SearchHistory.deleted_at.is_(None))

        if start_date:
            query = query.filter(SearchHistory.first_searched_at >= start_date)

        if end_date:
            query = query.filter(SearchHistory.first_searched_at <= end_date)

        return query.filter(
            or_(SearchHistory.converted_to_user_id.is_(None), SearchHistory.user_id.isnot(None))
        )
