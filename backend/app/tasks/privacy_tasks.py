# backend/app/tasks/privacy_tasks.py
"""
Celery tasks for privacy and data retention.

Automated tasks that run on schedule to maintain GDPR compliance
and apply data retention policies.
"""

from datetime import datetime, timezone
import logging
from typing import Any, Callable, Dict, Optional, Tuple, TypeVar, cast

from celery.app.task import Task
from sqlalchemy.orm import Session

from ..database import get_db
from ..services.privacy_service import PrivacyService
from ..services.search_history_cleanup_service import SearchHistoryCleanupService
from .celery_app import celery_app

TaskCallable = TypeVar("TaskCallable", bound=Callable[..., Any])


def typed_task(*task_args: Any, **task_kwargs: Any) -> Callable[[TaskCallable], TaskCallable]:
    """Return a typed Celery task decorator for mypy."""

    return cast(Callable[[TaskCallable], TaskCallable], celery_app.task(*task_args, **task_kwargs))


logger = logging.getLogger(__name__)


class DatabaseTask(Task):  # type: ignore[type-arg]
    """
    Base task class that provides database session management.
    """

    _db: Optional[Session] = None

    @property
    def db(self) -> Session:
        if self._db is None:
            self._db = cast(Session, next(get_db()))
        return self._db

    def on_failure(
        self,
        exc: BaseException,
        task_id: str,
        args: Tuple[Any, ...],
        kwargs: Dict[str, Any],
        einfo: Any,
    ) -> None:
        """Close database session on task failure."""
        if self._db:
            self._db.close()
            self._db = None

    def on_success(
        self,
        retval: object,
        task_id: str,
        args: Tuple[Any, ...],
        kwargs: Dict[str, Any],
    ) -> None:
        """Close database session on task success."""
        if self._db:
            self._db.close()
            self._db = None


@typed_task(bind=True, base=DatabaseTask, name="privacy.apply_retention_policies")
def apply_retention_policies(self: DatabaseTask) -> Dict[str, int]:
    """
    Apply data retention policies across all data types.

    This task runs daily to automatically clean up old data
    according to GDPR and business requirements.

    Returns:
        Dictionary with counts of processed records
    """
    logger.info("Starting automated data retention policy application")

    try:
        privacy_service = PrivacyService(self.db)
        retention_stats = privacy_service.apply_retention_policies()

        logger.info(f"Data retention policies applied successfully: {retention_stats}")

        # Also run search history cleanup
        cleanup_service = SearchHistoryCleanupService(self.db)
        soft_deleted, guest_sessions = cleanup_service.cleanup_all()

        # Combine results
        combined_stats = {
            **retention_stats,
            "soft_deleted_searches_removed": soft_deleted,
            "guest_sessions_removed": guest_sessions,
        }

        logger.info(f"Complete retention cleanup finished: {combined_stats}")
        return combined_stats

    except Exception as e:
        logger.error(f"Error applying retention policies: {str(e)}", exc_info=True)
        raise


@typed_task(bind=True, base=DatabaseTask, name="privacy.cleanup_search_history")
def cleanup_search_history(self: DatabaseTask) -> Dict[str, Any]:
    """
    Clean up old search history records.

    This task runs weekly to remove soft-deleted searches
    and expired guest sessions.

    Returns:
        Dictionary with cleanup statistics
    """
    logger.info("Starting search history cleanup")

    try:
        cleanup_service = SearchHistoryCleanupService(self.db)
        soft_deleted_count, guest_session_count = cleanup_service.cleanup_all()

        stats = {
            "soft_deleted_searches_removed": soft_deleted_count,
            "guest_sessions_removed": guest_session_count,
            "cleanup_date": datetime.now(timezone.utc).isoformat(),
        }

        logger.info(f"Search history cleanup completed: {stats}")
        return stats

    except Exception as e:
        logger.error(f"Error during search history cleanup: {str(e)}", exc_info=True)
        raise


@typed_task(bind=True, base=DatabaseTask, name="privacy.generate_privacy_report")
def generate_privacy_report(self: DatabaseTask) -> Dict[str, Any]:
    """
    Generate privacy and data retention statistics report.

    This task runs weekly to provide visibility into
    data retention compliance.

    Returns:
        Dictionary with privacy statistics
    """
    logger.info("Generating privacy compliance report")

    try:
        privacy_service = PrivacyService(self.db)
        cleanup_service = SearchHistoryCleanupService(self.db)

        # Get privacy statistics
        privacy_stats = privacy_service.get_privacy_statistics()

        # Get cleanup statistics
        cleanup_stats = cleanup_service.get_cleanup_statistics()

        report = {
            "report_date": datetime.now(timezone.utc).isoformat(),
            "privacy_statistics": privacy_stats,
            "cleanup_statistics": cleanup_stats,
            "compliance_status": {
                "gdpr_data_export_enabled": True,
                "gdpr_data_deletion_enabled": True,
                "automated_retention_active": True,
            },
        }

        logger.info(
            f"Privacy report generated: {len(privacy_stats)} privacy metrics, {len(cleanup_stats)} cleanup metrics"
        )
        return report

    except Exception as e:
        logger.error(f"Error generating privacy report: {str(e)}", exc_info=True)
        raise


@typed_task(bind=True, base=DatabaseTask, name="privacy.anonymize_old_bookings")
def anonymize_old_bookings(self: DatabaseTask, days_old: Optional[int] = None) -> int:
    """
    Anonymize bookings older than specified days.

    This task can be run manually or scheduled to anonymize
    old booking data while preserving business records.

    Args:
        days_old: Number of days old for booking anonymization.
                 If None, uses config setting.

    Returns:
        Number of bookings anonymized
    """
    logger.info(f"Starting booking anonymization for bookings older than {days_old} days")

    try:
        privacy_service = PrivacyService(self.db)

        # If days_old is provided, temporarily override the setting
        if days_old is not None:
            from ..core.config import settings

            original_setting = getattr(settings, "booking_pii_retention_days", 2555)
            settings.booking_pii_retention_days = days_old

            try:
                retention_stats = privacy_service.apply_retention_policies()
                anonymized_count = int(retention_stats.get("old_bookings_anonymized", 0) or 0)
            finally:
                # Restore original setting
                settings.booking_pii_retention_days = original_setting
        else:
            retention_stats = privacy_service.apply_retention_policies()
            anonymized_count = int(retention_stats.get("old_bookings_anonymized", 0) or 0)

        logger.info(f"Anonymized {anonymized_count} old bookings")
        return anonymized_count

    except Exception as e:
        logger.error(f"Error anonymizing old bookings: {str(e)}", exc_info=True)
        raise


# Task to process user data export requests
@typed_task(bind=True, base=DatabaseTask, name="privacy.process_data_export_request")
def process_data_export_request(
    self: DatabaseTask,
    user_id: int,
    request_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Process a user data export request.

    This task can be used to handle large data exports asynchronously.

    Args:
        user_id: ID of the user requesting data export
        request_id: Optional request ID for tracking

    Returns:
        Dictionary with export results
    """
    logger.info(f"Processing data export request for user {user_id} (request: {request_id})")

    try:
        privacy_service = PrivacyService(self.db)
        export_data: Dict[str, Any] = privacy_service.export_user_data(str(user_id))

        # Add metadata
        export_data["request_id"] = request_id
        export_data["processed_at"] = datetime.now(timezone.utc).isoformat()

        logger.info(f"Data export completed for user {user_id}")
        return export_data

    except Exception as e:
        logger.error(f"Error processing data export for user {user_id}: {str(e)}", exc_info=True)
        raise


# Task to process user data deletion requests
@typed_task(bind=True, base=DatabaseTask, name="privacy.process_data_deletion_request")
def process_data_deletion_request(
    self: DatabaseTask,
    user_id: int,
    delete_account: bool = False,
    request_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Process a user data deletion request.

    This task can be used to handle data deletion asynchronously,
    especially useful for large amounts of data.

    Args:
        user_id: ID of the user requesting data deletion
        delete_account: Whether to delete the entire account
        request_id: Optional request ID for tracking

    Returns:
        Dictionary with deletion results
    """
    logger.info(
        f"Processing data deletion request for user {user_id} "
        f"(delete_account: {delete_account}, request: {request_id})"
    )

    try:
        privacy_service = PrivacyService(self.db)

        if delete_account:
            deletion_stats: Dict[str, Any] = privacy_service.delete_user_data(
                str(user_id), delete_account=True
            )
        else:
            # Just anonymize
            success = privacy_service.anonymize_user(str(user_id))
            deletion_stats = {"anonymized": 1 if success else 0}

        result = {
            "user_id": user_id,
            "request_id": request_id,
            "delete_account": delete_account,
            "deletion_stats": deletion_stats,
            "processed_at": datetime.now(timezone.utc).isoformat(),
        }

        logger.info(f"Data deletion completed for user {user_id}: {deletion_stats}")
        return result

    except Exception as e:
        logger.error(f"Error processing data deletion for user {user_id}: {str(e)}", exc_info=True)
        raise
