# backend/app/services/search_history_cleanup_service.py
"""
Search History Cleanup Service.

Handles periodic cleanup of old soft-deleted records and expired guest sessions
based on configuration settings.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Tuple

from sqlalchemy import and_
from sqlalchemy.orm import Session

from ..core.config import settings
from ..models.search_history import SearchHistory
from ..repositories.search_history_repository import SearchHistoryRepository
from .base import BaseService

logger = logging.getLogger(__name__)


class SearchHistoryCleanupService(BaseService):
    """
    Service for cleaning up old search history records.

    Handles:
    - Permanent deletion of old soft-deleted records
    - Cleanup of expired guest sessions
    - Purging of old converted guest searches
    """

    def __init__(self, db: Session):
        """Initialize the cleanup service."""
        super().__init__(db)
        self.repository = SearchHistoryRepository(db)

    @BaseService.measure_operation("cleanup_soft_deleted_searches")
    def cleanup_soft_deleted_searches(self) -> int:
        """
        Permanently delete soft-deleted searches older than retention period.

        Uses settings.soft_delete_retention_days to determine cutoff.

        Returns:
            Number of records permanently deleted
        """
        if not settings.soft_delete_retention_days:
            logger.info("Soft delete retention is disabled (0 days), skipping cleanup")
            return 0

        cutoff_date = datetime.now(timezone.utc) - timedelta(days=settings.soft_delete_retention_days)

        try:
            # Find and delete old soft-deleted records
            deleted_count = self.repository.hard_delete_old_soft_deleted(days_old=settings.soft_delete_retention_days)

            with self.transaction():
                pass  # Transaction commits automatically

            logger.info(
                f"Permanently deleted {deleted_count} soft-deleted searches "
                f"older than {settings.soft_delete_retention_days} days"
            )

            return deleted_count

        except Exception as e:
            logger.error(f"Error cleaning up soft-deleted searches: {str(e)}")
            raise

    @BaseService.measure_operation("cleanup_old_guest_sessions")
    def cleanup_old_guest_sessions(self) -> int:
        """
        Clean up old guest session searches based on purge settings.

        Uses settings.guest_session_purge_days to determine cutoff.
        This permanently deletes guest searches that are:
        - Older than the purge period
        - Already converted to user searches

        Returns:
            Number of guest session records deleted
        """
        if not settings.guest_session_purge_days:
            logger.info("Guest session purge is disabled (0 days), skipping cleanup")
            return 0

        cutoff_date = datetime.now(timezone.utc) - timedelta(days=settings.guest_session_purge_days)

        try:
            # Delete old converted guest searches
            converted_deleted = self.repository.delete_converted_guest_searches(
                days_old=settings.guest_session_purge_days
            )

            # Delete old non-converted guest searches
            # These are guest searches that were never converted and are very old
            expired_days = settings.guest_session_expiry_days + settings.guest_session_purge_days
            expired_deleted = self.repository.delete_old_unconverted_guest_searches(days_old=expired_days)

            total_deleted = converted_deleted + expired_deleted

            with self.transaction():
                pass  # Transaction commits automatically

            logger.info(
                f"Cleaned up {total_deleted} old guest session records "
                f"({converted_deleted} converted, {expired_deleted} expired)"
            )

            return total_deleted

        except Exception as e:
            logger.error(f"Error cleaning up guest sessions: {str(e)}")
            raise

    @BaseService.measure_operation("cleanup_all")
    def cleanup_all(self) -> Tuple[int, int]:
        """
        Run all cleanup operations.

        Returns:
            Tuple of (soft_deleted_count, guest_session_count)
        """
        logger.info("Starting search history cleanup")

        # Run cleanup operations
        soft_deleted_count = self.cleanup_soft_deleted_searches()
        guest_session_count = self.cleanup_old_guest_sessions()

        logger.info(
            f"Search history cleanup complete. "
            f"Removed {soft_deleted_count} soft-deleted records and "
            f"{guest_session_count} old guest sessions"
        )

        return soft_deleted_count, guest_session_count

    @BaseService.measure_operation("get_cleanup_statistics")
    def get_cleanup_statistics(self) -> dict:
        """
        Get statistics about records eligible for cleanup.

        Returns:
            Dictionary with cleanup statistics
        """
        stats = {
            "soft_deleted_eligible": 0,
            "converted_guest_eligible": 0,
            "expired_guest_eligible": 0,
            "total_soft_deleted": 0,
            "total_guest_sessions": 0,
        }

        # Total soft-deleted records
        # repo-pattern-ignore: Statistics query for reporting - count only deleted
        stats["total_soft_deleted"] = self.db.query(SearchHistory).filter(SearchHistory.deleted_at.isnot(None)).count()

        # Soft-deleted records eligible for cleanup
        if settings.soft_delete_retention_days:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=settings.soft_delete_retention_days)
            # This is complex enough to keep as direct query for now
            stats["soft_deleted_eligible"] = (
                # repo-pattern-ignore: Statistics query for reporting
                self.db.query(SearchHistory)
                # repo-pattern-ignore: Statistics query for reporting
                .filter(and_(SearchHistory.deleted_at.isnot(None), SearchHistory.deleted_at < cutoff_date))
                # repo-pattern-ignore: Statistics query for reporting
                .count()
            )

        # Total guest sessions
        stats["total_guest_sessions"] = (
            # repo-pattern-ignore: Statistics query for reporting
            self.db.query(SearchHistory)
            # repo-pattern-ignore: Statistics query for reporting
            .filter(SearchHistory.guest_session_id.isnot(None))
            # repo-pattern-ignore: Statistics query for reporting
            .count()
        )

        # Converted guest sessions eligible for cleanup
        if settings.guest_session_purge_days:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=settings.guest_session_purge_days)
            stats["converted_guest_eligible"] = (
                # repo-pattern-ignore: Statistics query for reporting
                self.db.query(SearchHistory)
                # repo-pattern-ignore: Statistics query for reporting
                .filter(
                    and_(
                        SearchHistory.guest_session_id.isnot(None),
                        SearchHistory.converted_to_user_id.isnot(None),
                        SearchHistory.converted_at < cutoff_date,
                    )
                    # repo-pattern-ignore: Statistics query for reporting
                ).count()
            )

        # Expired guest sessions eligible for cleanup
        if settings.guest_session_expiry_days and settings.guest_session_purge_days:
            expired_cutoff = datetime.now(timezone.utc) - timedelta(
                days=settings.guest_session_expiry_days + settings.guest_session_purge_days
            )
            stats["expired_guest_eligible"] = (
                # repo-pattern-ignore: Statistics query for reporting
                self.db.query(SearchHistory)
                # repo-pattern-ignore: Statistics query for reporting
                .filter(
                    and_(
                        SearchHistory.guest_session_id.isnot(None),
                        SearchHistory.converted_to_user_id.is_(None),
                        SearchHistory.first_searched_at < expired_cutoff,
                    )
                    # repo-pattern-ignore: Statistics query for reporting
                ).count()
            )

        return stats
