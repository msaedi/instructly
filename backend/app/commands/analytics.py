#!/usr/bin/env python
# backend/app/commands/analytics.py
"""
Analytics management commands for iNSTAiNSTRU.

This module provides CLI commands for managing analytics calculations,
checking status, and triggering manual runs.

Usage:
    python -m app.commands.analytics run        # Run analytics calculation
    python -m app.commands.analytics status     # Check last run status
    python -m app.commands.analytics help       # Show help
"""

import argparse
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import sys
from typing import Any, Dict

# Add project root to Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from celery.result import AsyncResult
from redis import Redis
from scripts.calculate_service_analytics import AnalyticsCalculator

from app.core.config import settings
from app.database import get_db
from app.repositories.service_catalog_repository import ServiceAnalyticsRepository
from app.tasks.enqueue import enqueue_task

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class AnalyticsCommand:
    """Analytics management command handler."""

    def __init__(self) -> None:
        """Initialize the command handler."""
        self.redis_client = Redis.from_url(settings.redis_url)
        self.last_run_key = "analytics:last_run"

    def run_analytics(self, days_back: int = 90, async_mode: bool = False) -> Dict[str, Any]:
        """
        Run analytics calculation.

        Args:
            days_back: Number of days to analyze
            async_mode: Whether to run asynchronously via Celery

        Returns:
            dict: Execution result
        """
        logger.info(f"Starting analytics calculation for last {days_back} days")

        if async_mode:
            # Run via Celery (async)
            logger.info("Submitting analytics task to Celery queue...")
            result = enqueue_task(
                "app.tasks.analytics.calculate_analytics",
                kwargs={"days_back": days_back},
            )

            # Store task ID for status checking
            self._store_last_run_info(
                {
                    "task_id": result.id,
                    "started_at": datetime.now(timezone.utc).isoformat(),
                    "days_back": days_back,
                    "mode": "async",
                }
            )

            return {
                "status": "submitted",
                "task_id": result.id,
                "message": f"Analytics task submitted. Task ID: {result.id}",
            }
        else:
            # Run directly (sync)
            logger.info("Running analytics calculation directly...")
            start_time = datetime.now(timezone.utc)

            try:
                # Get database session
                db = next(get_db())

                # Create calculator and run
                calculator = AnalyticsCalculator(db)
                services_updated = calculator.calculate_all_analytics(days_back=days_back)
                calculator.update_search_counts()
                report = calculator.generate_report()

                end_time = datetime.now(timezone.utc)
                execution_time = (end_time - start_time).total_seconds()

                # Store execution info
                run_info = {
                    "completed_at": end_time.isoformat(),
                    "started_at": start_time.isoformat(),
                    "execution_time": execution_time,
                    "services_updated": services_updated,
                    "days_back": days_back,
                    "mode": "sync",
                    "status": "success",
                    "report": report,
                }
                self._store_last_run_info(run_info)

                logger.info(f"Analytics calculation completed in {execution_time:.2f}s")
                logger.info(f"Services updated: {services_updated}")

                db.close()

                return run_info

            except Exception as e:
                logger.error(f"Analytics calculation failed: {e}", exc_info=True)

                # Store failure info
                self._store_last_run_info(
                    {
                        "started_at": start_time.isoformat(),
                        "failed_at": datetime.now(timezone.utc).isoformat(),
                        "error": str(e),
                        "days_back": days_back,
                        "mode": "sync",
                        "status": "failed",
                    }
                )

                return {
                    "status": "failed",
                    "error": str(e),
                    "message": "Analytics calculation failed. Check logs for details.",
                }

    def check_status(self) -> Dict[str, Any]:
        """
        Check the status of the last analytics run.

        Returns:
            dict: Status information
        """
        # Get last run info from Redis
        last_run_data = self.redis_client.get(self.last_run_key)

        if not last_run_data:
            return {
                "status": "no_data",
                "message": "No analytics run information found.",
            }

        last_run = json.loads(last_run_data)

        # If it was an async task, check its status
        if last_run.get("mode") == "async" and "task_id" in last_run:
            task_id = last_run["task_id"]
            result: AsyncResult[Any] = AsyncResult(task_id)

            # Use result.state to check task status (pending/running are not attributes)
            task_state = result.state
            if task_state == "PENDING":
                status = "pending"
                message = "Task is waiting to be processed"
            elif task_state == "STARTED":
                status = "running"
                message = "Task is currently running"
            elif result.successful():
                status = "success"
                message = "Task completed successfully"
                # Update last run info with result
                if result.result:
                    last_run.update(result.result)
                    self._store_last_run_info(last_run)
            elif result.failed():
                status = "failed"
                message = f"Task failed: {result.info}"
            else:
                status = task_state
                message = f"Task status: {task_state}"

            last_run["current_status"] = status
            last_run["status_message"] = message

        # Get additional stats from database
        db = next(get_db())
        repo = ServiceAnalyticsRepository(db)

        total_records = repo.count_all()
        latest_update = repo.get_most_recent()

        if latest_update:
            last_run["latest_update"] = latest_update.last_calculated.isoformat()
            last_run["total_analytics_records"] = total_records

        db.close()

        # Format the response
        return self._format_status_response(last_run)

    def _store_last_run_info(self, info: Dict[str, Any]) -> None:
        """Store last run information in Redis."""
        self.redis_client.set(self.last_run_key, json.dumps(info), ex=86400 * 7)  # Keep for 7 days

    def _format_status_response(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Format status data for display."""
        response = {
            "last_run": {
                "started_at": data.get("started_at", "Unknown"),
                "completed_at": data.get("completed_at", "Not completed"),
                "status": data.get("status", data.get("current_status", "Unknown")),
                "mode": data.get("mode", "Unknown"),
            }
        }

        if "execution_time" in data:
            response["last_run"]["execution_time"] = f"{data['execution_time']:.2f} seconds"

        if "services_updated" in data:
            response["last_run"]["services_updated"] = data["services_updated"]

        if "error" in data:
            response["last_run"]["error"] = data["error"]

        if "task_id" in data:
            response["last_run"]["task_id"] = data["task_id"]

        if "status_message" in data:
            response["last_run"]["status_message"] = data["status_message"]

        if "report" in data:
            response["report"] = data["report"]

        if "total_analytics_records" in data:
            response["database_stats"] = {
                "total_records": data["total_analytics_records"],
                "latest_update": data.get("latest_update", "Unknown"),
            }

        return response


def main() -> None:
    """Main entry point for the analytics command."""
    parser = argparse.ArgumentParser(
        description="iNSTAiNSTRU Analytics Management",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m app.commands.analytics run                    # Run analytics (sync)
  python -m app.commands.analytics run --async            # Run analytics (via Celery)
  python -m app.commands.analytics run --days 30          # Analyze last 30 days
  python -m app.commands.analytics status                 # Check last run status
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Run command
    run_parser = subparsers.add_parser("run", help="Run analytics calculation")
    run_parser.add_argument(
        "--days", type=int, default=90, help="Number of days to analyze (default: 90)"
    )
    run_parser.add_argument(
        "--async", action="store_true", dest="async_mode", help="Run asynchronously via Celery"
    )

    # Status command
    _status_parser = subparsers.add_parser("status", help="Check last run status")

    # Parse arguments
    args = parser.parse_args()

    # Initialize command handler
    cmd = AnalyticsCommand()

    # Execute command
    if args.command == "run":
        print(f"\n🔄 Running analytics for last {args.days} days...")
        result = cmd.run_analytics(days_back=args.days, async_mode=args.async_mode)

        if result["status"] == "submitted":
            print(f"✅ {result['message']}")
            print("   Check status with: python -m app.commands.analytics status")
        elif result["status"] == "success":
            print("✅ Analytics completed successfully!")
            print(f"   Execution time: {result['execution_time']:.2f}s")
            print(f"   Services updated: {result['services_updated']}")
            if "report" in result:
                print("\n📊 Report Summary:")
                print(json.dumps(result["report"], indent=2))
        else:
            print(f"❌ Analytics failed: {result.get('error', 'Unknown error')}")
            sys.exit(1)

    elif args.command == "status":
        print("\n📊 Analytics Status")
        print("=" * 50)

        status = cmd.check_status()

        if "last_run" not in status:
            print("No analytics run information available.")
        else:
            # Display last run info
            last_run = status["last_run"]
            print("Last Run:")
            print(f"  Started: {last_run['started_at']}")
            print(f"  Status: {last_run['status']}")

            if last_run.get("completed_at") != "Not completed":
                print(f"  Completed: {last_run['completed_at']}")

            if "execution_time" in last_run:
                print(f"  Duration: {last_run['execution_time']}")

            if "services_updated" in last_run:
                print(f"  Services Updated: {last_run['services_updated']}")

            if "task_id" in last_run:
                print(f"  Task ID: {last_run['task_id']}")

            if "status_message" in last_run:
                print(f"  Message: {last_run['status_message']}")

            if "error" in last_run:
                print(f"  ❌ Error: {last_run['error']}")

            # Display database stats
            if "database_stats" in status:
                print("\nDatabase Statistics:")
                stats = status["database_stats"]
                print(f"  Total Analytics Records: {stats['total_records']}")
                print(f"  Latest Update: {stats['latest_update']}")

            # Display report if available
            if "report" in status:
                print("\nLast Report Summary:")
                print(json.dumps(status["report"], indent=2))

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
