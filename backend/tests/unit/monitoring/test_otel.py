"""Tests for OpenTelemetry configuration."""

from __future__ import annotations

from contextlib import contextmanager
from importlib import reload
import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi import FastAPI


class TestOtelConfiguration:
    """Test OTel initialization and configuration."""

    def test_otel_disabled_by_default(self):
        with patch.dict(os.environ, {"ENABLE_OTEL": "false"}):
            from app.monitoring import otel

            reload(otel)
            assert otel.is_otel_enabled() is False

    def test_otel_enabled_when_flag_true(self):
        with patch.dict(os.environ, {"ENABLE_OTEL": "true"}):
            from app.monitoring import otel

            reload(otel)
            assert otel.is_otel_enabled() is True

    def test_get_trace_id_returns_none_when_disabled(self):
        with patch.dict(os.environ, {"ENABLE_OTEL": "false"}):
            from app.monitoring import otel

            reload(otel)
            assert otel.get_current_trace_id() is None

    def test_init_otel_returns_false_when_disabled(self):
        with patch.dict(os.environ, {"ENABLE_OTEL": "false"}):
            from app.monitoring import otel

            reload(otel)
            assert otel.init_otel() is False

    def test_init_otel_succeeds_when_enabled(self):
        with patch.dict(
            os.environ,
            {
                "ENABLE_OTEL": "true",
                "AXIOM_API_TOKEN": "test-token",
                "AXIOM_TRACES_DATASET": "test-dataset",
            },
        ):
            from app.monitoring import otel

            reload(otel)

            with patch(
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

    def test_init_otel_idempotent(self):
        with patch.dict(
            os.environ,
            {
                "ENABLE_OTEL": "true",
                "AXIOM_API_TOKEN": "test-token",
                "AXIOM_TRACES_DATASET": "test-dataset",
            },
        ):
            from app.monitoring import otel

            reload(otel)

            with patch(
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
                assert otel.init_otel() is True
                mock_exporter.assert_called_once()

            otel.shutdown_otel()

    def test_sqlalchemy_instrumentation_uses_engine(self):
        with patch.dict(
            os.environ,
            {
                "ENABLE_OTEL": "true",
                "AXIOM_API_TOKEN": "test-token",
                "AXIOM_TRACES_DATASET": "test-dataset",
            },
        ):
            from app.monitoring import otel

            reload(otel)

            engine = object()
            otel.instrument_database(engine)

            with patch(
                "opentelemetry.exporter.otlp.proto.http.trace_exporter.OTLPSpanExporter"
            ) as mock_exporter, patch(
                "opentelemetry.sdk.trace.export.BatchSpanProcessor"
            ) as mock_processor, patch(
                "opentelemetry.instrumentation.logging.LoggingInstrumentor"
            ) as mock_logging, patch(
                "opentelemetry.sdk.trace.TracerProvider"
            ) as mock_provider, patch(
                "opentelemetry.instrumentation.sqlalchemy.SQLAlchemyInstrumentor"
            ) as mock_sqlalchemy:
                mock_logging.return_value.instrument.return_value = None
                mock_processor.return_value = MagicMock()
                mock_provider.return_value = MagicMock()
                mock_sqlalchemy.return_value.instrument.return_value = None

                assert otel.init_otel() is True
                mock_exporter.assert_called_once()
                mock_sqlalchemy.return_value.instrument.assert_called_once_with(engine=engine)

            otel.shutdown_otel()

    def test_instrument_fastapi_excludes_health_and_sse(self):
        with patch.dict(os.environ, {"ENABLE_OTEL": "true"}):
            from app.monitoring import otel

            reload(otel)
            app = FastAPI()

            with patch(
                "opentelemetry.instrumentation.fastapi.FastAPIInstrumentor.instrument_app"
            ) as mock_instrument:
                assert otel.instrument_fastapi(app) is True
                excluded_urls = mock_instrument.call_args.kwargs.get("excluded_urls", "")
                assert "api/v1/health" in excluded_urls
                assert "api/v1/ready" in excluded_urls
                assert "api/v1/messages/stream" in excluded_urls


def test_parse_otlp_headers_and_safe_int():
    from app.monitoring import otel

    reload(otel)
    headers = otel._parse_otlp_headers(
        "Authorization=Bearer%20token, bad-entry, =oops, X-Test=hello"
    )
    assert headers == {"Authorization": "Bearer token", "X-Test": "hello"}

    with patch.dict(os.environ, {"OTEL_BSP_MAX_QUEUE_SIZE": "nope"}):
        assert otel._safe_int("OTEL_BSP_MAX_QUEUE_SIZE", 321) == 321
    with patch.dict(os.environ, {"OTEL_BSP_MAX_QUEUE_SIZE": "64"}):
        assert otel._safe_int("OTEL_BSP_MAX_QUEUE_SIZE", 321) == 64


def test_init_otel_uses_explicit_headers_and_endpoint():
    with patch.dict(
        os.environ,
        {
            "ENABLE_OTEL": "true",
            "OTEL_EXPORTER_OTLP_HEADERS": "Authorization=Bearer%20token, X-Test=hello",
            "OTEL_EXPORTER_OTLP_ENDPOINT": "https://example.com/v1/traces",
        },
    ):
        from app.monitoring import otel

        reload(otel)

        with patch(
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
            kwargs = mock_exporter.call_args.kwargs
            assert kwargs["endpoint"] == "https://example.com/v1/traces"
            assert kwargs["headers"] == {"Authorization": "Bearer token", "X-Test": "hello"}

        otel.shutdown_otel()


def test_get_current_ids_and_create_span():
    from app.monitoring import otel

    reload(otel)

    class DummyContext:
        is_valid = True
        trace_id = 0xabc
        span_id = 0x1234

    class DummySpan:
        def get_span_context(self):
            return DummyContext()

    with patch.object(otel, "is_otel_enabled", return_value=True), patch(
        "opentelemetry.trace.get_current_span", return_value=DummySpan()
    ):
        assert otel.get_current_trace_id() == format(0xabc, "032x")
        assert otel.get_current_span_id() == format(0x1234, "016x")

    class DummySpanRecorder:
        def __init__(self) -> None:
            self.attrs: dict[str, object] = {}

        def set_attribute(self, key: str, value: object) -> None:
            self.attrs[key] = value

    @contextmanager
    def _dummy_span():
        span = DummySpanRecorder()
        yield span

    class DummyTracer:
        def start_as_current_span(self, _name: str):
            return _dummy_span()

    with patch.object(otel, "is_otel_enabled", return_value=True), patch(
        "opentelemetry.trace.get_tracer", return_value=DummyTracer()
    ):
        with otel.create_span("work", {"attr": 1}) as span:
            assert span is not None
            assert span.attrs["attr"] == 1


def test_instrument_additional_libraries_and_shutdown():
    from app.monitoring import otel

    reload(otel)
    otel._sqlalchemy_engine = object()

    with patch.object(otel, "is_otel_enabled", return_value=True), patch.object(
        otel, "_instrument_sqlalchemy"
    ) as mock_sqlalchemy, patch(
        "opentelemetry.instrumentation.httpx.HTTPXClientInstrumentor"
    ) as mock_httpx, patch(
        "opentelemetry.instrumentation.redis.RedisInstrumentor"
    ) as mock_redis:
        mock_httpx.return_value.instrument.return_value = None
        mock_redis.return_value.instrument.return_value = None
        otel.instrument_additional_libraries()
        mock_sqlalchemy.assert_called_once()
        mock_httpx.return_value.instrument.assert_called_once()
        mock_redis.return_value.instrument.assert_called_once()

    dummy_provider = SimpleNamespace(shutdown=lambda: None)
    otel._tracer_provider = dummy_provider
    otel._otel_initialized = True
    otel._sqlalchemy_instrumented = True
    otel.shutdown_otel()
    assert otel._tracer_provider is None
    assert otel._otel_initialized is False
    assert otel._sqlalchemy_instrumented is False
