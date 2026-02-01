"""Tests for the enqueue_task helper."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.tasks import enqueue as enqueue_module


def _setup_task(monkeypatch):
    task = MagicMock()
    task.apply_async.return_value = SimpleNamespace(id="task-123")
    monkeypatch.setattr(
        enqueue_module,
        "current_app",
        SimpleNamespace(tasks={"task.name": task}),
    )
    return task


def test_enqueue_injects_trace_and_request_id(monkeypatch):
    task = _setup_task(monkeypatch)
    monkeypatch.setattr(enqueue_module, "is_otel_enabled", lambda: True)
    monkeypatch.setattr(enqueue_module, "get_request_id", lambda: "req-123")

    def _inject(headers):
        headers["traceparent"] = "00-trace"

    with patch("opentelemetry.propagate.inject", side_effect=_inject) as mock_inject:
        enqueue_module.enqueue_task("task.name", args=(1,), kwargs={"a": 1})

    mock_inject.assert_called_once()
    headers = task.apply_async.call_args.kwargs["headers"]
    assert headers["traceparent"] == "00-trace"
    assert headers["request_id"] == "req-123"


def test_enqueue_preserves_request_id_when_otel_disabled(monkeypatch):
    task = _setup_task(monkeypatch)
    monkeypatch.setattr(enqueue_module, "is_otel_enabled", lambda: False)
    monkeypatch.setattr(enqueue_module, "get_request_id", lambda: "req-999")

    with patch("opentelemetry.propagate.inject") as mock_inject:
        enqueue_module.enqueue_task("task.name", args=(1,))

    mock_inject.assert_not_called()
    headers = task.apply_async.call_args.kwargs["headers"]
    assert headers["request_id"] == "req-999"


def test_enqueue_creates_headers_and_preserves_custom(monkeypatch):
    task = _setup_task(monkeypatch)
    monkeypatch.setattr(enqueue_module, "is_otel_enabled", lambda: False)
    monkeypatch.setattr(enqueue_module, "get_request_id", lambda: None)

    enqueue_module.enqueue_task("task.name", headers={"x-custom": "1"})

    headers = task.apply_async.call_args.kwargs["headers"]
    assert headers == {"x-custom": "1"}
