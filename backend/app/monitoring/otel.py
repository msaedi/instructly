"""
OpenTelemetry configuration for InstaInstru.

This module initializes distributed tracing with Axiom as the backend.
Enable/disable via ENABLE_OTEL environment variable.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import logging
import os
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from opentelemetry.sdk.trace import TracerProvider

logger = logging.getLogger(__name__)

# Feature flag - allows quick disable without redeploy
OTEL_ENABLED = os.getenv("ENABLE_OTEL", "false").lower() == "true"

# Lazy imports to avoid loading OTel when disabled
_tracer_provider: Optional["TracerProvider"] = None
_initialized = False


def is_otel_enabled() -> bool:
    """Check if OpenTelemetry is enabled."""
    return OTEL_ENABLED


def _parse_otlp_headers(raw: str) -> dict[str, str]:
    headers: dict[str, str] = {}
    for entry in raw.split(","):
        if not entry.strip() or "=" not in entry:
            continue
        key, value = entry.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key:
            headers[key] = value
    return headers


def init_otel(service_name: Optional[str] = None) -> bool:
    """
    Initialize OpenTelemetry tracing for the application.

    Args:
        service_name: Override service name (defaults to OTEL_SERVICE_NAME env var)

    Returns:
        True if initialization succeeded, False if disabled or failed
    """
    global _tracer_provider, _initialized

    if _initialized:
        logger.debug("OTel already initialized, skipping")
        return True

    if not OTEL_ENABLED:
        logger.info("OpenTelemetry disabled (ENABLE_OTEL != 'true')")
        return False

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.logging import LoggingInstrumentor
        from opentelemetry.sdk.resources import SERVICE_NAME, SERVICE_VERSION, Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        svc_name = service_name or os.getenv("OTEL_SERVICE_NAME", "instainstru-api")
        svc_version = os.getenv("GIT_SHA", "unknown")
        environment = os.getenv("ENVIRONMENT", "development")

        resource = Resource.create(
            {
                SERVICE_NAME: svc_name,
                SERVICE_VERSION: svc_version,
                "deployment.environment": environment,
            }
        )

        _tracer_provider = TracerProvider(resource=resource)
        trace.set_tracer_provider(_tracer_provider)

        raw_headers = os.getenv("OTEL_EXPORTER_OTLP_HEADERS", "").strip()
        exporter_headers: dict[str, str] | None = None
        if raw_headers:
            exporter_headers = _parse_otlp_headers(raw_headers)
        else:
            axiom_token = os.getenv("AXIOM_API_TOKEN")
            axiom_dataset = os.getenv("AXIOM_TRACES_DATASET", "instainstru-traces")
            if axiom_token:
                exporter_headers = {
                    "Authorization": f"Bearer {axiom_token}",
                    "X-Axiom-Dataset": axiom_dataset,
                }

        otlp_endpoint = os.getenv(
            "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
            os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "https://api.axiom.co") + "/v1/traces",
        )

        exporter = OTLPSpanExporter(
            endpoint=otlp_endpoint,
            headers=exporter_headers or None,
        )

        span_processor = BatchSpanProcessor(
            exporter,
            max_queue_size=2048,
            max_export_batch_size=512,
            schedule_delay_millis=5000,
        )
        _tracer_provider.add_span_processor(span_processor)

        # Enable log correlation (inject trace_id into log records)
        # IMPORTANT: set_logging_format=False to avoid conflicting with existing JSON logging
        LoggingInstrumentor().instrument(set_logging_format=False)

        try:
            from opentelemetry.instrumentation.celery import CeleryInstrumentor

            CeleryInstrumentor().instrument()
            logger.debug("Celery instrumented")
        except ImportError:
            pass
        except Exception as exc:
            logger.warning("Failed to instrument Celery: %s", exc)

        _initialized = True
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


def instrument_fastapi(app: Any) -> bool:
    """
    Instrument a FastAPI application with OpenTelemetry.

    Args:
        app: FastAPI application instance

    Returns:
        True if instrumentation succeeded
    """
    if not OTEL_ENABLED:
        return False

    if getattr(app, "_otel_instrumented", False):
        return True

    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        from app.core.constants import SSE_PATH_PREFIX

        excluded_urls = ",".join(
            [
                "health",
                "ready",
                "metrics",
                "api/v1/health",
                "api/v1/ready",
                "api/v1/metrics",
                SSE_PATH_PREFIX.lstrip("/"),
            ]
        )

        FastAPIInstrumentor.instrument_app(
            app,
            excluded_urls=excluded_urls,
        )

        setattr(app, "_otel_instrumented", True)
        logger.info("FastAPI instrumented with OTel (excluded: %s)", excluded_urls)
        return True

    except Exception as exc:
        logger.error("Failed to instrument FastAPI: %s", exc, exc_info=True)
        return False


def instrument_additional_libraries() -> None:
    """
    Instrument additional libraries used by the application.
    Call after init_otel().
    """
    if not OTEL_ENABLED:
        return

    try:
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

        SQLAlchemyInstrumentor().instrument()
        logger.debug("SQLAlchemy instrumented")
    except ImportError:
        pass
    except Exception as exc:
        logger.warning("Failed to instrument SQLAlchemy: %s", exc)

    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

        HTTPXClientInstrumentor().instrument()
        logger.debug("HTTPX instrumented")
    except ImportError:
        pass
    except Exception as exc:
        logger.warning("Failed to instrument HTTPX: %s", exc)

    try:
        from opentelemetry.instrumentation.redis import RedisInstrumentor

        RedisInstrumentor().instrument()
        logger.debug("Redis instrumented")
    except ImportError:
        pass
    except Exception as exc:
        logger.warning("Failed to instrument Redis: %s", exc)


def shutdown_otel() -> None:
    """Gracefully shutdown OpenTelemetry (flush pending spans)."""
    global _tracer_provider, _initialized

    if _tracer_provider is not None:
        try:
            _tracer_provider.shutdown()
            logger.info("OpenTelemetry shutdown complete")
        except Exception as exc:
            logger.error("Error during OTel shutdown: %s", exc)

    _initialized = False
    _tracer_provider = None


def get_current_trace_id() -> Optional[str]:
    """
    Get the current trace ID as a hex string.
    Useful for adding to Sentry tags or response headers.

    Returns:
        32-character hex trace ID, or None if no active span
    """
    if not OTEL_ENABLED:
        return None

    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        if span is None:
            return None

        ctx = span.get_span_context()
        if ctx is None or not ctx.is_valid:
            return None

        return format(ctx.trace_id, "032x")

    except Exception:
        return None


def get_current_span_id() -> Optional[str]:
    """
    Get the current span ID as a hex string.

    Returns:
        16-character hex span ID, or None if no active span
    """
    if not OTEL_ENABLED:
        return None

    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        if span is None:
            return None

        ctx = span.get_span_context()
        if ctx is None or not ctx.is_valid:
            return None

        return format(ctx.span_id, "016x")

    except Exception:
        return None


@contextmanager
def create_span(name: str, attributes: Optional[dict[str, Any]] = None) -> Iterator[Optional[Any]]:
    """
    Create a custom span for manual instrumentation.

    Usage:
        with create_span("process_payment", {"payment.amount": 100}):
            # ... do work ...
    """
    if not OTEL_ENABLED:
        yield None
        return

    try:
        from opentelemetry import trace

        tracer = trace.get_tracer(__name__)
        with tracer.start_as_current_span(name) as span:
            if attributes:
                for key, value in attributes.items():
                    span.set_attribute(key, value)
            yield span

    except Exception as exc:
        logger.warning("Failed to create span '%s': %s", name, exc)
        yield None
