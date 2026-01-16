from __future__ import annotations

from app.tasks import all_tasks


def test_verify_task_registration_all_present(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        all_tasks.celery_app,
        "tasks",
        {name: object() for name in all_tasks.ALL_TASKS},
        raising=False,
    )

    registered = all_tasks.verify_task_registration()
    assert set(all_tasks.ALL_TASKS).issubset(set(registered))

    output = capsys.readouterr().out
    assert "registered successfully" in output


def test_verify_task_registration_missing(monkeypatch, capsys) -> None:
    monkeypatch.setattr(all_tasks.celery_app, "tasks", {}, raising=False)

    registered = all_tasks.verify_task_registration()
    assert registered == []

    output = capsys.readouterr().out
    assert "Missing tasks" in output
