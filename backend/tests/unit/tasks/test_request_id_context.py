from __future__ import annotations

from app.tasks.celery_app import _resolve_task_request_id


def test_resolve_task_request_id_from_headers() -> None:
    resolved = _resolve_task_request_id("task-1", {"request_id": "req-1"}, {})
    assert resolved == "req-1"


def test_resolve_task_request_id_from_kwargs() -> None:
    resolved = _resolve_task_request_id("task-2", {}, {"request_id": "req-2"})
    assert resolved == "req-2"


def test_resolve_task_request_id_fallback() -> None:
    resolved = _resolve_task_request_id("task-3", {}, {})
    assert resolved == "task-task-3"
