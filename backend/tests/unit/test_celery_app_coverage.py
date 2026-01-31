from __future__ import annotations

import importlib
import logging
from types import SimpleNamespace
from unittest.mock import Mock

from app.core.config import settings

celery_module = importlib.import_module("app.tasks.celery_app")
from app.tasks.celery_app import (
    BaseTask,
    config_loggers,
    create_celery_app,
    health_check,
    run_availability_retention,
    typed_task,
)


def test_create_celery_app_appends_default_db(monkeypatch):
    monkeypatch.setenv("CELERY_BROKER_URL", "redis://localhost:6379")
    app = create_celery_app()
    assert app.conf.get("broker_url", "").endswith("/0")
    assert app.conf.result_backend == app.conf.get("broker_url")


def test_create_celery_app_preserves_db_suffix(monkeypatch):
    monkeypatch.setenv("CELERY_BROKER_URL", "redis://localhost:6379/5")
    app = create_celery_app()
    assert app.conf.get("broker_url", "").endswith("/5")


def test_create_celery_app_applies_worker_config(monkeypatch):
    monkeypatch.setattr(celery_module, "CELERY_WORKER_CONFIG", {"prefetch_multiplier": 9})
    app = create_celery_app()
    assert app.conf.worker_prefetch_multiplier == 9


def test_config_loggers_sets_beat_level():
    config_loggers()
    beat_logger = logging.getLogger("celery.beat")
    assert beat_logger.level == logging.WARNING


def test_base_task_hooks_do_not_error():
    class DummyTask(BaseTask):
        name = "dummy.task"
        request = SimpleNamespace(retries=2)

    task = DummyTask()
    task.on_retry(Exception("retry"), "task-id", (), {}, None)
    task.on_failure(Exception("fail"), "task-id", (), {}, None)
    task.on_success({"ok": True}, "task-id", (), {})


def test_typed_task_decorator_wraps_function():
    @typed_task(name="test.task")
    def _task() -> str:
        return "ok"

    assert callable(_task)
    assert hasattr(_task, "delay")
    assert _task() == "ok"


def test_health_check_includes_worker():
    payload = health_check()

    assert payload["status"] == "healthy"
    assert payload["worker"] == "unknown"


def test_run_availability_retention_disabled(monkeypatch):
    monkeypatch.setattr(settings, "availability_retention_enabled", False, raising=False)
    payload = run_availability_retention()
    assert payload["inspected_days"] == 0
    assert payload["purged_days"] == 0


def test_run_availability_retention_enabled(monkeypatch):
    monkeypatch.setattr(settings, "availability_retention_enabled", True, raising=False)

    fake_session = Mock()
    monkeypatch.setattr("app.database.SessionLocal", Mock(return_value=fake_session))

    fake_service = Mock()
    fake_service.purge_availability_days.return_value = {"purged_days": 5}
    monkeypatch.setattr("app.services.retention_service.RetentionService", Mock(return_value=fake_service))

    payload = run_availability_retention()

    assert payload == {"purged_days": 5}
    fake_session.close.assert_called_once()


def test_celery_sentry_signal_handlers_call_init(monkeypatch):
    mock_init = Mock()
    monkeypatch.setattr(celery_module, "init_sentry", mock_init)

    celery_module._init_sentry_worker()
    celery_module._init_sentry_beat()

    assert mock_init.call_count == 2
