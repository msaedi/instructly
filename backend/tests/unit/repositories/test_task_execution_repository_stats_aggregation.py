from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.core.ulid_helper import generate_ulid
from app.models.task_execution import TaskExecution, TaskExecutionStatus
from app.repositories.task_execution_repository import TaskExecutionRepository


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _make_execution(
    *,
    task_name: str,
    status: str,
    started_at: datetime,
    finished_at: datetime | None = None,
    duration_ms: int | None = None,
    created_at: datetime | None = None,
) -> TaskExecution:
    return TaskExecution(
        celery_task_id=generate_ulid(),
        task_name=task_name,
        status=status,
        started_at=started_at,
        finished_at=finished_at,
        duration_ms=duration_ms,
        created_at=created_at or started_at,
    )


def test_record_start_inserts_and_reuses_existing_row(unit_db) -> None:
    repo = TaskExecutionRepository(unit_db)
    first_started_at = _now_utc() - timedelta(minutes=10)
    second_started_at = first_started_at + timedelta(minutes=5)
    celery_task_id = generate_ulid()

    created = repo.record_start(
        celery_task_id=celery_task_id,
        task_name="app.tasks.media.generate",
        queue="media",
        started_at=first_started_at,
        retries=0,
        worker="worker-a",
        trace_id="trace-a",
        request_id="req-a",
    )

    assert created.id is not None
    assert created.status == TaskExecutionStatus.STARTED.value
    assert created.task_name == "app.tasks.media.generate"
    assert created.queue == "media"
    assert created.worker == "worker-a"
    assert created.trace_id == "trace-a"
    assert created.request_id == "req-a"
    assert created.started_at == first_started_at

    updated = repo.update_on_completion(
        celery_task_id,
        status=TaskExecutionStatus.FAILURE.value,
        finished_at=first_started_at + timedelta(seconds=30),
        duration_ms=30_000,
        error_type="RuntimeError",
        error_message="first attempt failed",
        result_summary='{"ok":false}',
        retries=1,
    )

    assert updated is not None
    assert updated.status == TaskExecutionStatus.FAILURE.value
    assert _as_utc(updated.finished_at) == first_started_at + timedelta(seconds=30)
    assert updated.duration_ms == 30_000
    assert updated.error_type == "RuntimeError"
    assert updated.error_message == "first attempt failed"
    assert updated.result_summary == '{"ok":false}'
    assert updated.retries == 1

    restarted = repo.record_start(
        celery_task_id=celery_task_id,
        task_name="app.tasks.media.generate.retry",
        queue="retry-queue",
        started_at=second_started_at,
        retries=2,
        worker="worker-b",
        trace_id="trace-b",
        request_id="req-b",
    )

    assert restarted.id == created.id
    assert restarted.status == TaskExecutionStatus.STARTED.value
    assert restarted.task_name == "app.tasks.media.generate.retry"
    assert restarted.queue == "retry-queue"
    assert restarted.worker == "worker-b"
    assert restarted.trace_id == "trace-b"
    assert restarted.request_id == "req-b"
    assert restarted.started_at == second_started_at
    assert restarted.finished_at is None
    assert restarted.duration_ms is None
    assert restarted.retries == 2
    assert restarted.error_type is None
    assert restarted.error_message is None
    assert restarted.result_summary is None
    assert unit_db.query(TaskExecution).count() == 1


def test_update_on_completion_preserves_omitted_optional_fields(unit_db) -> None:
    repo = TaskExecutionRepository(unit_db)
    started_at = _now_utc() - timedelta(minutes=5)
    execution = TaskExecution(
        celery_task_id=generate_ulid(),
        task_name="app.tasks.sync.catalog",
        status=TaskExecutionStatus.STARTED.value,
        started_at=started_at,
        retries=4,
        error_type="TimeoutError",
        error_message="original failure",
        result_summary='{"state":"stale"}',
    )
    unit_db.add(execution)
    unit_db.flush()

    updated = repo.update_on_completion(
        execution.celery_task_id,
        status=TaskExecutionStatus.SUCCESS.value,
        finished_at=started_at + timedelta(seconds=15),
        duration_ms=15_000,
    )

    assert updated is not None
    assert updated.status == TaskExecutionStatus.SUCCESS.value
    assert _as_utc(updated.finished_at) == started_at + timedelta(seconds=15)
    assert updated.duration_ms == 15_000
    assert updated.retries == 4
    assert updated.error_type == "TimeoutError"
    assert updated.error_message == "original failure"
    assert updated.result_summary == '{"state":"stale"}'


def test_get_recent_orders_by_started_at_then_created_at_without_filters(unit_db) -> None:
    repo = TaskExecutionRepository(unit_db)
    shared_started_at = _now_utc() - timedelta(minutes=30)
    older_created_at = shared_started_at + timedelta(seconds=1)
    middle_created_at = shared_started_at + timedelta(seconds=2)
    newest_created_at = shared_started_at + timedelta(seconds=3)

    older = _make_execution(
        task_name="app.tasks.cleanup",
        status=TaskExecutionStatus.SUCCESS.value,
        started_at=shared_started_at,
        finished_at=shared_started_at + timedelta(seconds=10),
        duration_ms=10_000,
        created_at=older_created_at,
    )
    newest = _make_execution(
        task_name="app.tasks.cleanup",
        status=TaskExecutionStatus.FAILURE.value,
        started_at=shared_started_at,
        finished_at=shared_started_at + timedelta(seconds=20),
        duration_ms=20_000,
        created_at=newest_created_at,
    )
    middle = _make_execution(
        task_name="app.tasks.cleanup",
        status=TaskExecutionStatus.RETRY.value,
        started_at=shared_started_at,
        finished_at=shared_started_at + timedelta(seconds=15),
        duration_ms=15_000,
        created_at=middle_created_at,
    )
    unit_db.add_all([older, newest, middle])
    unit_db.flush()

    executions = repo.get_recent(limit=10, since_hours=24)

    assert [execution.id for execution in executions] == [newest.id, middle.id, older.id]


def test_get_task_stats_returns_empty_list_when_no_rows_match(unit_db) -> None:
    repo = TaskExecutionRepository(unit_db)

    assert repo.get_task_stats(task_name=None, since_hours=24) == []


def test_get_task_stats_python_aggregates_mixed_rows(unit_db) -> None:
    repo = TaskExecutionRepository(unit_db)
    now = _now_utc()
    task_name = f"app.tasks.aggregate.{generate_ulid()}"
    last_success_at = now - timedelta(minutes=9)
    last_failure_at = now - timedelta(minutes=6)
    unit_db.add_all(
        [
            _make_execution(
                task_name=task_name,
                status=TaskExecutionStatus.SUCCESS.value,
                started_at=now - timedelta(minutes=10),
                finished_at=last_success_at,
                duration_ms=100,
            ),
            _make_execution(
                task_name=task_name,
                status=TaskExecutionStatus.FAILURE.value,
                started_at=now - timedelta(minutes=7),
                finished_at=last_failure_at,
                duration_ms=None,
            ),
            _make_execution(
                task_name=task_name,
                status=TaskExecutionStatus.SUCCESS.value,
                started_at=now - timedelta(minutes=5),
                finished_at=None,
                duration_ms=300,
            ),
            _make_execution(
                task_name=task_name,
                status=TaskExecutionStatus.SUCCESS.value,
                started_at=now - timedelta(days=3),
                finished_at=now - timedelta(days=3, seconds=-30),
                duration_ms=999,
            ),
        ]
    )
    unit_db.flush()

    stats = repo.get_task_stats(task_name=task_name, since_hours=24)

    assert len(stats) == 1
    row = stats[0]
    assert row["task_name"] == task_name
    assert row["total_count"] == 3
    assert row["success_count"] == 2
    assert row["failure_count"] == 1
    assert row["success_rate"] == pytest.approx(2 / 3)
    assert row["avg_duration_ms"] == 200.0
    assert row["p50_duration_ms"] == 200.0
    assert row["p95_duration_ms"] == 290.0
    assert _as_utc(row["last_success_at"]) == last_success_at
    assert _as_utc(row["last_failure_at"]) == last_failure_at


def test_get_task_stats_orders_equal_count_groups_by_task_name(unit_db) -> None:
    repo = TaskExecutionRepository(unit_db)
    now = _now_utc()
    alpha_name = f"app.tasks.alpha.{generate_ulid()}"
    beta_name = f"app.tasks.beta.{generate_ulid()}"
    unit_db.add_all(
        [
            _make_execution(
                task_name=beta_name,
                status=TaskExecutionStatus.SUCCESS.value,
                started_at=now - timedelta(minutes=4),
                finished_at=now - timedelta(minutes=3),
                duration_ms=100,
            ),
            _make_execution(
                task_name=beta_name,
                status=TaskExecutionStatus.FAILURE.value,
                started_at=now - timedelta(minutes=3),
                finished_at=now - timedelta(minutes=2),
                duration_ms=200,
            ),
            _make_execution(
                task_name=alpha_name,
                status=TaskExecutionStatus.SUCCESS.value,
                started_at=now - timedelta(minutes=2),
                finished_at=now - timedelta(minutes=1),
                duration_ms=150,
            ),
            _make_execution(
                task_name=alpha_name,
                status=TaskExecutionStatus.FAILURE.value,
                started_at=now - timedelta(minutes=1),
                finished_at=now,
                duration_ms=250,
            ),
        ]
    )
    unit_db.flush()

    stats = repo.get_task_stats(task_name=None, since_hours=24)

    assert [row["task_name"] for row in stats] == [alpha_name, beta_name]
    assert [row["total_count"] for row in stats] == [2, 2]


@pytest.mark.parametrize(
    ("values", "percentile", "expected"),
    [
        ([], 0.95, None),
        ([42.0], 0.5, 42.0),
        ([42.0], 0.95, 42.0),
        ([10.0, 20.0], 0.95, 19.5),
        ([10.0, 20.0, 30.0], 0.0, 10.0),
        ([10.0, 20.0, 30.0], 1.0, 30.0),
    ],
)
def test_percentile_supported_inputs(values, percentile, expected) -> None:
    assert TaskExecutionRepository._percentile(values, percentile) == expected
