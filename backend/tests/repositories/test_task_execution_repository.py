from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.core.ulid_helper import generate_ulid
from app.models.task_execution import TaskExecution, TaskExecutionStatus
from app.repositories.task_execution_repository import TaskExecutionRepository


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def test_create_and_update_on_completion(db) -> None:
    repo = TaskExecutionRepository(db)
    started_at = _now_utc() - timedelta(minutes=5)
    execution = TaskExecution(
        celery_task_id="celery-task-1",
        task_name="app.tasks.example.success",
        status=TaskExecutionStatus.STARTED.value,
        started_at=started_at,
        retries=0,
        queue="analytics",
        worker="worker-1",
    )

    created = repo.create(execution)
    updated = repo.update_on_completion(
        "celery-task-1",
        status=TaskExecutionStatus.SUCCESS.value,
        finished_at=started_at + timedelta(seconds=2),
        duration_ms=2000,
        result_summary='{"ok":true}',
        retries=0,
    )

    assert created.id is not None
    assert updated is not None
    assert updated.status == TaskExecutionStatus.SUCCESS.value
    assert updated.duration_ms == 2000
    assert updated.result_summary == '{"ok":true}'


def test_get_recent_filters_and_orders(db) -> None:
    repo = TaskExecutionRepository(db)
    now = _now_utc()
    task_name_alpha = f"app.tasks.alpha.{generate_ulid()}"
    task_name_beta = f"app.tasks.beta.{generate_ulid()}"
    db.add_all(
        [
            TaskExecution(
                celery_task_id=generate_ulid(),
                task_name=task_name_alpha,
                status=TaskExecutionStatus.FAILURE.value,
                started_at=now - timedelta(minutes=10),
                finished_at=now - timedelta(minutes=9),
                duration_ms=1000,
            ),
            TaskExecution(
                celery_task_id=generate_ulid(),
                task_name=task_name_alpha,
                status=TaskExecutionStatus.FAILURE.value,
                started_at=now - timedelta(minutes=5),
                finished_at=now - timedelta(minutes=4),
                duration_ms=900,
            ),
            TaskExecution(
                celery_task_id=generate_ulid(),
                task_name=task_name_beta,
                status=TaskExecutionStatus.SUCCESS.value,
                started_at=now - timedelta(hours=30),
                finished_at=now - timedelta(hours=30, minutes=-1),
                duration_ms=500,
            ),
        ]
    )
    db.commit()

    executions = repo.get_recent(
        task_name=task_name_alpha,
        status=TaskExecutionStatus.FAILURE.value,
        limit=1,
        since_hours=24,
    )

    assert len(executions) == 1
    assert executions[0].task_name == task_name_alpha
    assert executions[0].duration_ms == 900


def test_get_task_stats_aggregates_counts_and_percentiles(db) -> None:
    repo = TaskExecutionRepository(db)
    now = _now_utc()
    capture_task_name = f"app.tasks.capture.{generate_ulid()}"
    other_task_name = f"app.tasks.other.{generate_ulid()}"
    db.add_all(
        [
            TaskExecution(
                celery_task_id=generate_ulid(),
                task_name=capture_task_name,
                status=TaskExecutionStatus.SUCCESS.value,
                started_at=now - timedelta(minutes=30),
                finished_at=now - timedelta(minutes=29),
                duration_ms=100,
            ),
            TaskExecution(
                celery_task_id=generate_ulid(),
                task_name=capture_task_name,
                status=TaskExecutionStatus.FAILURE.value,
                started_at=now - timedelta(minutes=20),
                finished_at=now - timedelta(minutes=19),
                duration_ms=300,
            ),
            TaskExecution(
                celery_task_id=generate_ulid(),
                task_name=capture_task_name,
                status=TaskExecutionStatus.RETRY.value,
                started_at=now - timedelta(minutes=10),
                finished_at=now - timedelta(minutes=9),
                duration_ms=500,
            ),
            TaskExecution(
                celery_task_id=generate_ulid(),
                task_name=other_task_name,
                status=TaskExecutionStatus.SUCCESS.value,
                started_at=now - timedelta(minutes=15),
                finished_at=now - timedelta(minutes=14),
                duration_ms=50,
            ),
        ]
    )
    db.commit()

    stats = repo.get_task_stats(task_name=capture_task_name, since_hours=24)

    assert len(stats) == 1
    row = stats[0]
    assert row["task_name"] == capture_task_name
    assert row["total_count"] == 3
    assert row["success_count"] == 1
    assert row["failure_count"] == 1
    assert row["success_rate"] == 0.5
    assert row["avg_duration_ms"] == 300.0
    assert row["p50_duration_ms"] == 300.0
    assert row["p95_duration_ms"] == 480.0
    assert row["last_success_at"] is not None
    assert row["last_failure_at"] is not None


def test_cleanup_old_respects_retention_window(db) -> None:
    repo = TaskExecutionRepository(db)
    now = _now_utc()
    old_task_id = generate_ulid()
    new_task_id = generate_ulid()
    db.add_all(
        [
            TaskExecution(
                celery_task_id=old_task_id,
                task_name="app.tasks.cleanup",
                status=TaskExecutionStatus.SUCCESS.value,
                started_at=now - timedelta(days=120),
                finished_at=now - timedelta(days=120, minutes=-1),
                duration_ms=100,
                created_at=now - timedelta(days=120),
            ),
            TaskExecution(
                celery_task_id=new_task_id,
                task_name="app.tasks.cleanup",
                status=TaskExecutionStatus.SUCCESS.value,
                started_at=now - timedelta(days=5),
                finished_at=now - timedelta(days=5, minutes=-1),
                duration_ms=100,
                created_at=now - timedelta(days=5),
            ),
        ]
    )
    db.commit()

    deleted_count = repo.cleanup_old(retention_days=90)
    db.commit()

    assert deleted_count == 1
    assert repo.get_by_celery_task_id(old_task_id) is None
    assert repo.get_by_celery_task_id(new_task_id) is not None
