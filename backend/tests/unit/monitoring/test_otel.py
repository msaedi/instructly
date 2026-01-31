"""Tests for OpenTelemetry configuration."""

from __future__ import annotations

from importlib import reload
import os
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
