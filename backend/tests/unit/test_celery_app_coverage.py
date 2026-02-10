from __future__ import annotations

import importlib
import logging
import sys
import types
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


def test_resolve_task_request_id_priority_order():
    assert (
        celery_module._resolve_task_request_id(
            "task-1",
            {"request_id": "hdr-id", "x-request-id": "alt-id"},
            {"request_id": "kw-id"},
        )
        == "hdr-id"
    )
    assert (
        celery_module._resolve_task_request_id(
            "task-2",
            {"x-request-id": "alt-id"},
            {"request_id": "kw-id"},
        )
        == "alt-id"
    )
    assert (
        celery_module._resolve_task_request_id("task-3", None, {"request_id": "kw-id"}) == "kw-id"
    )
    assert celery_module._resolve_task_request_id("task-4", None, None) == "task-task-4"
    assert celery_module._resolve_task_request_id(None, None, None) == "task-unknown"


def test_patch_celery_redis_pubsub_reconnect_paths(monkeypatch):
    fake_module = types.ModuleType("celery.backends.redis")

    class FakeResultConsumer:
        pass

    fake_module.ResultConsumer = FakeResultConsumer
    monkeypatch.setitem(sys.modules, "celery.backends.redis", fake_module)

    celery_module._patch_celery_redis_pubsub()
    assert getattr(FakeResultConsumer, "_instructly_pubsub_patch", False) is True

    conn = SimpleNamespace(register_connect_callback=Mock())
    pubsub = SimpleNamespace(
        subscribe=Mock(),
        connection_pool=SimpleNamespace(get_connection=Mock(return_value=conn)),
        on_connect=Mock(),
        connection=None,
    )
    client = SimpleNamespace(
        connection_pool=SimpleNamespace(reset=Mock()),
        mget=Mock(return_value=[b"meta", None]),
        pubsub=Mock(return_value=pubsub),
    )

    with_subscriptions = SimpleNamespace(
        _pubsub=object(),
        backend=SimpleNamespace(client=client),
        subscribed_to=["booking.events"],
        on_state_change=Mock(),
        _decode_result=lambda meta: {"decoded": meta},
    )
    FakeResultConsumer._reconnect_pubsub(with_subscriptions)
    pubsub.subscribe.assert_called_once_with("booking.events")
    with_subscriptions.on_state_change.assert_called_once()

    no_subscriptions = SimpleNamespace(
        _pubsub=object(),
        backend=SimpleNamespace(client=client),
        subscribed_to=[],
        on_state_change=Mock(),
        _decode_result=lambda meta: {"decoded": meta},
    )
    FakeResultConsumer._reconnect_pubsub(no_subscriptions)
    conn.register_connect_callback.assert_called()


def test_patch_celery_redis_pubsub_returns_when_import_fails(monkeypatch):
    monkeypatch.setitem(sys.modules, "celery.backends.redis", None)
    celery_module._patch_celery_redis_pubsub()


def test_otel_worker_and_beat_init_paths(monkeypatch):
    instrument = Mock()
    monkeypatch.setattr(celery_module, "instrument_additional_libraries", instrument)

    monkeypatch.setattr(celery_module, "init_otel", lambda **_kwargs: False)
    celery_module._init_otel_worker()
    instrument.assert_not_called()

    monkeypatch.setattr(celery_module, "init_otel", lambda **_kwargs: True)
    celery_module._init_otel_beat()
    instrument.assert_called_once()


def test_shutdown_otel_worker_calls_shutdown(monkeypatch):
    shutdown = Mock()
    monkeypatch.setattr(celery_module, "shutdown_otel", shutdown)
    celery_module._shutdown_otel_worker()
    shutdown.assert_called_once()


def test_base_task_request_context_lifecycle(monkeypatch):
    class DummyTask(BaseTask):
        name = "dummy.task"
        request = SimpleNamespace(headers={"request_id": "rid-1"}, retries=0)

    task = DummyTask()

    monkeypatch.setattr(celery_module, "set_request_id", lambda _rid: "token-1")
    task.before_start("task-1", (), {})
    assert task.request.request_id_token == "token-1"

    reset = Mock()
    monkeypatch.setattr(celery_module, "reset_request_id", reset)
    task.after_return("SUCCESS", None, "task-1", (), {}, None)
    reset.assert_called_once_with("token-1")
    assert task.request.request_id_token is None

    # Failure path should swallow reset errors and still clear token.
    task.request.request_id_token = "token-2"
    monkeypatch.setattr(celery_module, "reset_request_id", Mock(side_effect=RuntimeError("boom")))
    task.on_failure(Exception("failure"), "task-1", (), {}, None)
    assert task.request.request_id_token is None
