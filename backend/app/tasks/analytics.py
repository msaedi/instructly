# backend/app/tasks/analytics.py
"""
Analytics calculation Celery tasks for InstaInstru.

This module contains tasks for calculating service analytics, generating reports,
and updating metrics asynchronously.
"""

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.database import get_db
from app.tasks.celery_app import BaseTask, celery_app
from scripts.calculate_service_analytics import AnalyticsCalculator

logger = logging.getLogger(__name__)


@celery_app.task(
    base=BaseTask,
    name="app.tasks.analytics.calculate_analytics",
    bind=True,
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=600,
)
def calculate_analytics(self, days_back: int = 90) -> Dict[str, Any]:
    """
    Calculate service analytics for all instructors.

    This task wraps the AnalyticsCalculator to run analytics calculations
    asynchronously with proper error handling and logging.

    Args:
        days_back: Number of days to look back for analytics (default: 90)

    Returns:
        dict: Execution summary with metrics
    """
    start_time = time.time()
    task_id = self.request.id

    logger.info(
        f"Starting analytics calculation task {task_id}",
        extra={
            "task_id": task_id,
            "days_back": days_back,
            "start_time": datetime.now(timezone.utc).isoformat(),
        },
    )

    db: Optional[Session] = None
    try:
        # Get database session
        db = next(get_db())

        # Create analytics calculator
        calculator = AnalyticsCalculator(db)

        # Calculate analytics for all services
        logger.info("Calculating analytics for all services...")
        services_updated = calculator.calculate_all_analytics(days_back=days_back)

        # Update search counts
        logger.info("Updating search count metrics...")
        calculator.update_search_counts()

        # Generate summary report
        report = calculator.generate_report()

        # Calculate execution time
        execution_time = time.time() - start_time

        # Log completion
        logger.info(
            f"Analytics calculation completed successfully",
            extra={
                "task_id": task_id,
                "execution_time": execution_time,
                "services_updated": services_updated,
                "report": report,
            },
        )

        # Return execution summary
        return {
            "status": "success",
            "task_id": task_id,
            "execution_time": execution_time,
            "services_updated": services_updated,
            "report": report,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as exc:
        execution_time = time.time() - start_time

        logger.error(
            f"Analytics calculation failed after {execution_time:.2f}s",
            exc_info=True,
            extra={
                "task_id": task_id,
                "execution_time": execution_time,
                "error": str(exc),
            },
        )

        # Retry with exponential backoff
        raise self.retry(exc=exc, countdown=60 * (2**self.request.retries), max_retries=3)

    finally:
        # Ensure database session is closed
        if db:
            db.close()


@celery_app.task(
    base=BaseTask,
    name="app.tasks.analytics.generate_daily_report",
    bind=True,
    max_retries=2,
)
def generate_daily_report(self) -> Dict[str, Any]:
    """
    Generate daily analytics report.

    This task generates a comprehensive daily report of platform metrics
    and can be scheduled to run after analytics calculation.

    Returns:
        dict: Report summary
    """
    start_time = time.time()
    task_id = self.request.id

    logger.info(f"Generating daily analytics report {task_id}")

    db: Optional[Session] = None
    try:
        db = next(get_db())

        # Create calculator for report generation
        calculator = AnalyticsCalculator(db)  # Daily report

        # Generate report
        report = calculator.generate_report()

        execution_time = time.time() - start_time

        logger.info(
            f"Daily report generated successfully",
            extra={
                "task_id": task_id,
                "execution_time": execution_time,
                "report_date": datetime.now(timezone.utc).date().isoformat(),
            },
        )

        return {
            "status": "success",
            "task_id": task_id,
            "execution_time": execution_time,
            "report": report,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as exc:
        logger.error(f"Failed to generate daily report: {exc}", exc_info=True)
        raise self.retry(exc=exc, countdown=300)  # Retry in 5 minutes

    finally:
        if db:
            db.close()


@celery_app.task(
    base=BaseTask,
    name="app.tasks.analytics.update_service_metrics",
    bind=True,
)
def update_service_metrics(self, service_id: int) -> Dict[str, Any]:
    """
    Update analytics for a specific service.

    This task can be triggered when a service needs immediate metric updates,
    such as after a booking completion or instructor update.

    Args:
        service_id: ID of the service to update

    Returns:
        dict: Update summary
    """
    logger.info(f"Updating metrics for service {service_id}")

    db: Optional[Session] = None
    try:
        db = next(get_db())

        calculator = AnalyticsCalculator(db)

        # Use repository to get the service
        from app.repositories.factory import RepositoryFactory

        catalog_repo = RepositoryFactory.create_service_catalog_repository(db)
        service = catalog_repo.get_by_id(service_id)

        if not service:
            logger.warning(f"Service {service_id} not found")
            return {
                "status": "error",
                "message": f"Service {service_id} not found",
            }

        # Calculate analytics for this specific service
        booking_stats = calculator.calculate_booking_stats(service_id)
        instructor_stats = calculator.calculate_instructor_stats(service_id)

        # Update analytics using repository
        analytics_repo = RepositoryFactory.create_service_analytics_repository(db)
        analytics_repo.get_or_create(service_id)

        update_data = {
            "booking_count_7d": booking_stats.get("count_7d", 0),
            "booking_count_30d": booking_stats.get("count_30d", 0),
            "avg_price_booked": booking_stats.get("avg_price"),
            "active_instructors": instructor_stats["active_instructors"],
            "total_weekly_hours": instructor_stats["total_weekly_hours"],
            "last_calculated": datetime.now(timezone.utc),
        }

        updated = analytics_repo.update(service_id, **update_data)

        logger.info(f"Metrics updated for service {service_id}")

        return {
            "status": "success",
            "service_id": service_id,
            "booking_stats": booking_stats,
            "instructor_stats": instructor_stats,
            "updated": updated is not None,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as exc:
        logger.error(f"Failed to update service {service_id} metrics: {exc}")
        raise

    finally:
        if db:
            db.close()


# Optional: Task execution tracking
@celery_app.task(
    name="app.tasks.analytics.record_task_execution",
    bind=True,
)
def record_task_execution(
    self,
    task_name: str,
    status: str,
    execution_time: float,
    result: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
) -> None:
    """
    Record task execution in database for tracking.

    This is an optional task that can be called after other tasks complete
    to maintain an execution history.

    Args:
        task_name: Name of the executed task
        status: Execution status (success/failure)
        execution_time: Time taken to execute
        result: Task result summary
        error: Error message if failed
    """
    db: Optional[Session] = None
    try:
        db = next(get_db())

        # This would require a TaskExecution model to be created
        # For now, just log it
        logger.info(
            f"Task execution recorded",
            extra={
                "task_name": task_name,
                "status": status,
                "execution_time": execution_time,
                "result": result,
                "error": error,
                "recorded_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    except Exception as exc:
        logger.error(f"Failed to record task execution: {exc}")

    finally:
        if db:
            db.close()
