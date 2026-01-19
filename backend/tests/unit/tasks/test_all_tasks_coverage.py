from __future__ import annotations

import runpy
import sys
from types import SimpleNamespace

from app.tasks import all_tasks


def test_verify_task_registration_reports_missing(monkeypatch, capsys) -> None:
    monkeypatch.setattr(all_tasks, "ALL_TASKS", ["task.a", "task.b"])
    monkeypatch.setattr(all_tasks, "celery_app", SimpleNamespace(tasks={}))

    tasks = all_tasks.verify_task_registration()
    captured = capsys.readouterr()

    assert tasks == []
    assert "Missing tasks" in captured.out


def test_verify_task_registration_success(monkeypatch, capsys) -> None:
    monkeypatch.setattr(all_tasks, "ALL_TASKS", ["task.a", "task.b"])
    monkeypatch.setattr(all_tasks, "celery_app", SimpleNamespace(tasks={"task.a": 1, "task.b": 2}))

    tasks = all_tasks.verify_task_registration()
    captured = capsys.readouterr()

    assert set(tasks) == {"task.a", "task.b"}
    assert "registered successfully" in captured.out


def test_all_tasks_module_main_prints(monkeypatch, capsys) -> None:
    from app.tasks import celery_app as celery_app_instance

    monkeypatch.setattr(
        celery_app_instance,
        "tasks",
        {"task.a": 1, "celery.backend_cleanup": 1},
    )

    sys.modules.pop("app.tasks.all_tasks", None)
    runpy.run_module("app.tasks.all_tasks", run_name="__main__")

    captured = capsys.readouterr()
    assert "Registered Celery tasks" in captured.out
    assert "task.a" in captured.out
    assert "celery.backend_cleanup" not in captured.out
