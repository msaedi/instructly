"""Tests for OpenTelemetry configuration."""

from __future__ import annotations

from contextlib import contextmanager
from importlib import reload
import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
import pytest


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


def test_create_span_propagates_caller_exceptions():
    from app.monitoring import otel

    reload(otel)

    class DummySpanRecorder:
        def set_attribute(self, _key: str, _value: object) -> None:
            return None

    @contextmanager
    def _dummy_span():
        yield DummySpanRecorder()

    class DummyTracer:
        def start_as_current_span(self, _name: str):
            return _dummy_span()

    with patch.object(otel, "is_otel_enabled", return_value=True), patch(
        "opentelemetry.trace.get_tracer", return_value=DummyTracer()
    ):
        with pytest.raises(RuntimeError, match="caller boom"):
            with otel.create_span("work"):
                raise RuntimeError("caller boom")


def test_create_span_exits_when_attribute_setup_fails():
    from app.monitoring import otel

    reload(otel)

    attr_exc = RuntimeError("attr boom")
    span = MagicMock()
    span.set_attribute.side_effect = attr_exc
    span_cm = MagicMock()
    span_cm.__enter__.return_value = span

    class DummyTracer:
        def start_as_current_span(self, _name: str):
            return span_cm

    with patch.object(otel, "is_otel_enabled", return_value=True), patch(
        "opentelemetry.trace.get_tracer", return_value=DummyTracer()
    ):
        with otel.create_span("work", {"attr": 1}) as created_span:
            assert created_span is None

    span_cm.__exit__.assert_called_once()
    exc_type, exc_value, exc_tb = span_cm.__exit__.call_args.args
    assert exc_type is RuntimeError
    assert exc_value is attr_exc
    assert exc_tb is attr_exc.__traceback__


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


class TestFilteringSpanProcessor:
    """Tests for the FilteringSpanProcessor that drops noisy spans."""

    def _make_span(self, name: str, scope_name: str) -> MagicMock:
        span = MagicMock()
        span.name = name
        scope = MagicMock()
        scope.name = scope_name
        span.instrumentation_scope = scope
        return span

    def test_suppresses_sqlalchemy_connect_span(self):
        from app.monitoring.otel import FilteringSpanProcessor

        inner = MagicMock()
        processor = FilteringSpanProcessor(inner)
        span = self._make_span("connect", "opentelemetry.instrumentation.sqlalchemy")

        processor.on_end(span)

        inner.on_end.assert_not_called()

    def test_passes_non_connect_span(self):
        from app.monitoring.otel import FilteringSpanProcessor

        inner = MagicMock()
        processor = FilteringSpanProcessor(inner)
        span = self._make_span("SELECT postgres", "opentelemetry.instrumentation.sqlalchemy")

        processor.on_end(span)

        inner.on_end.assert_called_once_with(span)

    def test_passes_connect_from_other_scope(self):
        from app.monitoring.otel import FilteringSpanProcessor

        inner = MagicMock()
        processor = FilteringSpanProcessor(inner)
        span = self._make_span("connect", "opentelemetry.instrumentation.redis")

        processor.on_end(span)

        inner.on_end.assert_called_once_with(span)

    def test_delegates_on_start(self):
        from app.monitoring.otel import FilteringSpanProcessor

        inner = MagicMock()
        processor = FilteringSpanProcessor(inner)
        span = MagicMock()
        context = MagicMock()

        processor.on_start(span, context)

        inner.on_start.assert_called_once_with(span, context)

    def test_delegates_on_ending(self):
        from app.monitoring.otel import FilteringSpanProcessor

        inner = MagicMock()
        processor = FilteringSpanProcessor(inner)
        span = MagicMock()

        processor._on_ending(span)

        inner._on_ending.assert_called_once_with(span)

    def test_delegates_shutdown_and_flush(self):
        from app.monitoring.otel import FilteringSpanProcessor

        inner = MagicMock()
        inner.force_flush.return_value = True
        processor = FilteringSpanProcessor(inner)

        processor.shutdown()
        inner.shutdown.assert_called_once()

        result = processor.force_flush(5000)
        inner.force_flush.assert_called_once_with(5000)
        assert result is True

    def test_handles_span_with_no_scope(self):
        from app.monitoring.otel import FilteringSpanProcessor

        inner = MagicMock()
        processor = FilteringSpanProcessor(inner)
        span = MagicMock()
        span.name = "connect"
        span.instrumentation_scope = None

        processor.on_end(span)

        inner.on_end.assert_called_once_with(span)


class TestAddBusinessContext:
    """Tests for the add_business_context helper."""

    def test_sets_user_id_attribute(self):
        from app.monitoring import otel

        mock_span = MagicMock()
        with patch.object(otel, "is_otel_enabled", return_value=True), patch(
            "opentelemetry.trace.get_current_span", return_value=mock_span
        ):
            otel.add_business_context(user_id="01ABC123DEF456GH789JK0LM01")

        mock_span.set_attribute.assert_called_once_with(
            "app.user_id", "01ABC123DEF456GH789JK0LM01"
        )

    def test_sets_multiple_attributes(self):
        from app.monitoring import otel

        mock_span = MagicMock()
        with patch.object(otel, "is_otel_enabled", return_value=True), patch(
            "opentelemetry.trace.get_current_span", return_value=mock_span
        ):
            otel.add_business_context(
                user_id="01USER",
                booking_id="01BOOK",
                instructor_id="01INST",
            )

        calls = mock_span.set_attribute.call_args_list
        assert len(calls) == 3
        call_dict = {c.args[0]: c.args[1] for c in calls}
        assert call_dict["app.user_id"] == "01USER"
        assert call_dict["app.booking_id"] == "01BOOK"
        assert call_dict["app.instructor_id"] == "01INST"

    def test_skips_none_values(self):
        from app.monitoring import otel

        mock_span = MagicMock()
        with patch.object(otel, "is_otel_enabled", return_value=True), patch(
            "opentelemetry.trace.get_current_span", return_value=mock_span
        ):
            otel.add_business_context(user_id="01USER")

        mock_span.set_attribute.assert_called_once_with("app.user_id", "01USER")

    def test_noop_when_disabled(self):
        from app.monitoring import otel

        with patch.object(otel, "is_otel_enabled", return_value=False), patch(
            "opentelemetry.trace.get_current_span"
        ) as mock_get_span:
            otel.add_business_context(user_id="01ABC")

        mock_get_span.assert_not_called()
