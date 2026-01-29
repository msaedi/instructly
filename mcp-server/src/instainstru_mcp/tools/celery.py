"""MCP tools for Celery monitoring."""

from __future__ import annotations

from fastmcp import FastMCP

from ..client import InstaInstruClient


def register_tools(mcp: FastMCP, client: InstaInstruClient) -> dict[str, object]:
    async def instainstru_celery_worker_status() -> dict:
        """Get Celery worker status.

        Returns worker information including:
        - Hostname and online/offline status
        - Active tasks count
        - Total processed tasks
        - Concurrency settings
        - Queue assignments
        - Summary of total/online/offline workers
        """
        return await client.get_celery_workers()

    async def instainstru_celery_queue_depth() -> dict:
        """Get Celery queue depths.

        Returns queue information including:
        - Queue name
        - Current depth (number of pending tasks)
        - Total depth across all queues
        """
        return await client.get_celery_queues()

    async def instainstru_celery_failed_tasks(limit: int = 50) -> dict:
        """Get recently failed Celery tasks.

        Args:
            limit: Maximum number of failed tasks to return (1-100, default 50)

        Returns failed task information including:
        - Task ID and name
        - Queue where task failed
        - Failure timestamp
        - Exception message
        - Truncated traceback (max 1000 chars)
        - Truncated args/kwargs (max 200 chars)
        """
        return await client.get_celery_failed_tasks(limit=limit)

    async def instainstru_celery_payment_health() -> dict:
        """Get payment pipeline health status.

        Combines Celery task monitoring with database payment status checks.

        Returns health information including:
        - Overall health status (healthy/unhealthy)
        - List of issues with severity (warning/critical)
        - Count of pending authorizations
        - Count of overdue authorizations (within 24h of booking)
        - Count of pending captures (completed bookings waiting for capture)
        - Count of failed payments in last 24 hours
        - Last run status of payment-related Celery tasks
        """
        return await client.get_celery_payment_health()

    # Tier 2: Active Tasks, Task History, Beat Schedule

    async def instainstru_celery_active_tasks() -> dict:
        """Get currently running Celery tasks across all workers.

        Returns a list of active tasks including:
        - Task ID and name
        - Worker processing the task
        - Start timestamp
        - Truncated args/kwargs (max 200 chars)
        """
        return await client.get_celery_active_tasks()

    async def instainstru_celery_task_history(
        task_name: str | None = None,
        state: str | None = None,
        hours: int = 1,
        limit: int = 100,
    ) -> dict:
        """Get recent Celery task history.

        Filter by task name pattern, state, and time window.

        Args:
            task_name: Filter by task name (partial match)
            state: Filter by state (SUCCESS, FAILURE, PENDING, STARTED, RETRY)
            hours: Look back window in hours (1-24, default 1)
            limit: Maximum results to return (1-500, default 100)

        Returns task history including:
        - Task ID and name
        - State (SUCCESS, FAILURE, etc.)
        - Timing info (received, started, succeeded timestamps)
        - Runtime in seconds
        - Result (truncated) or exception message
        - Retry count
        """
        return await client.get_celery_task_history(
            task_name=task_name,
            state=state,
            hours=hours,
            limit=limit,
        )

    async def instainstru_celery_beat_schedule() -> dict:
        """Get Celery Beat schedule - all periodic tasks and when they run.

        Returns the configured periodic task schedule including:
        - Task name (schedule entry name)
        - Task path (Python task function path)
        - Schedule in human-readable format (e.g., "every 5 minutes", "daily at 03:30 UTC")
        - Enabled status
        """
        return await client.get_celery_beat_schedule()

    mcp.tool()(instainstru_celery_worker_status)
    mcp.tool()(instainstru_celery_queue_depth)
    mcp.tool()(instainstru_celery_failed_tasks)
    mcp.tool()(instainstru_celery_payment_health)
    mcp.tool()(instainstru_celery_active_tasks)
    mcp.tool()(instainstru_celery_task_history)
    mcp.tool()(instainstru_celery_beat_schedule)

    return {
        "instainstru_celery_worker_status": instainstru_celery_worker_status,
        "instainstru_celery_queue_depth": instainstru_celery_queue_depth,
        "instainstru_celery_failed_tasks": instainstru_celery_failed_tasks,
        "instainstru_celery_payment_health": instainstru_celery_payment_health,
        "instainstru_celery_active_tasks": instainstru_celery_active_tasks,
        "instainstru_celery_task_history": instainstru_celery_task_history,
        "instainstru_celery_beat_schedule": instainstru_celery_beat_schedule,
    }
