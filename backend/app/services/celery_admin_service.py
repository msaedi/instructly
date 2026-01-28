"""Service for Celery monitoring via Flower API."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import logging
from typing import Any, cast

import httpx
from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.booking import Booking, BookingStatus, PaymentStatus

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
        result = (
            self.db.query(func.count(Booking.id))  # repo-pattern-ignore: admin monitoring
            .filter(
                Booking.payment_status == PaymentStatus.SCHEDULED.value,
                Booking.booking_date >= now.date(),
                Booking.status == BookingStatus.CONFIRMED.value,
            )
            .scalar()
        )
        return result or 0

    def _query_overdue_authorizations(self, now: datetime) -> int:
        """Query overdue authorizations count (sync helper for asyncio.to_thread)."""
        cutoff_24h = now + timedelta(hours=24)
        result = (
            self.db.query(func.count(Booking.id))  # repo-pattern-ignore: admin monitoring
            .filter(
                Booking.payment_status == PaymentStatus.SCHEDULED.value,
                Booking.booking_start_utc <= cutoff_24h,
                Booking.booking_start_utc > now,
                Booking.status == BookingStatus.CONFIRMED.value,
            )
            .scalar()
        )
        return result or 0

    def _query_pending_captures(self) -> int:
        """Query pending captures count (sync helper for asyncio.to_thread)."""
        result = (
            self.db.query(func.count(Booking.id))  # repo-pattern-ignore: admin monitoring
            .filter(
                Booking.payment_status == PaymentStatus.AUTHORIZED.value,
                Booking.status == BookingStatus.COMPLETED.value,
            )
            .scalar()
        )
        return result or 0

    def _query_failed_payments_24h(self, now: datetime) -> int:
        """Query failed payments in last 24h count (sync helper for asyncio.to_thread)."""
        cutoff_24h_ago = now - timedelta(hours=24)
        result = (
            self.db.query(func.count(Booking.id))  # repo-pattern-ignore: admin monitoring
            .filter(
                and_(
                    Booking.payment_status.in_(
                        [
                            PaymentStatus.PAYMENT_METHOD_REQUIRED.value,
                            PaymentStatus.MANUAL_REVIEW.value,
                        ]
                    ),
                    Booking.updated_at >= cutoff_24h_ago,
                )
            )
            .scalar()
        )
        return result or 0

    @BaseService.measure_operation("get_payment_health")
    async def get_payment_health(self) -> dict[str, Any]:
        """Get payment pipeline health status.

        Combines Flower task history with DB queries for booking payment status.
        """
        now = datetime.now(timezone.utc)
        issues: list[dict[str, Any]] = []

        # Run all DB queries in parallel using asyncio.to_thread
        # repo-pattern-ignore: MCP admin read-only aggregate queries for monitoring
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
