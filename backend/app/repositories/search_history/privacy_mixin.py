"""Privacy/export helpers for search history data."""

from typing import List, cast

from sqlalchemy import desc, func

from ...models.search_history import SearchHistory
from .mixin_base import SearchHistoryRepositoryMixinBase


class PrivacyMixin(SearchHistoryRepositoryMixinBase):
    """User-scoped search history access for privacy workflows."""

    def get_user_searches(self, user_id: str, exclude_deleted: bool = True) -> List[SearchHistory]:
        """
        Get all searches for a user.
        """
        query = self.db.query(SearchHistory).filter(SearchHistory.user_id == user_id)

        if exclude_deleted:
            query = query.filter(SearchHistory.deleted_at.is_(None))

        return cast(
            List[SearchHistory], query.order_by(desc(SearchHistory.first_searched_at)).all()
        )

    def delete_user_searches(self, user_id: str) -> int:
        """
        Delete all searches for a user (hard delete).
        """
        return int(
            self.db.query(SearchHistory)
            .filter(SearchHistory.user_id == user_id)
            .delete(synchronize_session=False)
        )

    def count_all_searches(self) -> int:
        """
        Count all search history records.
        """
        return int(self.db.query(func.count(SearchHistory.id)).scalar() or 0)
