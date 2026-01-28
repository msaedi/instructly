"""Service for Celery monitoring via Flower API."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import logging
from typing import Any, cast

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.repositories.admin_ops_repository import AdminOpsRepository

from .base import BaseService

logger = logging.getLogger(__name__)


def _secret_value(value: object | None) -> str:
    """Extract value from SecretStr or return string."""
    if value is None:
        return ""
    getter = getattr(value, "get_secret_value", None)
    if callable(getter):
        return str(getter())
    return str(value)


class CeleryAdminService(BaseService):
    """Service for Celery monitoring via Flower API and payment health queries."""

    FLOWER_TIMEOUT = 10.0
    MAX_FAILED_TASKS_LIMIT = 100
    TRACEBACK_TRUNCATE_LENGTH = 1000
    ARGS_TRUNCATE_LENGTH = 200

    def __init__(self, db: Session) -> None:
        """Initialize the service."""
        super().__init__(db)
        self.repository = AdminOpsRepository(db)

    async def _call_flower(
        self,
        endpoint: str,
        method: str = "GET",
        params: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any] | None:
        """Make a request to the Flower API.

        Returns None if the request fails (graceful degradation).
        """
        flower_url = settings.flower_url.rstrip("/")
        url = f"{flower_url}{endpoint}"
        timeout_value = timeout or self.FLOWER_TIMEOUT

        # Build auth if configured
        auth = None
        flower_user = settings.flower_user
        flower_password = _secret_value(settings.flower_password)
        if flower_user and flower_password:
            auth = httpx.BasicAuth(flower_user, flower_password)

        try:
            async with httpx.AsyncClient(timeout=timeout_value) as client:
                response = await client.request(
                    method,
                    url,
                    params=params,
                    auth=auth,
                )
                response.raise_for_status()
                return cast(dict[str, Any], response.json())
        except httpx.TimeoutException:
            logger.warning("Flower API timeout: %s", url)
            return None
        except httpx.HTTPError as exc:
            logger.warning("Flower API error: %s - %s", url, exc)
            return None
        except Exception as exc:
            logger.exception("Unexpected error calling Flower API: %s", exc)
            return None

    @BaseService.measure_operation("get_workers")
    async def get_workers(self) -> dict[str, Any]:
        """Get Celery worker status from Flower.

        Returns worker list with status, active tasks, and summary.
        """
        now = datetime.now(timezone.utc)
        data = await self._call_flower("/api/workers")

        workers = []
        summary = {
            "total_workers": 0,
            "online_workers": 0,
            "offline_workers": 0,
            "total_active_tasks": 0,
        }

        if data:
            for hostname, info in data.items():
                status_bool = info.get("status", False)
                status = "online" if status_bool else "offline"
                active_tasks_list = info.get("active", [])
                active_count = len(active_tasks_list) if isinstance(active_tasks_list, list) else 0

                # Get processed total from stats
                stats = info.get("stats", {})
                total_stats = stats.get("total", {})
                processed_total = (
                    total_stats.get("total", 0) if isinstance(total_stats, dict) else 0
                )

                concurrency = info.get("concurrency", 0)

                # Get queue names
                active_queues = info.get("active_queues", [])
                queue_names = []
                if isinstance(active_queues, list):
                    for q in active_queues:
                        if isinstance(q, dict) and "name" in q:
                            queue_names.append(q["name"])

                workers.append(
                    {
                        "hostname": hostname,
                        "status": status,
                        "active_tasks": active_count,
                        "processed_total": processed_total,
                        "concurrency": concurrency,
                        "queues": queue_names,
                    }
                )

                summary["total_workers"] += 1
                if status == "online":
                    summary["online_workers"] += 1
                else:
                    summary["offline_workers"] += 1
                summary["total_active_tasks"] += active_count

        return {
            "workers": workers,
            "summary": summary,
            "checked_at": now,
        }

    @BaseService.measure_operation("get_queues")
    async def get_queues(self) -> dict[str, Any]:
        """Get Celery queue depths from Flower.

        Returns queue list with depth and total depth.
        """
        now = datetime.now(timezone.utc)
        data = await self._call_flower("/api/queues/length")

        queues = []
        total_depth = 0

        if data:
            for queue_name, depth in data.items():
                queue_depth = depth if isinstance(depth, int) else 0
                queues.append(
                    {
                        "name": queue_name,
                        "depth": queue_depth,
                        "consumers": 0,  # Flower queue/length doesn't return consumer count
                    }
                )
                total_depth += queue_depth

        return {
            "queues": queues,
            "total_depth": total_depth,
            "checked_at": now,
        }

    @BaseService.measure_operation("get_failed_tasks")
    async def get_failed_tasks(self, limit: int = 50) -> dict[str, Any]:
        """Get failed Celery tasks from Flower.

        Args:
            limit: Maximum number of failed tasks to return (capped at 100).

        Returns failed tasks with exception/traceback info.
        """
        now = datetime.now(timezone.utc)
        # Cap the limit
        effective_limit = min(limit, self.MAX_FAILED_TASKS_LIMIT)

        data = await self._call_flower(
            "/api/tasks",
            params={"state": "FAILURE", "limit": effective_limit},
        )

        failed_tasks = []

        if data:
            for task_id, task_info in data.items():
                if not isinstance(task_info, dict):
                    continue

                # Parse failed_at from received timestamp
                received = task_info.get("received")
                failed_at = None
                if received:
                    try:
                        failed_at = datetime.fromtimestamp(received, tz=timezone.utc)
                    except (TypeError, ValueError):
                        pass

                # Truncate traceback and args
                traceback = task_info.get("traceback")
                if traceback and len(traceback) > self.TRACEBACK_TRUNCATE_LENGTH:
                    traceback = traceback[: self.TRACEBACK_TRUNCATE_LENGTH] + "..."

                args_str = str(task_info.get("args", ""))
                if len(args_str) > self.ARGS_TRUNCATE_LENGTH:
                    args_str = args_str[: self.ARGS_TRUNCATE_LENGTH] + "..."

                kwargs_str = str(task_info.get("kwargs", ""))
                if len(kwargs_str) > self.ARGS_TRUNCATE_LENGTH:
                    kwargs_str = kwargs_str[: self.ARGS_TRUNCATE_LENGTH] + "..."

                failed_tasks.append(
                    {
                        "task_id": task_id,
                        "task_name": task_info.get("name", "unknown"),
                        "queue": task_info.get("queue"),
                        "failed_at": failed_at,
                        "exception": task_info.get("exception"),
                        "traceback": traceback,
                        "task_args": args_str if args_str != "()" else None,
                        "task_kwargs": kwargs_str if kwargs_str != "{}" else None,
                    }
                )

        return {
            "failed_tasks": failed_tasks,
            "count": len(failed_tasks),
            "checked_at": now,
        }

    def _query_pending_authorizations(self, now: datetime) -> int:
        """Query pending authorizations count (sync helper for asyncio.to_thread)."""
        return self.repository.count_pending_authorizations(from_date=now.date())

    def _query_overdue_authorizations(self, now: datetime) -> int:
        """Query overdue authorizations count (sync helper for asyncio.to_thread)."""
        cutoff_24h = now + timedelta(hours=24)
        return self.repository.count_overdue_authorizations(
            cutoff_time=cutoff_24h, current_time=now
        )

    def _query_pending_captures(self) -> int:
        """Query pending captures count (sync helper for asyncio.to_thread)."""
        from app.models.booking import BookingStatus, PaymentStatus

        return self.repository.count_bookings_by_payment_and_status(
            payment_status=PaymentStatus.AUTHORIZED.value,
            booking_status=BookingStatus.COMPLETED.value,
        )

    def _query_failed_payments_24h(self, now: datetime) -> int:
        """Query failed payments in last 24h count (sync helper for asyncio.to_thread)."""
        cutoff_24h_ago = now - timedelta(hours=24)
        return self.repository.count_failed_payments(updated_since=cutoff_24h_ago)

    @BaseService.measure_operation("get_payment_health")
    async def get_payment_health(self) -> dict[str, Any]:
        """Get payment pipeline health status.

        Combines Flower task history with DB queries for booking payment status.
        """
        now = datetime.now(timezone.utc)
        issues: list[dict[str, Any]] = []

        # Run all DB queries in parallel using asyncio.to_thread
        (
            pending_auth_count,
            overdue_auth_count,
            pending_capture_count,
            failed_24h_count,
        ) = await asyncio.gather(
            asyncio.to_thread(self._query_pending_authorizations, now),
            asyncio.to_thread(self._query_overdue_authorizations, now),
            asyncio.to_thread(self._query_pending_captures),
            asyncio.to_thread(self._query_failed_payments_24h, now),
        )

        # Build issues list
        if overdue_auth_count > 0:
            issues.append(
                {
                    "severity": "critical",
                    "message": "Bookings within 24 hours without authorization",
                    "count": overdue_auth_count,
                }
            )

        if pending_capture_count > 10:
            issues.append(
                {
                    "severity": "warning",
                    "message": "Completed bookings pending capture",
                    "count": pending_capture_count,
                }
            )

        if failed_24h_count > 0:
            issues.append(
                {
                    "severity": "warning",
                    "message": "Failed payments in last 24 hours",
                    "count": failed_24h_count,
                }
            )

        # Check Flower for payment task history
        last_task_runs: list[dict[str, Any]] = []
        payment_task_names = [
            "app.tasks.payment_tasks.authorize_scheduled_payments",
            "app.tasks.payment_tasks.capture_completed_bookings",
            "app.tasks.payment_tasks.retry_failed_payments",
        ]

        for task_name in payment_task_names:
            short_name = task_name.split(".")[-1]
            # Try to get recent task runs from Flower
            task_data = await self._call_flower(
                "/api/tasks",
                params={"name": task_name, "limit": 1},
            )

            last_run_at = None
            status = None
            if task_data:
                # Get the most recent task
                for _task_id, task_info in task_data.items():
                    if isinstance(task_info, dict):
                        received = task_info.get("received")
                        if received:
                            try:
                                last_run_at = datetime.fromtimestamp(received, tz=timezone.utc)
                            except (TypeError, ValueError):
                                pass
                        status = task_info.get("state", "unknown")
                        break

            last_task_runs.append(
                {
                    "task_name": short_name,
                    "last_run_at": last_run_at,
                    "status": status,
                }
            )

        healthy = len(issues) == 0

        return {
            "healthy": healthy,
            "issues": issues,
            "pending_authorizations": pending_auth_count,
            "overdue_authorizations": overdue_auth_count,
            "pending_captures": pending_capture_count,
            "failed_payments_24h": failed_24h_count,
            "last_task_runs": last_task_runs,
            "checked_at": now,
        }

    # ==================== TIER 2: Active Tasks, Task History, Beat Schedule ====================

    MAX_TASK_HISTORY_HOURS = 24
    MAX_TASK_HISTORY_LIMIT = 500
    RESULT_TRUNCATE_LENGTH = 500

    @BaseService.measure_operation("get_active_tasks")
    async def get_active_tasks(self) -> dict[str, Any]:
        """Get currently running Celery tasks from Flower.

        Returns a list of active tasks across all workers.
        """
        now = datetime.now(timezone.utc)
        data = await self._call_flower("/api/tasks", params={"state": "STARTED"})

        tasks = []
        if data:
            for task_id, task_info in data.items():
                if not isinstance(task_info, dict):
                    continue

                # Parse started_at timestamp
                started = task_info.get("started")
                started_at = None
                if started:
                    try:
                        started_at = datetime.fromtimestamp(started, tz=timezone.utc)
                    except (TypeError, ValueError):
                        pass

                # Truncate args/kwargs
                args_str = str(task_info.get("args", ""))
                if len(args_str) > self.ARGS_TRUNCATE_LENGTH:
                    args_str = args_str[: self.ARGS_TRUNCATE_LENGTH] + "..."

                kwargs_str = str(task_info.get("kwargs", ""))
                if len(kwargs_str) > self.ARGS_TRUNCATE_LENGTH:
                    kwargs_str = kwargs_str[: self.ARGS_TRUNCATE_LENGTH] + "..."

                tasks.append(
                    {
                        "task_id": task_id,
                        "task_name": task_info.get("name", "unknown"),
                        "worker": task_info.get("worker", "unknown"),
                        "started_at": started_at,
                        "args": args_str if args_str and args_str != "()" else None,
                        "kwargs": kwargs_str if kwargs_str and kwargs_str != "{}" else None,
                    }
                )

        return {
            "tasks": tasks,
            "count": len(tasks),
            "checked_at": now,
        }

    @BaseService.measure_operation("get_task_history")
    async def get_task_history(
        self,
        task_name: str | None = None,
        state: str | None = None,
        hours: int = 1,
        limit: int = 100,
    ) -> dict[str, Any]:
        """Get recent Celery task history from Flower.

        Args:
            task_name: Filter by task name (partial match via Flower).
            state: Filter by state (SUCCESS, FAILURE, PENDING, STARTED, RETRY).
            hours: Look back window (max 24 hours).
            limit: Maximum number of results (max 500).

        Returns task history with timing and result info.
        """
        now = datetime.now(timezone.utc)

        # Cap parameters
        effective_hours = min(hours, self.MAX_TASK_HISTORY_HOURS)
        effective_limit = min(limit, self.MAX_TASK_HISTORY_LIMIT)

        # Build query params
        params: dict[str, Any] = {"limit": effective_limit}
        if task_name:
            params["name"] = task_name
        if state:
            params["state"] = state

        data = await self._call_flower("/api/tasks", params=params)

        tasks = []
        cutoff_time = now - timedelta(hours=effective_hours)

        if data:
            for task_id, task_info in data.items():
                if not isinstance(task_info, dict):
                    continue

                # Parse timestamps
                received_at = None
                received = task_info.get("received")
                if received:
                    try:
                        received_at = datetime.fromtimestamp(received, tz=timezone.utc)
                    except (TypeError, ValueError):
                        pass

                # Skip tasks outside time window
                if received_at and received_at < cutoff_time:
                    continue

                started_at = None
                started = task_info.get("started")
                if started:
                    try:
                        started_at = datetime.fromtimestamp(started, tz=timezone.utc)
                    except (TypeError, ValueError):
                        pass

                succeeded_at = None
                succeeded = task_info.get("succeeded")
                if succeeded:
                    try:
                        succeeded_at = datetime.fromtimestamp(succeeded, tz=timezone.utc)
                    except (TypeError, ValueError):
                        pass

                # Calculate runtime if we have start and end times
                runtime_seconds = None
                if started_at and succeeded_at:
                    runtime_seconds = (succeeded_at - started_at).total_seconds()

                # Truncate result
                result = task_info.get("result")
                if result:
                    result_str = str(result)
                    if len(result_str) > self.RESULT_TRUNCATE_LENGTH:
                        result = result_str[: self.RESULT_TRUNCATE_LENGTH] + "..."
                    else:
                        result = result_str

                tasks.append(
                    {
                        "task_id": task_id,
                        "task_name": task_info.get("name", "unknown"),
                        "state": task_info.get("state", "unknown"),
                        "received_at": received_at,
                        "started_at": started_at,
                        "succeeded_at": succeeded_at,
                        "runtime_seconds": runtime_seconds,
                        "result": result,
                        "exception": task_info.get("exception"),
                        "retries": task_info.get("retries", 0),
                    }
                )

        # Record filters applied
        filters_applied = {
            "task_name": task_name,
            "state": state,
            "hours": effective_hours,
            "limit": effective_limit,
        }

        return {
            "tasks": tasks,
            "count": len(tasks),
            "filters_applied": filters_applied,
            "checked_at": now,
        }

    @BaseService.measure_operation("get_beat_schedule")
    async def get_beat_schedule(self) -> dict[str, Any]:
        """Get Celery Beat schedule from static configuration.

        Returns the configured periodic tasks with human-readable schedules.
        This reads from the static configuration rather than Flower for accuracy.
        """
        from app.tasks.beat_schedule import get_beat_schedule as get_schedule_config

        now = datetime.now(timezone.utc)
        tasks = []

        schedule_config = get_schedule_config()

        for name, config in schedule_config.items():
            task = config.get("task", "")
            schedule = config.get("schedule")

            # Convert schedule to human-readable string
            schedule_str = self._format_schedule(schedule)

            tasks.append(
                {
                    "name": name,
                    "task": task,
                    "schedule": schedule_str,
                    "last_run": None,  # Would need Flower/DB tracking to know this
                    "next_run": None,  # Would need scheduler state to calculate
                    "enabled": True,
                }
            )

        return {
            "tasks": tasks,
            "count": len(tasks),
            "checked_at": now,
        }

    @staticmethod
    def _format_schedule(schedule: object) -> str:
        """Convert a Celery schedule to human-readable format."""
        from celery.schedules import crontab

        if isinstance(schedule, timedelta):
            total_seconds = int(schedule.total_seconds())
            if total_seconds < 60:
                return f"every {total_seconds} seconds"
            elif total_seconds < 3600:
                minutes = total_seconds // 60
                return f"every {minutes} minute{'s' if minutes != 1 else ''}"
            else:
                hours = total_seconds // 3600
                return f"every {hours} hour{'s' if hours != 1 else ''}"
        elif isinstance(schedule, crontab):
            # Build human-readable crontab description
            # Use getattr for crontab internals (they're undocumented but stable)
            minute = str(getattr(schedule, "_orig_minute", "*"))
            hour = str(getattr(schedule, "_orig_hour", "*"))
            dom = str(getattr(schedule, "_orig_day_of_month", "*"))
            month = str(getattr(schedule, "_orig_month_of_year", "*"))
            dow = str(getattr(schedule, "_orig_day_of_week", "*"))

            # Common patterns
            if minute.startswith("*/"):
                interval = minute[2:]
                return f"every {interval} minutes"
            elif hour.startswith("*/"):
                interval = hour[2:]
                return f"every {interval} hours"

            # Specific times
            if minute != "*" and hour != "*":
                time_str = f"{hour.zfill(2)}:{minute.zfill(2)} UTC"
                if dow != "*":
                    dow_names = {
                        "0": "Sunday",
                        "1": "Monday",
                        "2": "Tuesday",
                        "3": "Wednesday",
                        "4": "Thursday",
                        "5": "Friday",
                        "6": "Saturday",
                    }
                    dow_name = dow_names.get(dow, f"day {dow}")
                    return f"{dow_name} at {time_str}"
                elif dom != "*":
                    return f"day {dom} of month at {time_str}"
                else:
                    return f"daily at {time_str}"

            # Hourly at specific minute
            if minute != "*" and hour == "*":
                return f"hourly at :{minute.zfill(2)}"

            # Fallback: raw crontab representation
            return f"cron({minute} {hour} {dom} {month} {dow})"

        return str(schedule)
