# backend/app/tasks/search_history_cleanup.py
"""
Celery tasks for search history cleanup.

Provides periodic tasks to clean up old search history data.
"""

from datetime import datetime, timezone
import logging
from typing import Any, Callable, Dict, TypeVar, cast

from celery import shared_task
from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..services.search_history_cleanup_service import SearchHistoryCleanupService

logger = logging.getLogger(__name__)


TaskCallable = TypeVar("TaskCallable", bound=Callable[..., Any])


def typed_shared_task(
    *task_args: Any, **task_kwargs: Any
) -> Callable[[TaskCallable], TaskCallable]:
    return cast(Callable[[TaskCallable], TaskCallable], shared_task(*task_args, **task_kwargs))


@typed_shared_task(
    name="cleanup_search_history",
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 60},
)
def cleanup_search_history(self: Any) -> Dict[str, Any]:
    """
    Periodic task to clean up old search history records.

    This task should be scheduled to run daily (or as configured).
    It removes:
    - Soft-deleted records older than retention period
    - Old guest session records

    Schedule with Celery beat:
    ```python
    'cleanup-search-history': {
        'task': 'cleanup_search_history',
        'schedule': crontab(hour=2, minute=0),  # Run at 2 AM daily
    }
    ```
    """
    logger.info(f"Starting search history cleanup task at {datetime.now(timezone.utc)}")

    db: Session = SessionLocal()
    try:
        cleanup_service = SearchHistoryCleanupService(db)

        # Get statistics before cleanup
        stats_before = cleanup_service.get_cleanup_statistics()
        logger.info(f"Cleanup statistics before: {stats_before}")

        # Run cleanup
        soft_deleted, guest_sessions = cleanup_service.cleanup_all()

        # Get statistics after cleanup
        stats_after = cleanup_service.get_cleanup_statistics()
        logger.info(f"Cleanup statistics after: {stats_after}")

        # Log summary
        logger.info(
            f"Search history cleanup completed. "
            f"Removed {soft_deleted} soft-deleted records and "
            f"{guest_sessions} old guest sessions"
        )

        return {
            "status": "success",
            "soft_deleted_removed": soft_deleted,
            "guest_sessions_removed": guest_sessions,
            "stats_before": stats_before,
            "stats_after": stats_after,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as e:
        logger.error(f"Error in search history cleanup task: {str(e)}")
        raise
    finally:
        db.close()


@typed_shared_task(
    name="search_history_cleanup_dry_run",
    bind=True,
)
def search_history_cleanup_dry_run(self: Any) -> Dict[str, Any]:
    """
    Dry run to check what would be cleaned up without actually deleting.

    Useful for monitoring and debugging.
    """
    logger.info("Running search history cleanup dry run")

    db: Session = SessionLocal()
    try:
        cleanup_service = SearchHistoryCleanupService(db)
        stats = cleanup_service.get_cleanup_statistics()

        logger.info(f"Cleanup dry run statistics: {stats}")

        return {
            "status": "dry_run",
            "statistics": stats,
            "would_delete": {
                "soft_deleted": stats["soft_deleted_eligible"],
                "guest_sessions": stats["converted_guest_eligible"]
                + stats["expired_guest_eligible"],
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as e:
        logger.error(f"Error in cleanup dry run: {str(e)}")
        raise
    finally:
        db.close()
