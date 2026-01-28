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

    mcp.tool()(instainstru_celery_worker_status)
    mcp.tool()(instainstru_celery_queue_depth)
    mcp.tool()(instainstru_celery_failed_tasks)
    mcp.tool()(instainstru_celery_payment_health)

    return {
        "instainstru_celery_worker_status": instainstru_celery_worker_status,
        "instainstru_celery_queue_depth": instainstru_celery_queue_depth,
        "instainstru_celery_failed_tasks": instainstru_celery_failed_tasks,
        "instainstru_celery_payment_health": instainstru_celery_payment_health,
    }
