# backend/app/tasks/privacy_tasks.py
"""
Celery tasks for privacy and data retention.

Automated tasks that run on schedule to maintain GDPR compliance
and apply data retention policies.
"""

from datetime import datetime, timezone
import logging
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional, TypeVar, cast

from celery.app.task import Task

from ..database import get_db_session
from ..monitoring.sentry_crons import monitor_if_configured
from ..services.privacy_service import PrivacyService
from ..services.search_history_cleanup_service import SearchHistoryCleanupService
from .celery_app import celery_app

TaskCallable = TypeVar("TaskCallable", bound=Callable[..., Any])


def typed_task(*task_args: Any, **task_kwargs: Any) -> Callable[[TaskCallable], TaskCallable]:
    """Return a typed Celery task decorator for mypy."""

    return cast(Callable[[TaskCallable], TaskCallable], celery_app.task(*task_args, **task_kwargs))


def typed_monitor(slug: str) -> Callable[[TaskCallable], TaskCallable]:
    """Return a typed Sentry monitor decorator for mypy."""

    decorator: Callable[[TaskCallable], TaskCallable] = monitor_if_configured(slug)
    return decorator


logger = logging.getLogger(__name__)


if TYPE_CHECKING:

    class DatabaseTask:
        """Base task type for privacy tasks."""

else:

    class DatabaseTask(Task):
        """Base task type for privacy tasks."""


@typed_task(bind=True, base=DatabaseTask, name="privacy.apply_retention_policies")
@typed_monitor("apply-data-retention-policies")
def apply_retention_policies(self: "DatabaseTask") -> Dict[str, int]:
    """
    Apply data retention policies across all data types.

    This task runs daily to automatically clean up old data
    according to GDPR and business requirements.

    Returns:
        Dictionary with counts of processed records
    """
    logger.info("Starting automated data retention policy application")

    try:
        with get_db_session() as db:
            privacy_service = PrivacyService(db)
            retention_stats = privacy_service.apply_retention_policies()

            logger.info("Data retention policies applied successfully: %s", retention_stats)

            # Also run search history cleanup
            cleanup_service = SearchHistoryCleanupService(db)
            soft_deleted, guest_sessions = cleanup_service.cleanup_all()

            # Combine results
            combined_stats = {
                "search_events_deleted": retention_stats.search_events_deleted,
                "old_bookings_anonymized": retention_stats.old_bookings_anonymized,
                "soft_deleted_searches_removed": soft_deleted,
                "guest_sessions_removed": guest_sessions,
            }

            logger.info("Complete retention cleanup finished: %s", combined_stats)
            return combined_stats

    except Exception as e:
        logger.error("Error applying retention policies: %s", str(e), exc_info=True)
        raise


@typed_task(bind=True, base=DatabaseTask, name="privacy.cleanup_search_history")
@typed_monitor("cleanup-search-history")
def cleanup_search_history(self: "DatabaseTask") -> Dict[str, Any]:
    """
    Clean up old search history records.

    This task runs weekly to remove soft-deleted searches
    and expired guest sessions.

    Returns:
        Dictionary with cleanup statistics
    """
    logger.info("Starting search history cleanup")

    try:
        with get_db_session() as db:
            cleanup_service = SearchHistoryCleanupService(db)
            soft_deleted_count, guest_session_count = cleanup_service.cleanup_all()

            stats = {
                "soft_deleted_searches_removed": soft_deleted_count,
                "guest_sessions_removed": guest_session_count,
                "cleanup_date": datetime.now(timezone.utc).isoformat(),
            }

            logger.info("Search history cleanup completed: %s", stats)
            return stats

    except Exception as e:
        logger.error("Error during search history cleanup: %s", str(e), exc_info=True)
        raise


@typed_task(bind=True, base=DatabaseTask, name="privacy.generate_privacy_report")
@typed_monitor("generate-privacy-report")
def generate_privacy_report(self: "DatabaseTask") -> Dict[str, Any]:
    """
    Generate privacy and data retention statistics report.

    This task runs weekly to provide visibility into
    data retention compliance.

    Returns:
        Dictionary with privacy statistics
    """
    logger.info("Generating privacy compliance report")

    try:
        with get_db_session() as db:
            privacy_service = PrivacyService(db)
            cleanup_service = SearchHistoryCleanupService(db)

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
                "Privacy report generated successfully with %s cleanup metrics", len(cleanup_stats)
            )
            return report

    except Exception as e:
        logger.error("Error generating privacy report: %s", str(e), exc_info=True)
        raise


@typed_task(bind=True, base=DatabaseTask, name="privacy.anonymize_old_bookings")
def anonymize_old_bookings(self: "DatabaseTask", days_old: Optional[int] = None) -> int:
    """
    Anonymize bookings older than specified days.

    This task can be run manually or scheduled to anonymize
    old booking data while preserving business records.

    Args:
        days_old: Number of days old for booking anonymization.
                 If None, uses config setting. Custom values are logged
                 but the system uses the configured retention period.

    Returns:
        Number of bookings anonymized
    """
    from ..core.config import settings

    # Use configured setting - custom days_old is logged for audit but not applied
    # to avoid thread-unsafe global settings mutation in multi-worker environments
    configured_days = getattr(settings, "booking_pii_retention_days", 2555)
    if days_old is not None and days_old != configured_days:
        logger.warning(
            "Custom days_old=%s requested, but using configured retention period of %s days for thread safety. To change retention period, update booking_pii_retention_days in settings.",
            days_old,
            configured_days,
        )
    logger.info("Starting booking anonymization for bookings older than %s days", configured_days)

    try:
        with get_db_session() as db:
            privacy_service = PrivacyService(db)
            retention_stats = privacy_service.apply_retention_policies()
            anonymized_count = int(retention_stats.old_bookings_anonymized)

            logger.info("Anonymized %s old bookings", anonymized_count)
            return anonymized_count

    except Exception as e:
        logger.error("Error anonymizing old bookings: %s", str(e), exc_info=True)
        raise


# Task to process user data export requests
@typed_task(bind=True, base=DatabaseTask, name="privacy.process_data_export_request")
def process_data_export_request(
    self: "DatabaseTask",
    user_id: str,
    request_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Process a user data export request.

    This task can be used to handle large data exports asynchronously.

    Args:
        user_id: ULID of the user requesting data export
        request_id: Optional request ID for tracking

    Returns:
        Dictionary with export results
    """
    logger.info("Processing data export request for user %s (request: %s)", user_id, request_id)

    try:
        with get_db_session() as db:
            privacy_service = PrivacyService(db)
            export_data: Dict[str, Any] = privacy_service.export_user_data(user_id)

            # Add metadata
            export_data["request_id"] = request_id
            export_data["processed_at"] = datetime.now(timezone.utc).isoformat()

            logger.info("Data export completed for user %s", user_id)
            return export_data

    except Exception as e:
        logger.error("Error processing data export for user %s: %s", user_id, str(e), exc_info=True)
        raise


# Task to process user data deletion requests
@typed_task(bind=True, base=DatabaseTask, name="privacy.process_data_deletion_request")
def process_data_deletion_request(
    self: "DatabaseTask",
    user_id: str,
    delete_account: bool = False,
    request_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Process a user data deletion request.

    This task can be used to handle data deletion asynchronously,
    especially useful for large amounts of data.

    Args:
        user_id: ULID of the user requesting data deletion
        delete_account: Whether to delete the entire account
        request_id: Optional request ID for tracking

    Returns:
        Dictionary with deletion results
    """
    logger.info(
        "Processing data deletion request for user %s (delete_account: %s, request: %s)",
        user_id,
        delete_account,
        request_id,
    )

    try:
        with get_db_session() as db:
            privacy_service = PrivacyService(db)

            if delete_account:
                deletion_stats: Dict[str, Any] = privacy_service.delete_user_data(
                    user_id, delete_account=True
                )
            else:
                # Just anonymize
                success = privacy_service.anonymize_user(user_id)
                deletion_stats = {"anonymized": 1 if success else 0}

            result = {
                "user_id": user_id,
                "request_id": request_id,
                "delete_account": delete_account,
                "deletion_stats": deletion_stats,
                "processed_at": datetime.now(timezone.utc).isoformat(),
            }

            logger.info("Data deletion completed for user %s: %s", user_id, deletion_stats)
            return result

    except Exception as e:
        logger.error(
            "Error processing data deletion for user %s: %s", user_id, str(e), exc_info=True
        )
        raise
