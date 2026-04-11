"""Guest-to-user conversion helpers for search history."""

from datetime import datetime, timezone
from typing import List, cast

from ...models.search_history import SearchHistory
from .mixin_base import SearchHistoryRepositoryMixinBase


class GuestConversionMixin(SearchHistoryRepositoryMixinBase):
    """Guest session attribution and conversion helpers."""

    def get_guest_searches_for_conversion(self, guest_session_id: str) -> List[SearchHistory]:
        """
        Get all guest searches for conversion to user account, including deleted ones.

        Ordered by first search time, then query to break ties deterministically.
        """
        return cast(
            List[SearchHistory],
            self.db.query(SearchHistory)
            .filter(
                SearchHistory.guest_session_id == guest_session_id,
                SearchHistory.converted_to_user_id.is_(None),
            )
            .order_by(SearchHistory.first_searched_at, SearchHistory.search_query)
            .all(),
        )

    def mark_searches_as_converted(self, guest_session_id: str, user_id: str) -> int:
        """
        Mark guest searches as converted to user account.
        """
        return int(
            self.db.query(SearchHistory)
            .filter(
                SearchHistory.guest_session_id == guest_session_id,
                SearchHistory.converted_to_user_id.is_(None),
            )
            .update(
                {"converted_to_user_id": user_id, "converted_at": datetime.now(timezone.utc)},
                synchronize_session=False,
            )
        )
