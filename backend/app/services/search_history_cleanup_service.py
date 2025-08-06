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
            deleted_count = (
                # repo-pattern-migrate: TODO: Migrate to repository pattern
                self.db.query(SearchHistory)
                # repo-pattern-migrate: TODO: Migrate to repository pattern
                .filter(and_(SearchHistory.deleted_at.isnot(None), SearchHistory.deleted_at < cutoff_date)).delete(
                    synchronize_session=False
                )
            )

            # repo-pattern-migrate: TODO: Migrate to repository pattern
            self.db.commit()

            logger.info(
                f"Permanently deleted {deleted_count} soft-deleted searches "
                f"older than {settings.soft_delete_retention_days} days"
            )

            return deleted_count

        except Exception as e:
            # repo-pattern-migrate: TODO: Migrate to repository pattern
            self.db.rollback()
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
            converted_deleted = (
                # repo-pattern-migrate: TODO: Migrate to repository pattern
                self.db.query(SearchHistory)
                # repo-pattern-migrate: TODO: Migrate to repository pattern
                .filter(
                    and_(
                        SearchHistory.guest_session_id.isnot(None),
                        SearchHistory.converted_to_user_id.isnot(None),
                        SearchHistory.converted_at < cutoff_date,
                    )
                ).delete(synchronize_session=False)
            )

            # Delete old non-converted guest searches
            # These are guest searches that were never converted and are very old
            expired_cutoff = datetime.now(timezone.utc) - timedelta(
                days=settings.guest_session_expiry_days + settings.guest_session_purge_days
            )

            expired_deleted = (
                # repo-pattern-migrate: TODO: Migrate to repository pattern
                self.db.query(SearchHistory)
                # repo-pattern-migrate: TODO: Migrate to repository pattern
                .filter(
                    and_(
                        SearchHistory.guest_session_id.isnot(None),
                        SearchHistory.converted_to_user_id.is_(None),
                        SearchHistory.first_searched_at < expired_cutoff,
                    )
                ).delete(synchronize_session=False)
            )

            total_deleted = converted_deleted + expired_deleted

            # repo-pattern-migrate: TODO: Migrate to repository pattern
            self.db.commit()

            logger.info(
                f"Cleaned up {total_deleted} old guest session records "
                f"({converted_deleted} converted, {expired_deleted} expired)"
            )

            return total_deleted

        except Exception as e:
            # repo-pattern-migrate: TODO: Migrate to repository pattern
            self.db.rollback()
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
        # repo-pattern-migrate: TODO: Migrate to repository pattern
        stats["total_soft_deleted"] = self.db.query(SearchHistory).filter(SearchHistory.deleted_at.isnot(None)).count()

        # Soft-deleted records eligible for cleanup
        if settings.soft_delete_retention_days:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=settings.soft_delete_retention_days)
            stats["soft_deleted_eligible"] = (
                # repo-pattern-migrate: TODO: Migrate to repository pattern
                self.db.query(SearchHistory)
                # repo-pattern-migrate: TODO: Migrate to repository pattern
                .filter(and_(SearchHistory.deleted_at.isnot(None), SearchHistory.deleted_at < cutoff_date))
                # repo-pattern-migrate: TODO: Migrate to repository pattern
                .count()
            )

        # Total guest sessions
        stats["total_guest_sessions"] = (
            # repo-pattern-migrate: TODO: Migrate to repository pattern
            self.db.query(SearchHistory)
            # repo-pattern-migrate: TODO: Migrate to repository pattern
            .filter(SearchHistory.guest_session_id.isnot(None))
            # repo-pattern-migrate: TODO: Migrate to repository pattern
            .count()
        )

        # Converted guest sessions eligible for cleanup
        if settings.guest_session_purge_days:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=settings.guest_session_purge_days)
            stats["converted_guest_eligible"] = (
                # repo-pattern-migrate: TODO: Migrate to repository pattern
                self.db.query(SearchHistory)
                # repo-pattern-migrate: TODO: Migrate to repository pattern
                .filter(
                    and_(
                        SearchHistory.guest_session_id.isnot(None),
                        SearchHistory.converted_to_user_id.isnot(None),
                        SearchHistory.converted_at < cutoff_date,
                    )
                ).count()
            )

        # Expired guest sessions eligible for cleanup
        if settings.guest_session_expiry_days and settings.guest_session_purge_days:
            expired_cutoff = datetime.now(timezone.utc) - timedelta(
                days=settings.guest_session_expiry_days + settings.guest_session_purge_days
            )
            stats["expired_guest_eligible"] = (
                # repo-pattern-migrate: TODO: Migrate to repository pattern
                self.db.query(SearchHistory)
                # repo-pattern-migrate: TODO: Migrate to repository pattern
                .filter(
                    and_(
                        SearchHistory.guest_session_id.isnot(None),
                        SearchHistory.converted_to_user_id.is_(None),
                        SearchHistory.first_searched_at < expired_cutoff,
                    )
                ).count()
            )

        return stats
