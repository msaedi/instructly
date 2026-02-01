"""Tests for Celery OpenTelemetry integration."""

from __future__ import annotations

from importlib import import_module, reload
import os
from unittest.mock import MagicMock, patch

from app.monitoring import otel as otel_module

celery_app_module = import_module("app.tasks.celery_app")


def test_init_otel_instruments_celery():
    with patch.dict(os.environ, {"ENABLE_OTEL": "true"}):
        reload(otel_module)

        with patch(
            "opentelemetry.exporter.otlp.proto.http.trace_exporter.OTLPSpanExporter"
        ) as mock_exporter, patch(
            "opentelemetry.sdk.trace.export.BatchSpanProcessor"
        ) as mock_processor, patch(
            "opentelemetry.instrumentation.logging.LoggingInstrumentor"
        ) as mock_logging, patch(
            "opentelemetry.instrumentation.celery.CeleryInstrumentor"
        ) as mock_celery, patch(
            "opentelemetry.sdk.trace.TracerProvider"
        ) as mock_provider:
            mock_logging.return_value.instrument.return_value = None
            mock_celery.return_value.instrument.return_value = None
            mock_processor.return_value = MagicMock()
            mock_provider.return_value = MagicMock()

            assert otel_module.init_otel() is True
            mock_exporter.assert_called_once()
            mock_celery.return_value.instrument.assert_called_once()

        otel_module.shutdown_otel()


def test_worker_init_and_shutdown_hooks(monkeypatch):
    with patch.object(celery_app_module, "init_otel", return_value=True) as mock_init, patch.object(
        celery_app_module, "instrument_additional_libraries"
    ) as mock_instrument:
        celery_app_module._init_otel_worker()

    mock_init.assert_called_once()
    mock_instrument.assert_called_once()

    with patch.object(celery_app_module, "shutdown_otel") as mock_shutdown:
        celery_app_module._shutdown_otel_worker()

    mock_shutdown.assert_called_once()
