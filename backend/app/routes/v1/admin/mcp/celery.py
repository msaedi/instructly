"""
MCP Admin endpoints for Celery monitoring.

All endpoints require a valid MCP service token with mcp:read scope.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies.database import get_db
from app.dependencies.mcp_auth import require_mcp_scope
from app.principal import Principal
from app.ratelimit.dependency import rate_limit
from app.schemas.celery_admin import (
    MCPCeleryActiveTask,
    MCPCeleryActiveTasksResponse,
    MCPCeleryBeatScheduleResponse,
    MCPCeleryFailedTask,
    MCPCeleryFailedTasksResponse,
    MCPCeleryLastTaskRun,
    MCPCeleryPaymentHealthIssue,
    MCPCeleryPaymentHealthResponse,
    MCPCeleryQueueInfo,
    MCPCeleryQueuesResponse,
    MCPCeleryScheduledTask,
    MCPCeleryTaskHistoryItem,
    MCPCeleryTaskHistoryResponse,
    MCPCeleryWorkerInfo,
    MCPCeleryWorkersResponse,
    MCPCeleryWorkersSummary,
)
from app.services.celery_admin_service import CeleryAdminService

router = APIRouter(tags=["MCP Admin - Celery"])


@router.get(
    "/workers",
    response_model=MCPCeleryWorkersResponse,
    dependencies=[Depends(rate_limit("admin_mcp"))],
)
async def get_workers(
    principal: Principal = Depends(require_mcp_scope("mcp:read")),
    db: Session = Depends(get_db),
) -> MCPCeleryWorkersResponse:
    """
    Get Celery worker status from Flower.

    Returns a list of workers with their status, active tasks,
    and processing statistics.
    """
    service = CeleryAdminService(db)
    result = await service.get_workers()

    workers = [MCPCeleryWorkerInfo(**w) for w in result["workers"]]
    summary = MCPCeleryWorkersSummary(**result["summary"])

    return MCPCeleryWorkersResponse(
        workers=workers,
        summary=summary,
        checked_at=result["checked_at"],
    )


@router.get(
    "/queues",
    response_model=MCPCeleryQueuesResponse,
    dependencies=[Depends(rate_limit("admin_mcp"))],
)
async def get_queues(
    principal: Principal = Depends(require_mcp_scope("mcp:read")),
    db: Session = Depends(get_db),
) -> MCPCeleryQueuesResponse:
    """
    Get Celery queue depths from Flower.

    Returns a list of queues with their current depth.
    """
    service = CeleryAdminService(db)
    result = await service.get_queues()

    queues = [MCPCeleryQueueInfo(**q) for q in result["queues"]]

    return MCPCeleryQueuesResponse(
        queues=queues,
        total_depth=result["total_depth"],
        checked_at=result["checked_at"],
    )


@router.get(
    "/failed",
    response_model=MCPCeleryFailedTasksResponse,
    dependencies=[Depends(rate_limit("admin_mcp"))],
)
async def get_failed_tasks(
    limit: int = Query(default=50, ge=1, le=100),
    principal: Principal = Depends(require_mcp_scope("mcp:read")),
    db: Session = Depends(get_db),
) -> MCPCeleryFailedTasksResponse:
    """
    Get failed Celery tasks from Flower.

    Returns a list of failed tasks with exception and traceback info.
    Traceback is truncated to 1000 characters, args/kwargs to 200 characters.
    """
    service = CeleryAdminService(db)
    result = await service.get_failed_tasks(limit=limit)

    failed_tasks = [MCPCeleryFailedTask(**t) for t in result["failed_tasks"]]

    return MCPCeleryFailedTasksResponse(
        failed_tasks=failed_tasks,
        count=result["count"],
        checked_at=result["checked_at"],
    )


@router.get(
    "/payment-health",
    response_model=MCPCeleryPaymentHealthResponse,
    dependencies=[Depends(rate_limit("admin_mcp"))],
)
async def get_payment_health(
    principal: Principal = Depends(require_mcp_scope("mcp:read")),
    db: Session = Depends(get_db),
) -> MCPCeleryPaymentHealthResponse:
    """
    Get payment pipeline health status.

    Combines Celery task status from Flower with database queries
    for booking payment status to provide a health overview.

    Checks:
    - Pending authorizations (scheduled but not yet processed)
    - Overdue authorizations (within 24h of booking but not authorized)
    - Pending captures (authorized but not yet captured after completion)
    - Failed payments in last 24 hours
    """
    service = CeleryAdminService(db)
    result = await service.get_payment_health()

    issues = [MCPCeleryPaymentHealthIssue(**i) for i in result["issues"]]
    last_task_runs = [MCPCeleryLastTaskRun(**t) for t in result["last_task_runs"]]

    return MCPCeleryPaymentHealthResponse(
        healthy=result["healthy"],
        issues=issues,
        pending_authorizations=result["pending_authorizations"],
        overdue_authorizations=result["overdue_authorizations"],
        pending_captures=result["pending_captures"],
        failed_payments_24h=result["failed_payments_24h"],
        last_task_runs=last_task_runs,
        checked_at=result["checked_at"],
    )


# ==================== TIER 2: Active Tasks, Task History, Beat Schedule ====================


@router.get(
    "/tasks/active",
    response_model=MCPCeleryActiveTasksResponse,
    dependencies=[Depends(rate_limit("admin_mcp"))],
)
async def get_active_tasks(
    principal: Principal = Depends(require_mcp_scope("mcp:read")),
    db: Session = Depends(get_db),
) -> MCPCeleryActiveTasksResponse:
    """
    Get currently running Celery tasks.

    Returns a list of tasks that are currently being executed across all workers.
    """
    service = CeleryAdminService(db)
    result = await service.get_active_tasks()

    tasks = [MCPCeleryActiveTask(**t) for t in result["tasks"]]

    return MCPCeleryActiveTasksResponse(
        tasks=tasks,
        count=result["count"],
        checked_at=result["checked_at"],
    )


@router.get(
    "/tasks/history",
    response_model=MCPCeleryTaskHistoryResponse,
    dependencies=[Depends(rate_limit("admin_mcp"))],
)
async def get_task_history(
    task_name: str | None = Query(default=None, description="Filter by task name (partial match)"),
    state: str
    | None = Query(
        default=None,
        description="Filter by state (SUCCESS, FAILURE, PENDING, STARTED, RETRY)",
    ),
    hours: int = Query(default=1, ge=1, le=24, description="Look back window in hours (max 24)"),
    limit: int = Query(default=100, ge=1, le=500, description="Max results (max 500)"),
    principal: Principal = Depends(require_mcp_scope("mcp:read")),
    db: Session = Depends(get_db),
) -> MCPCeleryTaskHistoryResponse:
    """
    Get recent Celery task history.

    Query recent task executions with optional filters for task name, state,
    and time window. Returns timing information and results/errors.
    """
    service = CeleryAdminService(db)
    result = await service.get_task_history(
        task_name=task_name,
        state=state,
        hours=hours,
        limit=limit,
    )

    tasks = [MCPCeleryTaskHistoryItem(**t) for t in result["tasks"]]

    return MCPCeleryTaskHistoryResponse(
        tasks=tasks,
        count=result["count"],
        filters_applied=result["filters_applied"],
        checked_at=result["checked_at"],
    )


@router.get(
    "/schedule",
    response_model=MCPCeleryBeatScheduleResponse,
    dependencies=[Depends(rate_limit("admin_mcp"))],
)
async def get_beat_schedule(
    principal: Principal = Depends(require_mcp_scope("mcp:read")),
    db: Session = Depends(get_db),
) -> MCPCeleryBeatScheduleResponse:
    """
    Get Celery Beat schedule.

    Returns all configured periodic tasks with human-readable schedule descriptions.
    This reads from the static configuration for accuracy.
    """
    service = CeleryAdminService(db)
    result = await service.get_beat_schedule()

    tasks = [MCPCeleryScheduledTask(**t) for t in result["tasks"]]

    return MCPCeleryBeatScheduleResponse(
        tasks=tasks,
        count=result["count"],
        checked_at=result["checked_at"],
    )
