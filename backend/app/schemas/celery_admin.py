"""Schemas for Celery MCP admin responses."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

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


# ==================== TIER 2: Active Tasks, Task History, Beat Schedule ====================


class MCPCeleryActiveTask(StrictModel):
    """Information about a currently running Celery task."""

    task_id: str
    task_name: str
    worker: str
    started_at: Optional[datetime] = None
    args: Optional[str] = None  # Truncated/sanitized
    kwargs: Optional[str] = None  # Truncated/sanitized


class MCPCeleryActiveTasksResponse(StrictModel):
    """Response for active tasks endpoint."""

    tasks: list[MCPCeleryActiveTask]
    count: int
    checked_at: datetime


class MCPCeleryTaskHistoryItem(StrictModel):
    """Information about a historical Celery task execution."""

    task_id: str
    task_name: str
    state: str
    received_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    succeeded_at: Optional[datetime] = None  # or failed_at
    runtime_seconds: Optional[float] = None
    result: Optional[str] = None  # Truncated for SUCCESS
    exception: Optional[str] = None  # For FAILURE
    retries: int = 0


class MCPCeleryTaskHistoryResponse(StrictModel):
    """Response for task history endpoint."""

    tasks: list[MCPCeleryTaskHistoryItem]
    count: int
    filters_applied: dict[str, Any]
    checked_at: datetime


class MCPCeleryPersistentTaskExecutionItem(StrictModel):
    """Information about a persistent Celery task execution row."""

    id: str
    celery_task_id: str
    task_name: str
    queue: Optional[str] = None
    status: str  # STARTED, SUCCESS, FAILURE, RETRY
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    retries: int = 0
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    result_summary: Optional[str] = None
    worker: Optional[str] = None
    trace_id: Optional[str] = None
    request_id: Optional[str] = None
    created_at: datetime


class MCPCeleryPersistentTaskExecutionsResponse(StrictModel):
    """Response for persistent task execution history endpoint."""

    executions: list[MCPCeleryPersistentTaskExecutionItem]
    count: int
    filters_applied: dict[str, Any]
    checked_at: datetime


class MCPCeleryTaskStatsItem(StrictModel):
    """Aggregate stats for persistent task execution history."""

    task_name: str
    total_count: int
    success_count: int
    failure_count: int
    success_rate: float
    avg_duration_ms: Optional[float] = None
    p50_duration_ms: Optional[float] = None
    p95_duration_ms: Optional[float] = None
    last_success_at: Optional[datetime] = None
    last_failure_at: Optional[datetime] = None


class MCPCeleryTaskStatsResponse(StrictModel):
    """Response for aggregate task execution stats endpoint."""

    stats: list[MCPCeleryTaskStatsItem]
    count: int
    filters_applied: dict[str, Any]
    checked_at: datetime


class MCPCeleryScheduledTask(StrictModel):
    """Information about a scheduled periodic task."""

    name: str
    task: str
    schedule: str  # Human-readable: "every 5 minutes", "daily at 00:00 UTC"
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None
    enabled: bool = True


class MCPCeleryBeatScheduleResponse(StrictModel):
    """Response for beat schedule endpoint."""

    tasks: list[MCPCeleryScheduledTask]
    count: int
    checked_at: datetime
