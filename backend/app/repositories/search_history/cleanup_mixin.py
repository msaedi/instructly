"""Cleanup and retention helpers for search history."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import and_

from ...models.search_history import SearchHistory
from .mixin_base import SearchHistoryRepositoryMixinBase


class CleanupMixin(SearchHistoryRepositoryMixinBase):
    """Retention and cleanup operations for SearchHistory rows."""

    def hard_delete_old_soft_deleted(self, days_old: int) -> int:
        """
        Permanently delete soft-deleted searches older than specified days.
        """
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_old)

        return int(
            self.db.query(SearchHistory)
            .filter(
                and_(SearchHistory.deleted_at.isnot(None), SearchHistory.deleted_at < cutoff_date)
            )
            .delete(synchronize_session=False)
        )

    def count_soft_deleted_total(self) -> int:
        """
        Count all soft-deleted search history records.
        """
        return int(
            self.db.query(SearchHistory).filter(SearchHistory.deleted_at.isnot(None)).count()
        )

    def count_soft_deleted_eligible(self, days_old: int) -> int:
        """
        Count soft-deleted records older than the given number of days.
        """
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_old)
        return int(
            self.db.query(SearchHistory)
            .filter(
                and_(
                    SearchHistory.deleted_at.isnot(None),
                    SearchHistory.deleted_at < cutoff_date,
                )
            )
            .count()
        )

    def count_total_guest_sessions(self) -> int:
        """
        Count all guest session records (any record with a guest_session_id).
        """
        return int(
            self.db.query(SearchHistory).filter(SearchHistory.guest_session_id.isnot(None)).count()
        )

    def count_converted_guest_eligible(self, days_old: int) -> int:
        """
        Count converted guest searches older than the purge threshold.
        """
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_old)
        return int(
            self.db.query(SearchHistory)
            .filter(
                and_(
                    SearchHistory.guest_session_id.isnot(None),
                    SearchHistory.converted_to_user_id.isnot(None),
                    SearchHistory.converted_at < cutoff_date,
                )
            )
            .count()
        )

    def count_expired_guest_eligible(self, days_old: int) -> int:
        """
        Count unconverted guest searches that have passed the expiry+purge window.
        """
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_old)
        return int(
            self.db.query(SearchHistory)
            .filter(
                and_(
                    SearchHistory.guest_session_id.isnot(None),
                    SearchHistory.converted_to_user_id.is_(None),
                    SearchHistory.first_searched_at < cutoff_date,
                )
            )
            .count()
        )

    def delete_converted_guest_searches(self, days_old: int) -> int:
        """
        Delete guest searches that were converted to user more than X days ago.
        """
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_old)

        return int(
            self.db.query(SearchHistory)
            .filter(
                and_(
                    SearchHistory.guest_session_id.isnot(None),
                    SearchHistory.converted_to_user_id.isnot(None),
                    SearchHistory.converted_at < cutoff_date,
                )
            )
            .delete(synchronize_session=False)
        )

    def delete_old_unconverted_guest_searches(self, days_old: int) -> int:
        """
        Hard delete old guest searches that were never converted.
        """
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_old)

        return int(
            self.db.query(SearchHistory)
            .filter(
                and_(
                    SearchHistory.guest_session_id.isnot(None),
                    SearchHistory.converted_to_user_id.is_(None),
                    SearchHistory.first_searched_at < cutoff_date,
                )
            )
            .delete(synchronize_session=False)
        )
