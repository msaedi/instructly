"""Repository for persistent Celery task execution history."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, cast

from sqlalchemy import delete, select, text, update
from sqlalchemy.orm import Session

from app.models.task_execution import TaskExecution, TaskExecutionStatus

from .base_repository import BaseRepository

_UNSET = object()


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


class TaskExecutionRepository(BaseRepository[TaskExecution]):
    """Data access for durable Celery execution history."""

    def __init__(self, db: Session) -> None:
        super().__init__(db, TaskExecution)

    def create(
        self,
        task_execution: TaskExecution | None = None,
        **kwargs: Any,
    ) -> TaskExecution:
        """Insert a new execution row."""
        if task_execution is None:
            task_execution = TaskExecution(**kwargs)
        self.db.add(task_execution)
        self.db.flush()
        return task_execution

    def get_by_celery_task_id(self, celery_task_id: str) -> TaskExecution | None:
        """Return the execution row for a Celery task id, if present."""
        return cast(
            TaskExecution | None,
            self.db.query(TaskExecution)
            .filter(TaskExecution.celery_task_id == celery_task_id)
            .one_or_none(),
        )

    def record_start(
        self,
        *,
        celery_task_id: str,
        task_name: str,
        queue: str | None,
        started_at: datetime,
        retries: int,
        worker: str | None,
        trace_id: str | None,
        request_id: str | None,
    ) -> TaskExecution:
        """Create or refresh the row for the latest task attempt."""
        existing = self.get_by_celery_task_id(celery_task_id)
        if existing is not None:
            existing.task_name = task_name
            existing.queue = queue
            existing.status = TaskExecutionStatus.STARTED.value
            existing.started_at = started_at
            existing.finished_at = None
            existing.duration_ms = None
            existing.retries = retries
            existing.error_type = None
            existing.error_message = None
            existing.result_summary = None
            existing.worker = worker
            existing.trace_id = trace_id
            existing.request_id = request_id
            self.db.flush()
            return existing

        return self.create(
            celery_task_id=celery_task_id,
            task_name=task_name,
            queue=queue,
            status=TaskExecutionStatus.STARTED.value,
            started_at=started_at,
            retries=retries,
            worker=worker,
            trace_id=trace_id,
            request_id=request_id,
        )

    def update_on_completion(
        self,
        celery_task_id: str,
        status: str,
        finished_at: datetime,
        duration_ms: int | None,
        error_type: str | None | object = _UNSET,
        error_message: str | None | object = _UNSET,
        result_summary: str | None | object = _UNSET,
        retries: int | None = None,
    ) -> TaskExecution | None:
        """Update a prerun-created row when the task reaches a terminal state."""
        values: dict[str, Any] = {
            "status": status,
            "finished_at": finished_at,
            "duration_ms": duration_ms,
        }
        if retries is not None:
            values["retries"] = retries
        if error_type is not _UNSET:
            values["error_type"] = error_type
        if error_message is not _UNSET:
            values["error_message"] = error_message
        if result_summary is not _UNSET:
            values["result_summary"] = result_summary

        stmt = (
            update(TaskExecution)
            .where(TaskExecution.celery_task_id == celery_task_id)
            .values(**values)
        )
        self.db.execute(stmt)
        self.db.flush()
        return self.get_by_celery_task_id(celery_task_id)

    def get_recent(
        self,
        task_name: str | None = None,
        status: str | None = None,
        limit: int = 50,
        since_hours: int = 24,
    ) -> list[TaskExecution]:
        """Return recent execution rows with optional task and status filters."""
        cutoff = _now_utc() - timedelta(hours=since_hours)
        query = self.db.query(TaskExecution).filter(TaskExecution.started_at >= cutoff)

        if task_name:
            query = query.filter(TaskExecution.task_name == task_name)
        if status:
            query = query.filter(TaskExecution.status == status)

        return cast(
            list[TaskExecution],
            query.order_by(TaskExecution.started_at.desc(), TaskExecution.created_at.desc())
            .limit(limit)
            .all(),
        )

    def get_task_stats(
        self,
        task_name: str | None = None,
        since_hours: int = 24,
    ) -> list[dict[str, Any]]:
        """Return per-task aggregate stats for the requested window."""
        if self.dialect_name == "postgresql":
            return self._get_task_stats_postgres(task_name=task_name, since_hours=since_hours)
        return self._get_task_stats_python(task_name=task_name, since_hours=since_hours)

    def _get_task_stats_postgres(
        self,
        *,
        task_name: str | None,
        since_hours: int,
    ) -> list[dict[str, Any]]:
        cutoff = _now_utc() - timedelta(hours=since_hours)
        params: dict[str, Any] = {
            "cutoff": cutoff,
            "task_name": task_name,
        }
        query = text(
            """
            SELECT
                task_name,
                COUNT(*) AS total_count,
                SUM(CASE WHEN status = 'SUCCESS' THEN 1 ELSE 0 END) AS success_count,
                SUM(CASE WHEN status = 'FAILURE' THEN 1 ELSE 0 END) AS failure_count,
                SUM(CASE WHEN status = 'SUCCESS' THEN 1 ELSE 0 END)::float
                    / NULLIF(
                        SUM(CASE WHEN status IN ('SUCCESS', 'FAILURE') THEN 1 ELSE 0 END),
                        0
                    ) AS success_rate,
                AVG(duration_ms) FILTER (WHERE duration_ms IS NOT NULL) AS avg_duration_ms,
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY duration_ms)
                    FILTER (WHERE duration_ms IS NOT NULL) AS p50_duration_ms,
                PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY duration_ms)
                    FILTER (WHERE duration_ms IS NOT NULL) AS p95_duration_ms,
                MAX(CASE WHEN status = 'SUCCESS' THEN finished_at END) AS last_success_at,
                MAX(CASE WHEN status = 'FAILURE' THEN finished_at END) AS last_failure_at
            FROM task_executions
            WHERE started_at >= :cutoff
                AND (:task_name IS NULL OR task_name = :task_name)
            GROUP BY task_name
            ORDER BY total_count DESC, task_name ASC
            """
        )
        rows = self.db.execute(query, params).all()
        return [
            {
                "task_name": row.task_name,
                "total_count": int(row.total_count or 0),
                "success_count": int(row.success_count or 0),
                "failure_count": int(row.failure_count or 0),
                "success_rate": float(row.success_rate) if row.success_rate is not None else 0.0,
                "avg_duration_ms": (
                    float(row.avg_duration_ms) if row.avg_duration_ms is not None else None
                ),
                "p50_duration_ms": (
                    float(row.p50_duration_ms) if row.p50_duration_ms is not None else None
                ),
                "p95_duration_ms": (
                    float(row.p95_duration_ms) if row.p95_duration_ms is not None else None
                ),
                "last_success_at": row.last_success_at,
                "last_failure_at": row.last_failure_at,
            }
            for row in rows
        ]

    def _get_task_stats_python(
        self,
        *,
        task_name: str | None,
        since_hours: int,
    ) -> list[dict[str, Any]]:
        cutoff = _now_utc() - timedelta(hours=since_hours)
        stmt = select(TaskExecution).where(TaskExecution.started_at >= cutoff)
        if task_name:
            stmt = stmt.where(TaskExecution.task_name == task_name)
        rows = list(self.db.execute(stmt).scalars())

        grouped: dict[str, list[TaskExecution]] = defaultdict(list)
        for row in rows:
            grouped[row.task_name].append(row)

        results: list[dict[str, Any]] = []
        for name, executions in sorted(grouped.items()):
            durations = sorted(
                float(execution.duration_ms)
                for execution in executions
                if execution.duration_ms is not None
            )
            success_count = sum(1 for execution in executions if execution.status == "SUCCESS")
            failure_count = sum(1 for execution in executions if execution.status == "FAILURE")
            denominator = success_count + failure_count

            results.append(
                {
                    "task_name": name,
                    "total_count": len(executions),
                    "success_count": success_count,
                    "failure_count": failure_count,
                    "success_rate": (success_count / denominator) if denominator else 0.0,
                    "avg_duration_ms": (sum(durations) / len(durations) if durations else None),
                    "p50_duration_ms": self._percentile(durations, 0.5),
                    "p95_duration_ms": self._percentile(durations, 0.95),
                    "last_success_at": max(
                        (
                            execution.finished_at
                            for execution in executions
                            if execution.status == "SUCCESS" and execution.finished_at is not None
                        ),
                        default=None,
                    ),
                    "last_failure_at": max(
                        (
                            execution.finished_at
                            for execution in executions
                            if execution.status == "FAILURE" and execution.finished_at is not None
                        ),
                        default=None,
                    ),
                }
            )

        results.sort(key=lambda row: (-row["total_count"], row["task_name"]))
        return results

    @staticmethod
    def _percentile(values: list[float], percentile: float) -> float | None:
        if not values:
            return None
        if len(values) == 1:
            return values[0]

        position = (len(values) - 1) * percentile
        lower_index = int(position)
        upper_index = min(lower_index + 1, len(values) - 1)
        lower_value = values[lower_index]
        upper_value = values[upper_index]
        weight = position - lower_index
        return lower_value + (upper_value - lower_value) * weight

    def cleanup_old(self, retention_days: int = 90) -> int:
        """Delete execution rows older than the configured retention window."""
        cutoff = _now_utc() - timedelta(days=retention_days)
        stmt = delete(TaskExecution).where(TaskExecution.created_at < cutoff)
        result = self.db.execute(stmt)
        self.db.flush()
        return int(result.rowcount or 0)
