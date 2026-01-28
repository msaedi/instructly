"""Schemas for Celery MCP admin responses."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from ._strict_base import StrictModel


class MCPCeleryWorkerInfo(StrictModel):
    """Information about a single Celery worker."""

    hostname: str
    status: str  # "online" or "offline"
    active_tasks: int
    processed_total: int
    concurrency: int
    queues: list[str]


class MCPCeleryWorkersSummary(StrictModel):
    """Summary counts for workers."""

    total_workers: int
    online_workers: int
    offline_workers: int
    total_active_tasks: int


class MCPCeleryWorkersResponse(StrictModel):
    """Response for Celery workers endpoint."""

    workers: list[MCPCeleryWorkerInfo]
    summary: MCPCeleryWorkersSummary
    checked_at: datetime


class MCPCeleryQueueInfo(StrictModel):
    """Information about a single Celery queue."""

    name: str
    depth: int
    consumers: int


class MCPCeleryQueuesResponse(StrictModel):
    """Response for Celery queues endpoint."""

    queues: list[MCPCeleryQueueInfo]
    total_depth: int
    checked_at: datetime


class MCPCeleryFailedTask(StrictModel):
    """Information about a failed Celery task."""

    task_id: str
    task_name: str
    queue: Optional[str] = None
    failed_at: Optional[datetime] = None
    exception: Optional[str] = None
    traceback: Optional[str] = None  # Truncated to 1000 chars
    task_args: Optional[str] = None  # Truncated to 200 chars
    task_kwargs: Optional[str] = None  # Truncated to 200 chars


class MCPCeleryFailedTasksResponse(StrictModel):
    """Response for failed tasks endpoint."""

    failed_tasks: list[MCPCeleryFailedTask]
    count: int
    checked_at: datetime


class MCPCeleryPaymentHealthIssue(StrictModel):
    """A payment health issue."""

    severity: str  # "warning" or "critical"
    message: str
    count: int


class MCPCeleryLastTaskRun(StrictModel):
    """Information about the last run of a payment task."""

    task_name: str
    last_run_at: Optional[datetime] = None
    status: Optional[str] = None


class MCPCeleryPaymentHealthResponse(StrictModel):
    """Response for payment health endpoint."""

    healthy: bool
    issues: list[MCPCeleryPaymentHealthIssue]
    pending_authorizations: int
    overdue_authorizations: int
    pending_captures: int
    failed_payments_24h: int
    last_task_runs: list[MCPCeleryLastTaskRun]
    checked_at: datetime
