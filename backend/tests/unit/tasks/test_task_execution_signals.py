from __future__ import annotations

from contextlib import contextmanager
import importlib
from types import SimpleNamespace

from app.models.task_execution import TaskExecution, TaskExecutionStatus

celery_module = importlib.import_module("app.tasks.celery_app")


@contextmanager
def _db_session_ctx(db):
    try:
        yield db
        db.flush()
    except Exception:
        db.rollback()
        raise


def _make_task(
    name: str,
    *,
    task_id: str,
    retries: int = 0,
    request_id: str | None = "req-1",
    queue: str = "payments",
) -> SimpleNamespace:
    headers = {"request_id": request_id} if request_id is not None else {}
    request = SimpleNamespace(
        id=task_id,
        retries=retries,
        headers=headers,
        hostname="celery@worker-1",
        delivery_info={"routing_key": queue},
    )
    return SimpleNamespace(name=name, request=request)


def test_task_prerun_creates_execution_row(unit_db, monkeypatch) -> None:
    monkeypatch.setattr(celery_module, "get_db_session", lambda: _db_session_ctx(unit_db))
    monkeypatch.setattr(celery_module, "get_current_trace_id", lambda: "trace-123")
    task = _make_task("app.tasks.payment.capture", task_id="task-prerun-1")

    celery_module.on_task_prerun(
        sender=task,
        task_id="task-prerun-1",
        task=task,
        args=(),
        kwargs={},
    )

    row = (
        unit_db.query(TaskExecution)
        .filter(TaskExecution.celery_task_id == "task-prerun-1")
        .one()
    )
    assert row.status == TaskExecutionStatus.STARTED.value
    assert row.queue == "payments"
    assert row.worker == "celery@worker-1"
    assert row.trace_id == "trace-123"
    assert row.request_id == "req-1"
    assert row.started_at is not None


def test_task_postrun_success_updates_duration_and_result(unit_db, monkeypatch) -> None:
    monkeypatch.setattr(celery_module, "get_db_session", lambda: _db_session_ctx(unit_db))
    monkeypatch.setattr(celery_module, "get_current_trace_id", lambda: "trace-123")
    task = _make_task("app.tasks.analytics.calculate", task_id="task-success-1")

    celery_module.on_task_prerun(
        sender=task,
        task_id="task-success-1",
        task=task,
        args=(),
        kwargs={},
    )
    task.request.task_execution_started_monotonic = 100.0
    monkeypatch.setattr(celery_module.time, "monotonic", lambda: 100.25)

    celery_module.on_task_postrun(
        sender=task,
        task_id="task-success-1",
        task=task,
        args=(),
        kwargs={},
        retval={"ok": True},
        state="SUCCESS",
    )

    row = (
        unit_db.query(TaskExecution)
        .filter(TaskExecution.celery_task_id == "task-success-1")
        .one()
    )
    assert row.status == TaskExecutionStatus.SUCCESS.value
    assert row.duration_ms == 250
    assert row.result_summary == '{"ok":true}'
    assert row.finished_at is not None


def test_task_failure_records_error_details(unit_db, monkeypatch) -> None:
    monkeypatch.setattr(celery_module, "get_db_session", lambda: _db_session_ctx(unit_db))
    monkeypatch.setattr(celery_module, "get_current_trace_id", lambda: "trace-123")
    task = _make_task("app.tasks.payment.capture", task_id="task-failure-1")
    message = "x" * 2500

    celery_module.on_task_prerun(
        sender=task,
        task_id="task-failure-1",
        task=task,
        args=(),
        kwargs={},
    )
    celery_module.on_task_failure(
        sender=task,
        task_id="task-failure-1",
        exception=RuntimeError(message),
        args=(),
        kwargs={},
        traceback=None,
        einfo=None,
    )
    celery_module.on_task_postrun(
        sender=task,
        task_id="task-failure-1",
        task=task,
        args=(),
        kwargs={},
        retval=None,
        state="FAILURE",
    )

    row = (
        unit_db.query(TaskExecution)
        .filter(TaskExecution.celery_task_id == "task-failure-1")
        .one()
    )
    assert row.status == TaskExecutionStatus.FAILURE.value
    assert row.error_type == "RuntimeError"
    assert row.error_message is not None
    assert len(row.error_message) == 2000


def test_task_retry_reuses_row_and_clears_previous_error(unit_db, monkeypatch) -> None:
    monkeypatch.setattr(celery_module, "get_db_session", lambda: _db_session_ctx(unit_db))
    monkeypatch.setattr(celery_module, "get_current_trace_id", lambda: "trace-123")
    task = _make_task("app.tasks.payment.retryable", task_id="task-retry-1", retries=0)

    celery_module.on_task_prerun(
        sender=task,
        task_id="task-retry-1",
        task=task,
        args=(),
        kwargs={},
    )
    original = (
        unit_db.query(TaskExecution)
        .filter(TaskExecution.celery_task_id == "task-retry-1")
        .one()
    )

    celery_module.on_task_retry(
        sender=task,
        request=task.request,
        reason=ValueError("try again"),
        einfo=None,
    )
    retried = (
        unit_db.query(TaskExecution)
        .filter(TaskExecution.celery_task_id == "task-retry-1")
        .one()
    )
    assert retried.id == original.id
    assert retried.status == TaskExecutionStatus.RETRY.value
    assert retried.error_type == "ValueError"

    task.request.retries = 1
    celery_module.on_task_prerun(
        sender=task,
        task_id="task-retry-1",
        task=task,
        args=(),
        kwargs={},
    )
    restarted = (
        unit_db.query(TaskExecution)
        .filter(TaskExecution.celery_task_id == "task-retry-1")
        .one()
    )
    assert restarted.id == original.id
    assert restarted.status == TaskExecutionStatus.STARTED.value
    assert restarted.retries == 1
    assert restarted.error_type is None
    assert restarted.error_message is None
    assert unit_db.query(TaskExecution).count() == 1


def test_built_in_celery_tasks_are_ignored(unit_db, monkeypatch) -> None:
    monkeypatch.setattr(celery_module, "get_db_session", lambda: _db_session_ctx(unit_db))
    task = _make_task("celery.backend_cleanup", task_id="celery-internal-1")

    celery_module.on_task_prerun(
        sender=task,
        task_id="celery-internal-1",
        task=task,
        args=(),
        kwargs={},
    )

    assert unit_db.query(TaskExecution).count() == 0
