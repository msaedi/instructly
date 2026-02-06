"""OpenTelemetry configuration for the InstaInstru MCP server."""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any, Optional
from urllib.parse import unquote

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from opentelemetry.sdk.trace import TracerProvider

_tracer_provider: Optional["TracerProvider"] = None
_otel_initialized = False
_otel_wrapped_ids: set[int] = set()


def _is_truthy_env(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def is_otel_enabled() -> bool:
    """Check if OpenTelemetry is enabled."""
    return _is_truthy_env(os.getenv("ENABLE_OTEL"))


def _parse_otlp_headers(raw: str | None) -> dict[str, str]:
    headers: dict[str, str] = {}
    if not raw:
        return headers

    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        if "=" not in entry:
            logger.warning("Malformed OTLP header entry (missing '='): %r", entry)
            continue
        key, value = entry.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            logger.warning("Malformed OTLP header entry (empty key): %r", entry)
            continue
        headers[key] = unquote(value)
    return headers


def init_otel(service_name: Optional[str] = None) -> bool:
    """
    Initialize OpenTelemetry tracing for the MCP server.

    Returns True when initialized, False when disabled or failed.
    """
    global _tracer_provider, _otel_initialized

    if _otel_initialized:
        logger.debug("OTel already initialized, skipping")
        return True

    if not is_otel_enabled():
        logger.info("OpenTelemetry disabled (ENABLE_OTEL=%r)", os.getenv("ENABLE_OTEL"))
        return False

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.logging import LoggingInstrumentor
        from opentelemetry.sdk.resources import SERVICE_NAME, SERVICE_VERSION, Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        svc_name = service_name or os.getenv("OTEL_SERVICE_NAME", "instainstru-mcp")
        svc_version = os.getenv("GIT_SHA", "unknown")
        environment = os.getenv("ENVIRONMENT", "development")

        resource_attributes: dict[str, Any] = {
            SERVICE_NAME: svc_name,
            SERVICE_VERSION: svc_version,
            "deployment.environment": environment,
        }
        resource = Resource.create(resource_attributes)

        _tracer_provider = TracerProvider(resource=resource)
        trace.set_tracer_provider(_tracer_provider)

        raw_headers = os.getenv("OTEL_EXPORTER_OTLP_HEADERS", "").strip()
        exporter_headers: dict[str, str] | None = None
        if raw_headers:
            exporter_headers = _parse_otlp_headers(raw_headers)
        else:
            # Fallback: construct from AXIOM_API_TOKEN (matches backend pattern)
            axiom_token = os.getenv("AXIOM_API_TOKEN")
            axiom_dataset = os.getenv("AXIOM_TRACES_DATASET", "instainstru-traces")
            if axiom_token:
                exporter_headers = {
                    "Authorization": f"Bearer {axiom_token}",
                    "X-Axiom-Dataset": axiom_dataset,
                }

        base_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "https://api.axiom.co").rstrip("/")
        otlp_endpoint = f"{base_endpoint}/v1/traces"

        exporter = OTLPSpanExporter(
            endpoint=otlp_endpoint,
            headers=exporter_headers,
        )

        span_processor = BatchSpanProcessor(exporter)
        _tracer_provider.add_span_processor(span_processor)

        LoggingInstrumentor().instrument(set_logging_format=False)

        _otel_initialized = True
        logger.info(
            "OpenTelemetry initialized: service=%s environment=%s endpoint=%s",
            svc_name,
            environment,
            otlp_endpoint,
        )
        return True
    except Exception as exc:
        logger.error("Failed to initialize OpenTelemetry: %s", exc, exc_info=True)
        return False


def instrument_app(app: Any) -> Any:
    """Wrap ASGI app with OpenTelemetry middleware when enabled."""
    if not is_otel_enabled() or not _otel_initialized:
        return app

    if getattr(app, "_otel_wrapped", False) or id(app) in _otel_wrapped_ids:
        return app

    try:
        from opentelemetry.instrumentation.asgi import OpenTelemetryMiddleware

        excluded_urls = "health,/api/v1/health"
        wrapped = OpenTelemetryMiddleware(app, excluded_urls=excluded_urls)
        try:
            setattr(app, "_otel_wrapped", True)
        except Exception:
            _otel_wrapped_ids.add(id(app))
        setattr(wrapped, "_otel_wrapped", True)
        return wrapped
    except Exception as exc:
        logger.error("Failed to instrument MCP ASGI app: %s", exc, exc_info=True)
        return app
