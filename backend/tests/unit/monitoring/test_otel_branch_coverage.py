"""Additional branch coverage tests for app.monitoring.otel."""

from __future__ import annotations

import builtins
from contextlib import contextmanager
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


def test_truthy_and_empty_header_parsing_defaults():
    otel = _reload_otel()
    assert otel._is_truthy_env(None) is False
    assert otel._parse_otlp_headers(None) == {}
    assert otel._parse_otlp_headers("") == {}


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


def test_init_otel_handles_celery_import_error():
    with patch.dict(
        os.environ,
        {
            "ENABLE_OTEL": "true",
            "AXIOM_API_TOKEN": "token",
            "AXIOM_TRACES_DATASET": "dataset",
        },
    ):
        otel = _reload_otel()
        real_import = builtins.__import__

        def _import(name, *args, **kwargs):
            if name == "opentelemetry.instrumentation.celery":
                raise ImportError("no-celery")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=_import), patch(
            "opentelemetry.exporter.otlp.proto.http.trace_exporter.OTLPSpanExporter"
        ) as mock_exporter, patch(
            "opentelemetry.sdk.trace.export.BatchSpanProcessor"
        ) as mock_processor, patch(
            "opentelemetry.instrumentation.logging.LoggingInstrumentor"
        ) as mock_logging, patch(
            "opentelemetry.sdk.trace.TracerProvider"
        ) as mock_provider:
            mock_logging.return_value.instrument.return_value = None
            mock_processor.return_value = MagicMock()
            mock_provider.return_value = MagicMock()

            assert otel.init_otel() is True
            mock_exporter.assert_called_once()

        otel.shutdown_otel()


def test_init_otel_returns_false_on_top_level_exception():
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
            "opentelemetry.sdk.trace.TracerProvider",
            side_effect=RuntimeError("provider-boom"),
        ):
            assert otel.init_otel() is False


def test_instrument_fastapi_returns_false_on_instrumentation_error():
    with patch.dict(os.environ, {"ENABLE_OTEL": "true"}):
        otel = _reload_otel()
        app = FastAPI()

        with patch(
            "opentelemetry.instrumentation.fastapi.FastAPIInstrumentor.instrument_app",
            side_effect=RuntimeError("boom"),
        ):
            assert otel.instrument_fastapi(app) is False


def test_instrument_fastapi_returns_false_when_disabled():
    with patch.dict(os.environ, {"ENABLE_OTEL": "false"}):
        otel = _reload_otel()
        assert otel.instrument_fastapi(FastAPI()) is False


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


def test_instrument_database_calls_sqlalchemy_when_ready():
    otel = _reload_otel()
    otel._otel_initialized = True

    with patch.object(otel, "is_otel_enabled", return_value=True), patch.object(
        otel, "_instrument_sqlalchemy"
    ) as mock_instrument:
        engine = object()
        otel.instrument_database(engine)
        mock_instrument.assert_called_once_with(engine)


def test_instrument_additional_libraries_returns_when_disabled():
    otel = _reload_otel()
    with patch.object(otel, "is_otel_enabled", return_value=False), patch.object(
        otel, "_instrument_sqlalchemy"
    ) as mock_sql:
        otel.instrument_additional_libraries()
        mock_sql.assert_not_called()


def test_instrument_additional_libraries_handles_import_errors():
    otel = _reload_otel()
    real_import = builtins.__import__

    def _import(name, *args, **kwargs):
        if name in {
            "opentelemetry.instrumentation.httpx",
            "opentelemetry.instrumentation.redis",
        }:
            raise ImportError("missing-instrumentor")
        return real_import(name, *args, **kwargs)

    with patch.object(otel, "is_otel_enabled", return_value=True), patch(
        "builtins.__import__", side_effect=_import
    ):
        otel.instrument_additional_libraries()


def test_instrument_additional_libraries_handles_runtime_errors(caplog):
    otel = _reload_otel()
    with patch.object(otel, "is_otel_enabled", return_value=True), patch(
        "opentelemetry.instrumentation.httpx.HTTPXClientInstrumentor"
    ) as mock_httpx, patch(
        "opentelemetry.instrumentation.redis.RedisInstrumentor"
    ) as mock_redis:
        mock_httpx.return_value.instrument.side_effect = RuntimeError("httpx-boom")
        mock_redis.return_value.instrument.side_effect = RuntimeError("redis-boom")
        otel.instrument_additional_libraries()

    assert "Failed to instrument HTTPX" in caplog.text
    assert "Failed to instrument Redis" in caplog.text


def test_shutdown_otel_logs_provider_shutdown_error(caplog):
    otel = _reload_otel()
    otel._otel_initialized = True

    class _Provider:
        def shutdown(self):
            raise RuntimeError("shutdown-boom")

    otel._tracer_provider = _Provider()
    otel.shutdown_otel()
    assert "Error during OTel shutdown" in caplog.text


def test_get_current_ids_handle_none_invalid_and_exception():
    otel = _reload_otel()
    with patch.object(otel, "is_otel_enabled", return_value=True), patch(
        "opentelemetry.trace.get_current_span", return_value=None
    ):
        assert otel.get_current_trace_id() is None
        assert otel.get_current_span_id() is None

    class _InvalidCtx:
        is_valid = False
        trace_id = 1
        span_id = 2

    class _Span:
        def get_span_context(self):
            return _InvalidCtx()

    with patch.object(otel, "is_otel_enabled", return_value=True), patch(
        "opentelemetry.trace.get_current_span", return_value=_Span()
    ):
        assert otel.get_current_trace_id() is None
        assert otel.get_current_span_id() is None

    with patch.object(otel, "is_otel_enabled", return_value=True), patch(
        "opentelemetry.trace.get_current_span", side_effect=RuntimeError("boom")
    ):
        assert otel.get_current_trace_id() is None
        assert otel.get_current_span_id() is None


def test_create_span_disabled_and_error_path(caplog):
    otel = _reload_otel()
    with patch.object(otel, "is_otel_enabled", return_value=False):
        with otel.create_span("disabled") as span:
            assert span is None

    class _Tracer:
        @contextmanager
        def start_as_current_span(self, _name: str):
            raise RuntimeError("span-boom")
            yield  # pragma: no cover

    with patch.object(otel, "is_otel_enabled", return_value=True), patch(
        "opentelemetry.trace.get_tracer", return_value=_Tracer()
    ):
        with otel.create_span("err") as span:
            assert span is None
    assert "Failed to create span" in caplog.text
