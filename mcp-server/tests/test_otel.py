from __future__ import annotations

import importlib
import logging
import sys
import types

import pytest
from instainstru_mcp import otel as otel_mod


def _ensure_module(name: str, *, package: bool = False) -> types.ModuleType:
    module = types.ModuleType(name)
    if package:
        module.__path__ = []  # type: ignore[attr-defined]
    sys.modules[name] = module
    return module


@pytest.fixture(autouse=True)
def _stub_opentelemetry_modules():
    created: list[str] = []

    def ensure(name: str, *, package: bool = False) -> types.ModuleType | None:
        if name in sys.modules:
            return None
        try:
            importlib.import_module(name)
            return None
        except Exception:
            created.append(name)
            return _ensure_module(name, package=package)

    ensure("opentelemetry", package=True)
    ensure("opentelemetry.exporter", package=True)
    ensure("opentelemetry.exporter.otlp", package=True)
    ensure("opentelemetry.exporter.otlp.proto", package=True)
    ensure("opentelemetry.exporter.otlp.proto.http", package=True)
    trace_exporter = ensure("opentelemetry.exporter.otlp.proto.http.trace_exporter")
    if trace_exporter is not None and not hasattr(trace_exporter, "OTLPSpanExporter"):

        class OTLPSpanExporter:
            def __init__(self, endpoint=None, headers=None):
                self.endpoint = endpoint
                self.headers = headers

        trace_exporter.OTLPSpanExporter = OTLPSpanExporter

    ensure("opentelemetry.instrumentation", package=True)
    logging_module = ensure("opentelemetry.instrumentation.logging")
    if logging_module is not None and not hasattr(logging_module, "LoggingInstrumentor"):

        class LoggingInstrumentor:
            def instrument(self, set_logging_format=False):
                self.set_logging_format = set_logging_format

        logging_module.LoggingInstrumentor = LoggingInstrumentor

    asgi_module = ensure("opentelemetry.instrumentation.asgi")
    if asgi_module is not None and not hasattr(asgi_module, "OpenTelemetryMiddleware"):

        class OpenTelemetryMiddleware:
            def __init__(self, app, excluded_urls=None):
                self.app = app
                self.excluded_urls = excluded_urls

        asgi_module.OpenTelemetryMiddleware = OpenTelemetryMiddleware

    ensure("opentelemetry.sdk", package=True)
    resources_module = ensure("opentelemetry.sdk.resources")
    if resources_module is not None:
        resources_module.SERVICE_NAME = "service.name"
        resources_module.SERVICE_VERSION = "service.version"

        class Resource:
            @staticmethod
            def create(attrs):
                return attrs

        resources_module.Resource = Resource

    trace_module = ensure("opentelemetry.sdk.trace")
    if trace_module is not None and not hasattr(trace_module, "TracerProvider"):

        class TracerProvider:
            def __init__(self, resource=None):
                self.resource = resource

            def add_span_processor(self, processor):
                self.processor = processor

        trace_module.TracerProvider = TracerProvider

    trace_export_module = ensure("opentelemetry.sdk.trace.export")
    if trace_export_module is not None and not hasattr(trace_export_module, "BatchSpanProcessor"):

        class BatchSpanProcessor:
            def __init__(self, exporter):
                self.exporter = exporter

        trace_export_module.BatchSpanProcessor = BatchSpanProcessor

    otel_trace_module = ensure("opentelemetry.trace")
    if otel_trace_module is not None and not hasattr(otel_trace_module, "set_tracer_provider"):

        def set_tracer_provider(provider):
            return None

        otel_trace_module.set_tracer_provider = set_tracer_provider

    yield

    for name in created:
        sys.modules.pop(name, None)


@pytest.fixture(autouse=True)
def _reset_otel_state(monkeypatch: pytest.MonkeyPatch):
    otel_mod._otel_initialized = False
    otel_mod._tracer_provider = None
    otel_mod._otel_wrapped_ids.clear()
    monkeypatch.delenv("ENABLE_OTEL", raising=False)
    monkeypatch.delenv("OTEL_SERVICE_NAME", raising=False)
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_HEADERS", raising=False)
    monkeypatch.delenv("AXIOM_API_TOKEN", raising=False)
    monkeypatch.delenv("AXIOM_TRACES_DATASET", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("GIT_SHA", raising=False)
    yield
    otel_mod._otel_initialized = False
    otel_mod._tracer_provider = None
    otel_mod._otel_wrapped_ids.clear()


def test_is_truthy_env() -> None:
    assert otel_mod._is_truthy_env(None) is False
    assert otel_mod._is_truthy_env("true") is True
    assert otel_mod._is_truthy_env("  YeS ") is True
    assert otel_mod._is_truthy_env("0") is False


def test_is_otel_enabled_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENABLE_OTEL", "true")
    assert otel_mod.is_otel_enabled() is True
    monkeypatch.setenv("ENABLE_OTEL", "false")
    assert otel_mod.is_otel_enabled() is False


def test_parse_otlp_headers_handles_malformed(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING)
    headers = otel_mod._parse_otlp_headers("foo,=bar,key=value%20x,token=abc")
    assert headers == {"key": "value x", "token": "abc"}
    assert any("Malformed OTLP header entry" in record.message for record in caplog.records)


def test_parse_otlp_headers_empty() -> None:
    assert otel_mod._parse_otlp_headers(None) == {}


def test_parse_otlp_headers_skips_empty_entries() -> None:
    headers = otel_mod._parse_otlp_headers("key=value,,token=abc")
    assert headers == {"key": "value", "token": "abc"}


def test_init_otel_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENABLE_OTEL", "false")
    assert otel_mod.init_otel() is False
    assert otel_mod._otel_initialized is False


def test_init_otel_already_initialized(monkeypatch: pytest.MonkeyPatch) -> None:
    otel_mod._otel_initialized = True
    monkeypatch.setenv("ENABLE_OTEL", "true")
    assert otel_mod.init_otel() is True


def test_init_otel_success(monkeypatch: pytest.MonkeyPatch) -> None:
    import opentelemetry.exporter.otlp.proto.http.trace_exporter as otlp_exporter
    import opentelemetry.instrumentation.logging as logging_instr
    import opentelemetry.sdk.resources as resources
    import opentelemetry.sdk.trace as sdk_trace
    import opentelemetry.sdk.trace.export as sdk_export
    import opentelemetry.trace as trace_mod

    providers: list[object] = []

    class DummyTracerProvider:
        def __init__(self, resource=None):
            self.resource = resource
            self.processors: list[object] = []

        def add_span_processor(self, processor):
            self.processors.append(processor)

    class DummyExporter:
        def __init__(self, endpoint=None, headers=None):
            self.endpoint = endpoint
            self.headers = headers

    class DummyBatchSpanProcessor:
        def __init__(self, exporter):
            self.exporter = exporter

    class DummyLoggingInstrumentor:
        def instrument(self, set_logging_format=False):
            self.set_logging_format = set_logging_format

    class DummyResource:
        @staticmethod
        def create(attrs):
            return attrs

    def fake_set_tracer_provider(provider):
        providers.append(provider)

    monkeypatch.setattr(trace_mod, "set_tracer_provider", fake_set_tracer_provider)
    monkeypatch.setattr(sdk_trace, "TracerProvider", DummyTracerProvider)
    monkeypatch.setattr(otlp_exporter, "OTLPSpanExporter", DummyExporter)
    monkeypatch.setattr(sdk_export, "BatchSpanProcessor", DummyBatchSpanProcessor)
    monkeypatch.setattr(logging_instr, "LoggingInstrumentor", DummyLoggingInstrumentor)
    monkeypatch.setattr(resources, "Resource", DummyResource)

    monkeypatch.setenv("ENABLE_OTEL", "true")
    monkeypatch.setenv("OTEL_SERVICE_NAME", "instainstru-mcp-test")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "https://example.com")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_HEADERS", "Authorization=Bearer%20token")

    assert otel_mod.init_otel() is True
    assert otel_mod._otel_initialized is True
    assert providers
    provider = providers[0]
    assert isinstance(provider, DummyTracerProvider)
    assert provider.processors
    processor = provider.processors[0]
    exporter = processor.exporter
    assert exporter.endpoint == "https://example.com/v1/traces"
    assert exporter.headers == {"Authorization": "Bearer token"}


def test_init_otel_handles_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    import opentelemetry.sdk.trace as sdk_trace

    class BoomProvider:
        def __init__(self, resource=None):
            raise RuntimeError("boom")

    monkeypatch.setattr(sdk_trace, "TracerProvider", BoomProvider)
    monkeypatch.setenv("ENABLE_OTEL", "true")
    assert otel_mod.init_otel() is False


def test_instrument_app_no_otel(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENABLE_OTEL", "false")
    app = object()
    assert otel_mod.instrument_app(app) is app


def test_instrument_app_already_wrapped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENABLE_OTEL", "true")
    otel_mod._otel_initialized = True
    app = types.SimpleNamespace(_otel_wrapped=True)
    assert otel_mod.instrument_app(app) is app


def test_instrument_app_success(monkeypatch: pytest.MonkeyPatch) -> None:
    import opentelemetry.instrumentation.asgi as asgi_instr

    class DummyMiddleware:
        def __init__(self, app, excluded_urls=None):
            self.app = app
            self.excluded_urls = excluded_urls

    monkeypatch.setattr(asgi_instr, "OpenTelemetryMiddleware", DummyMiddleware)
    monkeypatch.setenv("ENABLE_OTEL", "true")
    otel_mod._otel_initialized = True
    app = object()
    wrapped = otel_mod.instrument_app(app)
    assert isinstance(wrapped, DummyMiddleware)
    assert wrapped.excluded_urls == "health,/api/v1/health"
    assert getattr(wrapped, "_otel_wrapped", False) is True


def test_instrument_app_handles_exception(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    import opentelemetry.instrumentation.asgi as asgi_instr

    def boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(asgi_instr, "OpenTelemetryMiddleware", boom)
    monkeypatch.setenv("ENABLE_OTEL", "true")
    otel_mod._otel_initialized = True
    caplog.set_level(logging.ERROR)
    app = object()
    assert otel_mod.instrument_app(app) is app
    assert any("Failed to instrument MCP ASGI app" in record.message for record in caplog.records)


def test_init_otel_axiom_token_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """When OTEL_EXPORTER_OTLP_HEADERS is absent, construct from AXIOM_API_TOKEN."""
    import opentelemetry.exporter.otlp.proto.http.trace_exporter as otlp_exporter
    import opentelemetry.instrumentation.logging as logging_instr
    import opentelemetry.sdk.resources as resources
    import opentelemetry.sdk.trace as sdk_trace
    import opentelemetry.sdk.trace.export as sdk_export
    import opentelemetry.trace as trace_mod

    class DummyTracerProvider:
        def __init__(self, resource=None):
            self.resource = resource
            self.processors: list[object] = []

        def add_span_processor(self, processor):
            self.processors.append(processor)

    class DummyExporter:
        def __init__(self, endpoint=None, headers=None):
            self.endpoint = endpoint
            self.headers = headers

    class DummyBatchSpanProcessor:
        def __init__(self, exporter):
            self.exporter = exporter

    class DummyLoggingInstrumentor:
        def instrument(self, set_logging_format=False):
            pass

    class DummyResource:
        @staticmethod
        def create(attrs):
            return attrs

    monkeypatch.setattr(trace_mod, "set_tracer_provider", lambda p: None)
    monkeypatch.setattr(sdk_trace, "TracerProvider", DummyTracerProvider)
    monkeypatch.setattr(otlp_exporter, "OTLPSpanExporter", DummyExporter)
    monkeypatch.setattr(sdk_export, "BatchSpanProcessor", DummyBatchSpanProcessor)
    monkeypatch.setattr(logging_instr, "LoggingInstrumentor", DummyLoggingInstrumentor)
    monkeypatch.setattr(resources, "Resource", DummyResource)

    monkeypatch.setenv("ENABLE_OTEL", "true")
    # No OTEL_EXPORTER_OTLP_HEADERS set - should fall back to AXIOM vars
    monkeypatch.setenv("AXIOM_API_TOKEN", "xaat-test-token")
    monkeypatch.setenv("AXIOM_TRACES_DATASET", "my-dataset")

    assert otel_mod.init_otel() is True

    provider = otel_mod._tracer_provider
    assert provider is not None
    processor = provider.processors[0]
    exporter = processor.exporter
    assert exporter.headers == {
        "Authorization": "Bearer xaat-test-token",
        "X-Axiom-Dataset": "my-dataset",
    }
