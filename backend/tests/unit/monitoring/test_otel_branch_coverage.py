"""Additional branch coverage tests for app.monitoring.otel."""

from __future__ import annotations

from importlib import reload
import os
from unittest.mock import MagicMock, patch

from fastapi import FastAPI


def _reload_otel():
    from app.monitoring import otel

    reload(otel)
    return otel


def test_parse_otlp_headers_malformed_entries(caplog):
    otel = _reload_otel()

    headers = otel._parse_otlp_headers(" ,missing_equals, =empty_key,Good=Value%20Here")

    assert headers == {"Good": "Value Here"}
    assert "Malformed OTLP header entry" in caplog.text


def test_init_otel_handles_celery_instrumentation_error():
    with patch.dict(
        os.environ,
        {
            "ENABLE_OTEL": "true",
            "AXIOM_API_TOKEN": "token",
            "AXIOM_TRACES_DATASET": "dataset",
        },
    ):
        otel = _reload_otel()

        with patch(
            "opentelemetry.exporter.otlp.proto.http.trace_exporter.OTLPSpanExporter"
        ) as mock_exporter, patch(
            "opentelemetry.sdk.trace.export.BatchSpanProcessor"
        ) as mock_processor, patch(
            "opentelemetry.instrumentation.logging.LoggingInstrumentor"
        ) as mock_logging, patch(
            "opentelemetry.sdk.trace.TracerProvider"
        ) as mock_provider, patch(
            "opentelemetry.instrumentation.celery.CeleryInstrumentor"
        ) as mock_celery:
            mock_logging.return_value.instrument.return_value = None
            mock_processor.return_value = MagicMock()
            mock_provider.return_value = MagicMock()
            mock_celery.return_value.instrument.side_effect = RuntimeError("celery-boom")

            assert otel.init_otel() is True
            mock_exporter.assert_called_once()

        otel.shutdown_otel()


def test_instrument_fastapi_returns_false_on_instrumentation_error():
    with patch.dict(os.environ, {"ENABLE_OTEL": "true"}):
        otel = _reload_otel()
        app = FastAPI()

        with patch(
            "opentelemetry.instrumentation.fastapi.FastAPIInstrumentor.instrument_app",
            side_effect=RuntimeError("boom"),
        ):
            assert otel.instrument_fastapi(app) is False


def test_instrument_sqlalchemy_early_return_when_already_instrumented():
    otel = _reload_otel()
    otel._sqlalchemy_instrumented = True

    otel._instrument_sqlalchemy(object())

    assert otel._sqlalchemy_instrumented is True


def test_instrument_sqlalchemy_logs_warning_on_error(caplog):
    otel = _reload_otel()
    otel._sqlalchemy_instrumented = False

    with patch(
        "opentelemetry.instrumentation.sqlalchemy.SQLAlchemyInstrumentor"
    ) as mock_sqlalchemy:
        mock_sqlalchemy.return_value.instrument.side_effect = RuntimeError("sql-boom")
        otel._instrument_sqlalchemy(object())

    assert "Failed to instrument SQLAlchemy" in caplog.text
    assert otel._sqlalchemy_instrumented is False
